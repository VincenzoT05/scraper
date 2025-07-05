import csv
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# === SETUP SELENIUM ===
options = Options()
options.headless = True
driver = webdriver.Chrome(options=options)

def estrai_info_dettaglio(link):
    driver.get(link)
    time.sleep(2)

    data = {
        "Nome": "",
        "Link": link,
        "Indirizzo": "",
        "Telefono": "",
        "Email": "",
        "Sito web": ""
    }

    # Nome
    try:
        nome = driver.find_element(By.CSS_SELECTOR, ".info-box-content h4 a").text.strip()
        data["Nome"] = nome
    except:
        pass

    # Contatti
    try:
        box = driver.find_element(By.CLASS_NAME, "box-body")
        righe = box.find_elements(By.TAG_NAME, "p")
        for r in righe:
            txt = r.text.strip()
            if "@" in txt:
                data["Email"] = txt
            elif txt.lower().startswith("http"):
                data["Sito web"] = txt
            elif txt.replace(" ", "").replace("+", "").isdigit():
                data["Telefono"] = txt
            else:
                data["Indirizzo"] = txt
    except:
        pass

    print(f"✅ Estratto: {data['Nome']}")
    return data

def estrai_tutti():
    results = []
    page = 1

    while True:
        url = f"https://catalogo.fiereparma.it/manifestazione/cibus-2024/?pag={page}"
        print(f"🌐 Carico pagina {page}...")
        driver.get(url)
        time.sleep(2)

        link_elements = driver.find_elements(By.CSS_SELECTOR, ".info-box-content h4 a")
        if not link_elements:
            print("❌ Fine elenco.")
            break

        # PRENDIAMO I LINK PRIMA di visitarli
        links = [a.get_attribute("href") for a in link_elements]

        for href in links:
            dati = estrai_info_dettaglio(href)
            results.append(dati)
            time.sleep(1)

        page += 1

    return results

def salva_csv(data):
    keys = ["Nome", "Link", "Indirizzo", "Telefono", "Email", "Sito web"]
    with open("espositori_completi.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)

def main():
    try:
        print("🔍 Avvio scraping espositori CIBUS 2024...")
        tutti_dati = estrai_tutti()
        salva_csv(tutti_dati)
        print(f"✅ Completato! Salvati {len(tutti_dati)} espositori in espositori_completi.csv")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
