import os
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from base64 import b64encode
from datetime import datetime
import time
import csv
from io import StringIO

# ================= CONFIGURATIE VIA GITHUB SECRETS =================
BOL_CLIENT_ID = os.environ.get('BOL_CLIENT_ID')
BOL_CLIENT_SECRET = os.environ.get('BOL_CLIENT_SECRET')
EMAIL_SENDER = os.environ.get('EMAIL_SENDER')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
EMAIL_RECEIVER = os.environ.get('EMAIL_RECEIVER')

MINIMUM_VOORRAAD = 5
# ===================================================================

def get_bol_access_token():
    auth_string = f"{BOL_CLIENT_ID}:{BOL_CLIENT_SECRET}"
    base64_bytes = b64encode(auth_string.encode('ascii')).decode('ascii')
    headers = {
        'Authorization': f'Basic {base64_bytes}',
        'Accept': 'application/json'
    }
    response = requests.post('https://login.bol.com/token?grant_type=client_credentials', headers=headers)
    if response.status_code != 200:
        raise Exception(f"Fout bij Bol authenticatie: {response.text}")
    return response.json()['access_token']

def stuur_waarschuwings_mail(product_naam, ean, voorraad):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = f"Actie Vereist: Voorraad te laag voor {product_naam}"
    body = f"Beste beheerder,\n\nDit product is onder de minimum voorraad gekomen:\n\nProduct: {product_naam}\nEAN: {ean}\nHuidige voorraad: {voorraad}\n\nGroeten,\nJe GitHub Automatisering"
    msg.attach(MIMEText(body, 'plain'))
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        server.quit()
        print(f"Mail verstuurd voor {product_naam}")
    except Exception as e:
        print(f"Kon e-mail niet versturen: {e}")

def genereer_html(resultaten, error_msg=""):
    tijd_nu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    html_content = f"""<!DOCTYPE html><html lang="nl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Bol Voorraad</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-100 p-4 font-sans antialiased"><div class="max-w-md mx-auto bg-white rounded-xl shadow-md overflow-hidden p-6"><h1 class="text-2xl font-bold text-gray-800 mb-2 text-center">Voorraad Beheer</h1><p class="text-center text-xs text-gray-500 mb-6">Laatste update: {tijd_nu}</p>"""
    if error_msg:
        html_content += f"""<div class="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 mb-4"><p class="font-bold">Foutmelding</p><p>{error_msg}</p></div>"""
    else:
        html_content += '<div class="space-y-4">'
        for item in resultaten:
            is_low = item['status'] == "TE LAAG"
            bg_class = "bg-red-50 border-red-200" if is_low else "bg-green-50 border-green-200"
            text_class = "text-red-600" if is_low else "text-green-600"
            html_content += f"""<div class="p-4 rounded-lg border {bg_class}"><div class="flex justify-between items-center"><div><h3 class="font-semibold text-gray-800 text-sm">{item['naam']}</h3><p class="text-xs text-gray-500">EAN: {item['ean']}</p></div><div class="text-right"><span class="block text-2xl font-bold {text_class}">{item['voorraad']}</span><span class="text-xs uppercase font-bold {text_class}">{item['status']}</span></div></div></div>"""
        html_content += '</div>'
    html_content += "</div></body></html>"
    with open("index.html", "w", encoding="utf-8") as file:
        file.write(html_content)

def main():
    resultaten = []
    error_bericht = ""
    try:
        token = get_bol_access_token()
        headers_json = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.retailer.v10+json',
            'Content-Type': 'application/vnd.retailer.v10+json'
        }
        
        # 1. Export aanvragen
        export_payload = {"format": "CSV"}
        export_response = requests.post('https://api.bol.com/retailer/offers/export', headers=headers_json, json=export_payload)
        
        if export_response.status_code != 202:
            raise Exception(f"Fout bij aanvragen export: {export_response.text}")
            
        process_data = export_response.json()
        process_id = process_data.get('processStatusId')
        entity_id = process_data.get('entityId')
        
        # 2. Wachten tot Bol de lijst klaar heeft
        status = "PENDING"
        pogingen = 0
        while status == "PENDING" and pogingen < 20:
            time.sleep(15) # Wacht 15 seconden per keer
            pogingen += 1
            status_response = requests.get(f'https://api.bol.com/retailer/process-status/{process_id}', headers=headers_json)
            if status_response.status_code == 200:
                status = status_response.json().get('status')
            else:
                raise Exception(f"Fout bij controleren status: {status_response.text}")
                
        if status != "SUCCESS":
            raise Exception(f"Bol is te langzaam met de export of faalde. Status: {status}")
            
        # 3. Downloaden van de CSV
        headers_csv = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.retailer.v10+csv'
        }
        download_response = requests.get(f'https://api.bol.com/retailer/offers/export/{entity_id}', headers=headers_csv)
        
        if download_response.status_code != 200:
            raise Exception(f"Fout bij downloaden CSV: {download_response.text}")
            
        # 4. CSV inlezen en voorraad controleren
        csv_data = download_response.text
        reader = csv.DictReader(StringIO(csv_data))
        
        for row in reader:
            # We strippen spaties rondom de kolomnamen voor de zekerheid
            clean_row = {k.strip(): v for k, v in row.items()}
            
            ean = clean_row.get('ean', 'Onbekend')
            product_naam = clean_row.get('referenceCode', '')
            if not product_naam:
                product_naam = f"Product EAN: {ean}"
                
            try:
                stock_amount = int(clean_row.get('stockAmount', 0))
            except ValueError:
                stock_amount = 0
                
            status_text = "OK"
            if stock_amount < MINIMUM_VOORRAAD:
                status_text = "TE LAAG"
                stuur_waarschuwings_mail(product_naam, ean, stock_amount)
                
            resultaten.append({
                'ean': ean,
                'naam': product_naam,
                'voorraad': stock_amount,
                'status': status_text
            })
            
    except Exception as e:
        error_bericht = str(e)
        print(f"Fout: {error_bericht}")
        
    genereer_html(resultaten, error_bericht)

if __name__ == '__main__':
    main()
