import os
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# ── Configuração ──────────────────────────────────────────
AIRTABLE_KEY    = os.environ['AIRTABLE_KEY']
AIRTABLE_BASE   = os.environ['AIRTABLE_BASE']
AIRTABLE_TABLE  = os.environ['AIRTABLE_TABLE']   # tbllXIzMRWnN4CuPk
RESEND_API_KEY  = os.environ['RESEND_API_KEY']
EMAIL_TO        = os.environ['EMAIL_TO']

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── Airtable: buscar atores ───────────────────────────────
def get_atores():
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE}/{AIRTABLE_TABLE}"
    headers = {"Authorization": f"Bearer {AIRTABLE_KEY}"}
    params = {
        "fields[]": ["Nome", "Url Hancinema", "foto_count"],
        "filterByFormula": "NOT({Url Hancinema} = '')",
        "pageSize": 100
    }
    atores = []
    offset = None
    while True:
        if offset:
            params["offset"] = offset
        res = requests.get(url, headers=headers, params=params)
        data = res.json()
        atores.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return atores

# ── Airtable: salvar foto_count no registro ───────────────
def salvar_foto_count(record_id, count):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE}/{AIRTABLE_TABLE}/{record_id}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_KEY}",
        "Content-Type": "application/json"
    }
    res = requests.patch(url, headers=headers, json={"fields": {"foto_count": count}})
    if res.status_code not in (200, 201):
        print(f"  ⚠ Erro ao salvar no Airtable: {res.text}")

# ── HanCinema: contar fotos (com paginação) ───────────────
def get_photo_count(gallery_url):
    total = 0
    url = gallery_url
    pagina = 1

    while url:
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            if res.status_code != 200:
                print(f"  ⚠ Status {res.status_code} em {url}")
                return None

            soup = BeautifulSoup(res.text, "html.parser")

            # Seletor correto confirmado inspecionando o HTML real
            imgs = soup.select("ul.list.photo_list li img")
            total += len(imgs)

            # Verificar se tem próxima página
            next_link = soup.select_one("nav.navigation_button a[href*='p=']")
            if next_link and pagina < 50:  # limite de segurança: 50 páginas
                href = next_link.get("href", "")
                if href.startswith("http"):
                    url = href
                else:
                    from urllib.parse import urljoin
                    url = urljoin("https://www.hancinema.net/", href)
                pagina += 1
                time.sleep(1)  # respeitar o servidor entre páginas
            else:
                url = None

        except Exception as e:
            print(f"  ⚠ Erro ao acessar {url}: {e}")
            return None

    return total

# ── Email via Resend ──────────────────────────────────────
def send_email(updates):
    subject = f"📸 {len(updates)} ator(es) com fotos novas no HanCinema"
    body = "<h2>📸 Novas fotos detectadas no HanCinema</h2>\n<ul>\n"
    for nome, url, old_count, new_count in updates:
        diff = new_count - old_count if isinstance(old_count, int) else "?"
        body += (
            f'<li><strong>{nome}</strong> — '
            f'<a href="{url}">{url}</a> '
            f'({old_count} → {new_count} fotos, +{diff} nova(s))</li>\n'
        )
    body += f"</ul>\n<p><small>Verificado em {datetime.now().strftime('%d/%m/%Y às %H:%M')}</small></p>"

    res = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "from": "HanCinema Monitor <onboarding@resend.dev>",
            "to": [EMAIL_TO],
            "subject": subject,
            "html": body
        }
    )
    if res.status_code in (200, 201):
        print(f"✓ E-mail enviado com {len(updates)} atualizações!")
    else:
        print(f"✗ Erro ao enviar e-mail: {res.status_code} — {res.text}")

# ── Principal ─────────────────────────────────────────────
def main():
    print(f"Iniciando — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    atores = get_atores()
    print(f"Atores com URL HanCinema: {len(atores)}")

    updates = []

    for i, ator in enumerate(atores):
        nome      = ator["fields"].get("Nome", "Sem nome")
        url       = ator["fields"].get("Url Hancinema", "")
        old_count = ator["fields"].get("foto_count")  # None se ainda não foi registrado
        record_id = ator["id"]

        if not url:
            continue

        print(f"[{i+1}/{len(atores)}] {nome}...")
        new_count = get_photo_count(url)

        if new_count is None:
            print(f"  → Falha ao acessar, pulando.")
            continue

        print(f"  → {new_count} fotos encontradas (anterior: {old_count})")

        # Salvar sempre no Airtable (atualiza a memória)
        salvar_foto_count(record_id, new_count)

        if old_count is None:
            print(f"  → Primeiro registro salvo.")
        elif new_count != old_count:
            print(f"  → ATUALIZADO! {old_count} → {new_count}")
            updates.append((nome, url, old_count, new_count))

        # Pausa entre atores pra não sobrecarregar o HanCinema
        time.sleep(1.5)

    if updates:
        send_email(updates)
    else:
        print("Nenhuma atualização detectada.")

    print("Concluído!")

if __name__ == "__main__":
    main()
