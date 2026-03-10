import os
import requests
import json
from base64 import b64encode
from datetime import datetime
import time
import csv
from io import StringIO

# ================= CONFIGURATIE VIA GITHUB SECRETS =================
BOL_CLIENT_ID = os.environ.get('BOL_CLIENT_ID')
BOL_CLIENT_SECRET = os.environ.get('BOL_CLIENT_SECRET')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
JSONBIN_BIN_ID = os.environ.get('JSONBIN_BIN_ID')
JSONBIN_API_KEY = os.environ.get('JSONBIN_API_KEY')

STANDAARD_MIN_VOORRAAD = 5
# ===================================================================

def get_bol_access_token():
    auth_string = f"{BOL_CLIENT_ID}:{BOL_CLIENT_SECRET}"
    base64_bytes = b64encode(auth_string.encode('ascii')).decode('ascii')
    headers = {'Authorization': f'Basic {base64_bytes}', 'Accept': 'application/json'}
    response = requests.post('https://login.bol.com/token?grant_type=client_credentials', headers=headers)
    if response.status_code != 200:
        raise Exception(f"Fout bij Bol authenticatie: {response.text}")
    return response.json()['access_token']

def get_jsonbin_data():
    if not JSONBIN_BIN_ID or not JSONBIN_API_KEY:
        return {}
    url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
    headers = {'X-Master-Key': JSONBIN_API_KEY}
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            return r.json().get('record', {})
    except Exception as e:
        print(f"Error lezen database: {e}")
    return {}

def stuur_waarschuwings_telegram(product_naam, ean, voorraad, min_voorraad):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    bericht = f"🚨 *Voorraad Waarschuwing!*\n\nDit product moet bijbesteld worden:\n📦 *Product:* {product_naam}\n🔖 *EAN:* {ean}\n📉 *LVB Voorraad:* {voorraad} stuks (Drempel: {min_voorraad})"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": bericht, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception:
        pass

def genereer_html(resultaten, error_msg=""):
    tijd_nu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    html = f"""<!DOCTYPE html><html lang="nl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Bol LVB Voorraad</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-100 p-4 font-sans antialiased"><div class="max-w-md mx-auto bg-white rounded-xl shadow-md overflow-hidden p-6"><h1 class="text-2xl font-bold text-gray-800 mb-2 text-center">Voorraad & Instellingen</h1><p class="text-center text-xs text-gray-500 mb-6">Laatste Bol check: {tijd_nu}</p>"""
    
    if error_msg:
        html += f"""<div class="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 mb-4"><p class="font-bold">Fout</p><p>{error_msg}</p></div>"""
    else:
        html += '<div class="space-y-4 mb-6">'
        for item in resultaten:
            is_low = item['status'] == "TE LAAG"
            bg = "bg-red-50 border-red-200" if is_low else "bg-gray-50 border-gray-200"
            text_c = "text-red-600" if is_low else "text-green-600"
            safe_title = item['naam'].replace('"', '&quot;')
            
            html += f"""
            <div class="p-4 rounded-lg border {bg}">
                <div class="flex flex-col mb-2">
                    <h3 class="font-semibold text-gray-800 text-sm">{item['naam']}</h3>
                    <p class="text-xs text-gray-500">EAN: {item['ean']}</p>
                </div>
                <div class="flex justify-between items-center bg-white p-2 rounded border">
                    <div class="text-sm text-gray-600 flex items-center">
                        Minimaal: <input type="number" class="voorraad-input ml-2 w-16 p-1 border rounded text-center font-bold" data-ean="{item['ean']}" data-title="{safe_title}" value="{item['min_voorraad']}">
                    </div>
                    <div class="text-right">
                        <span class="block text-xl font-bold {text_c}">{item['voorraad']} <span class="text-xs font-normal text-gray-500">op voorraad</span></span>
                    </div>
                </div>
            </div>"""
        html += '</div>'
        
        # De JavaScript die jouw UI koppelt aan de Database
        html += f"""
        <button id="saveBtn" onclick="saveAll()" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-4 rounded-lg transition duration-300 shadow-md">
            Instellingen Opslaan
        </button>
        <script>
        async function saveAll() {{
            const btn = document.getElementById('saveBtn');
            btn.innerText = 'Bezig met opslaan...';
            btn.disabled = true;

            const inputs = document.querySelectorAll('.voorraad-input');
            let newData = {{}};

            inputs.forEach(input => {{
                const ean = input.getAttribute('data-ean');
                const val = parseInt(input.value);
                const title = input.getAttribute('data-title');
                newData[ean] = {{ "titel": title, "min_voorraad": val }};
            }});

            try {{
                const response = await fetch('https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}', {{
                    method: 'PUT',
                    headers: {{ 'Content-Type': 'application/json', 'X-Master-Key': '{JSONBIN_API_KEY}' }},
                    body: JSON.stringify(newData)
                }});
                if(response.ok) {{
                    btn.innerText = '✅ Instellingen Opgeslagen!';
                    btn.classList.replace('bg-blue-600', 'bg-green-600');
                    setTimeout(() => {{
                        btn.innerText = 'Instellingen Opslaan';
                        btn.disabled = false;
                        btn.classList.replace('bg-green-600', 'bg-blue-600');
                    }}, 3000);
                }} else {{ throw new Error('Mislukt'); }}
            }} catch (error) {{
                alert('Fout bij opslaan! Controleer je verbinding.');
                btn.innerText = 'Instellingen Opslaan';
                btn.disabled = false;
            }}
        }}
        </script>
        """
    html += "</div></body></html>"
    with open("index.html", "w", encoding="utf-8") as file:
        file.write(html)

