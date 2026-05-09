import os
import json
import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime

AIRTABLE_KEY = os.environ['AIRTABLE_KEY']
AIRTABLE_BASE = os.environ['AIRTABLE_BASE']
AIRTABLE_TABLE = os.environ['AIRTABLE_TABLE']
RESEND_API_KEY = os.environ['RESEND_API_KEY']
EMAIL_TO = os.environ['EMAIL_TO']

STATE_FILE = 'hancinema_state.json'

def get_atores():
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE}/{AIRTABLE_TABLE}"
    headers = {"Authorization": f"Bearer {AIRTABLE_KEY}"}
    params = {
        "fields[]": ["Nome", "Url Hancinema"],
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

def get_photo_count(gallery_url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        res = requests.get(gallery_url, headers=headers, timeout=15)
        if res.status_code != 200:
            return None
        soup = BeautifulSoup(res.text, "html.parser")
        imgs = soup.select(".gallery img, .photo-gallery img, #gallery img, .pictures img")
        if not imgs:
            section = soup.find("div", class_=lambda c: c and "gallery" in c.lower())
            if section:
                return hashlib.md5(section.get_text().encode()).hexdigest()
        return len(imgs)
    except Exception as e:
        print(f"Erro ao acessar {gallery_url}: {e}")
        return None

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def send_email(updates):
    subject = f"📸 {len(updates)} ator(es) com fotos novas no HanCinema"
    body = "<h2>📸 Novas fotos detectadas no HanCinema</h2>\n<ul>\n"
    for nome, url, old_count, new_count in updates:
        body += f'<li><strong>{nome}</strong> — <a href="{url}">{url}</a>'
        if isinstance(old_count, int) and isinstance(new_count, int):
            body += f" ({old_count} → {new_count} fotos)"
        body += "</li>\n"
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
    if res.status_code == 200:
        print(f"E-mail enviado com {len(updates)} atualizações!")
    else:
        print(f"Erro ao enviar e-mail: {res.text}")

def main():
    print(f"Iniciando — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    atores = get_atores()
    print(f"Atores com URL HanCinema: {len(atores)}")
    state = load_state()
    updates = []
    new_state = {}

    for i, ator in enumerate(atores):
        nome = ator["fields"].get("Nome", "Sem nome")
        url = ator["fields"].get("Url Hancinema", "")
        if not url:
            continue
        print(f"[{i+1}/{len(atores)}] {nome}...")
        count = get_photo_count(url)
        if count is None:
            new_state[url] = state.get(url)
            continue
        new_state[url] = count
        old_count = state.get(url)
        if old_count is not None and old_count != count:
            print(f"  → ATUALIZADO! {old_count} → {count}")
            updates.append((nome, url, old_count, count))
        elif old_count is None:
            print(f"  → Primeiro registro: {count}")

    save_state(new_state)
    if updates:
        send_email(updates)
    else:
        print("Nenhuma atualização encontrada.")
    print("Concluído!")

if __name__ == "__main__":
    main()
