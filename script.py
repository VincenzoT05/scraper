import requests
from bs4 import BeautifulSoup
import csv
import time

def estrai_info_pagina_dettaglio(url):
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        box = soup.select_one('.box-body .list-group')
        indirizzo = telefono = email = sito_web = ""
        if box:
            blocchi = box.find_all('p')
            for p in blocchi:
                testo = p.get_text(strip=True)
                if not testo:
                    a = p.find('a')
                    if a:
                        testo = a.get_text(strip=True)
                if "@" in testo:
                    email = testo
                elif "http" in testo:
                    sito_web = testo
                elif p.find('a', href=lambda x: x and x.startswith('tel:')):
                    telefono = testo
                elif not indirizzo:
                    indirizzo = testo

        return indirizzo, telefono, email, sito_web

    except Exception as e:
        print(f"❌ Errore su {url}: {e}")
        return "", "", "", ""

def estrai_espositori_da_pagina(numero_pagina):
    url = f'https://catalogo.fiereparma.it/manifestazione/cibus-2024/?pag={numero_pagina}'
    print(f"\n📄 Scansione pagina {numero_pagina}: {url}")
    response = requests.get(url)
    if response.status_code == 404:
        return None
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')
    espositori = []

    for box in soup.select('.info-box'):
        nome_tag = box.select_one('h4 a')
        if nome_tag:
            nome = nome_tag.get_text(strip=True)
            link = nome_tag['href']
            espositori.append((nome, link))

    return espositori if espositori else None

if __name__ == "__main__":
    pagina = 1
    file_output = 'espositori_cibus2024_completo.csv'
    with open(file_output, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Nome Espositore', 'Link', 'Indirizzo', 'Telefono', 'Email', 'Sito Web'])
        while True:
            espositori = estrai_espositori_da_pagina(pagina)
            if not espositori:
                print("\n✅ Nessuna altra pagina da analizzare. Fine.")
                break
            for count, (nome, link) in enumerate(espositori, start=1):
                print(f"🔍 [{nome}] → {link}")
                indirizzo, telefono, email, sito = estrai_info_pagina_dettaglio(link)
                writer.writerow([nome, link, indirizzo, telefono, email, sito])
                print("⏳ Attesa 60 secondi prima del prossimo espositore...")
                time.sleep(60)

            pagina += 1
            print("➡️ Passo alla pagina successiva...")
            time.sleep(5)
    print(f"\n✅ File CSV completo salvato in: {file_output}")