def main():
    resultaten = []
    error_bericht = ""
    try:
        # Haal eerst jouw opgeslagen instellingen op uit de database
        opgeslagen_instellingen = get_jsonbin_data()
        
        token = get_bol_access_token()
        headers_json = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.retailer.v10+json',
            'Content-Type': 'application/vnd.retailer.v10+json'
        }
        
        export_payload = {"format": "CSV"}
        export_response = requests.post('https://api.bol.com/retailer/offers/export', headers=headers_json, json=export_payload)
        
        if export_response.status_code != 202:
            raise Exception(f"Fout bij aanvragen export: {export_response.text}")
            
        process_data = export_response.json()
        process_id = process_data.get('processStatusId')
        
        status = "PENDING"
        entity_id = None
        pogingen = 0
        while status == "PENDING" and pogingen < 20:
            time.sleep(15)
            pogingen += 1
            status_response = requests.get(f'https://api.bol.com/shared/process-status/{process_id}', headers=headers_json)
            if status_response.status_code == 200:
                status_data = status_response.json()
                status = status_data.get('status')
                if status == "SUCCESS":
                    entity_id = status_data.get('entityId')
            else:
                raise Exception(f"Fout bij controleren status: {status_response.text}")
                
        if status != "SUCCESS" or not entity_id:
            raise Exception(f"Bol is te langzaam of faalde. Status: {status}")
            
        headers_csv = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.retailer.v10+csv'
        }
        download_response = requests.get(f'https://api.bol.com/retailer/offers/export/{entity_id}', headers=headers_csv)
        
        if download_response.status_code != 200:
            raise Exception(f"Fout bij downloaden CSV: {download_response.text}")
            
        csv_data = download_response.text
        reader = csv.DictReader(StringIO(csv_data))
        
        for row in reader:
            clean_row = {k.strip(): v for k, v in row.items()}
            
            # Alleen LVB producten
            if clean_row.get('fulfillmentVia') != 'FBB':
                continue
            
            ean = clean_row.get('ean', 'Onbekend')
            
            # Kijk of dit product al in jouw database instellingen staat
            eigen_info = opgeslagen_instellingen.get(ean)
            if eigen_info:
                product_naam = eigen_info.get('titel', clean_row.get('referenceCode', f"Product EAN: {ean}"))
                min_voorraad = int(eigen_info.get('min_voorraad', STANDAARD_MIN_VOORRAAD))
            else:
                product_naam = clean_row.get('referenceCode', f"Product EAN: {ean}")
                min_voorraad = STANDAARD_MIN_VOORRAAD
                
            try:
                stock_amount = int(clean_row.get('stockAmount', 0))
            except ValueError:
                stock_amount = 0
                
            status_text = "OK"
            if stock_amount < min_voorraad:
                status_text = "TE LAAG"
                stuur_waarschuwings_telegram(product_naam, ean, stock_amount, min_voorraad)
                
            resultaten.append({
                'ean': ean,
                'naam': product_naam,
                'voorraad': stock_amount,
                'min_voorraad': min_voorraad,
                'status': status_text
            })
            
    except Exception as e:
        error_bericht = str(e)
        print(f"Fout: {error_bericht}")
        
    genereer_html(resultaten, error_bericht)

if __name__ == '__main__':
    main()
