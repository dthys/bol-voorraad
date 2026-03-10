import os
import requests
import json
from base64 import b64encode
from datetime import datetime

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

def update_jsonbin_data(data):
    if not JSONBIN_BIN_ID or not JSONBIN_API_KEY:
        return
    url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
    headers = {'Content-Type': 'application/json', 'X-Master-Key': JSONBIN_API_KEY}
    try:
        requests.put(url, headers=headers, json=data)
    except Exception as e:
        print(f"Error update database: {e}")

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
    
    bin_id_veilig = JSONBIN_BIN_ID if JSONBIN_BIN_ID else "ONTBREEKT"
    api_key_veilig = JSONBIN_API_KEY if JSONBIN_API_KEY else "ONTBREEKT"

    html = f"""<!DOCTYPE html><html lang="nl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Bol LVB Voorraad</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-100 p-4 font-sans antialiased"><div class="max-w-md mx-auto bg-white rounded-xl shadow-md overflow-hidden p-6"><h1 class="text-2xl font-bold text-gray-800 mb-2 text-center">Voorraad & Instellingen</h1><p class="text-center text-xs text-gray-500 mb-6">Laatste automatische check: {tijd_nu}</p>"""
    
    if bin_id_veilig == "ONTBREEKT":
        html += """<div class="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 mb-4"><p class="font-bold">⚠️ Systeemfout</p><p>De JSONBin sleutels ontbreken!</p></div>"""

    if error_msg:
        html += f"""<div class="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 mb-4"><p class="font-bold">Foutmelding</p><p>{error_msg}</p></div>"""
    else:
        if len(resultaten) == 0:
            html += """<div class="bg-blue-100 border-l-4 border-blue-500 text-blue-700 p-4 mb-4"><p class="font-bold">Geen LVB Voorraad</p><p>Bol.com zegt dat er momenteel geen producten in het LVB magazijn liggen.</p></div>"""
        
        html += '<div class="space-y-4 mb-6">'
        for item in resultaten:
            is_low = item['voorraad'] < item['min_voorraad']
            is_onderweg = item['onderweg']
            
            # Kleuren bepalen op basis van de status
            if is_low and not is_onderweg:
                bg = "bg-red-50 border-red-200"
                text_c = "text-red-600"
            elif is_low and is_onderweg:
                bg = "bg-orange-50 border-orange-200"
                text_c = "text-orange-500"
            else:
                bg = "bg-gray-50 border-gray-200"
                text_c = "text-green-600"
                
            safe_title = item['naam'].replace('"', '&quot;')
            checked = "checked" if is_onderweg else ""
            
            html += f"""
            <div class="p-4 rounded-lg border {bg}">
                <div class="flex flex-col mb-2">
                    <h3 class="font-semibold text-gray-800 text-sm">{item['naam']}</h3>
                    <p class="text-xs text-gray-500">EAN: {item['ean']}</p>
                </div>
                <div class="flex justify-between items-center bg-white p-2 rounded border mb-2">
                    <div class="text-sm text-gray-600 flex items-center">
                        Min: <input type="number" class="voorraad-input ml-2 w-16 p-1 border rounded text-center font-bold" data-ean="{item['ean']}" data-title="{safe_title}" value="{item['min_voorraad']}">
                    </div>
                    <div class="text-right">
                        <span class="block text-xl font-bold {text_c}">{item['voorraad']} <span class="text-xs font-normal text-gray-500">stuks</span></span>
                    </div>
                </div>
                <div class="flex items-center bg-white p-2 rounded border border-gray-200">
                    <input type="checkbox" id="chk_{item['ean']}" class="onderweg-checkbox w-5 h-5 text-blue-600 rounded border-gray-300 focus:ring-blue-500" data-ean="{item['ean']}" {checked}>
                    <label for="chk_{item['ean']}" class="ml-2 text-sm text-gray-700 font-medium cursor-pointer">Voorraad verstuurd (Mute melding)</label>
                </div>
            </div>"""
        html += '</div>'
        
        html += f"""
        <button id="saveBtn" onclick="saveAll()" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-4 rounded-lg transition duration-300 shadow-md">
            Instellingen Opslaan
        </button>
        <script>
        async function saveAll() {{
            const btn = document.getElementById('saveBtn');
            const binId = '{bin_id_veilig}';
            
            if (binId === 'ONTBREEKT') return alert('Fout: Sleutels ontbreken.');

            btn.innerText = 'Bezig met opslaan...';
            btn.disabled = true;

            let newData = {{ "_systeem": "actief" }};
            document.querySelectorAll('.voorraad-input').forEach(input => {{
                const ean = input.getAttribute('data-ean');
                const chk = document.querySelector(`.onderweg-checkbox[data-ean="${{ean}}"]`);
                
                newData[ean] = {{ 
                    "titel": input.getAttribute('data-title'), 
                    "min_voorraad": parseInt(input.value),
                    "onderweg": chk ? chk.checked : false
                }};
            }});

            try {{
                const r = await fetch('https://api.jsonbin.io/v3/b/' + binId, {{
                    method: 'PUT',
                    headers: {{ 'Content-Type': 'application/json', 'X-Master-Key': '{api_key_veilig}' }},
                    body: JSON.stringify(newData)
                }});
                if(r.ok) {{
                    btn.innerText = '✅ Instellingen Opgeslagen!';
                    btn.classList.replace('bg-blue-600', 'bg-green-600');
                    setTimeout(() => {{
                        btn.innerText = 'Instellingen Opslaan';
                        btn.disabled = false;
                        btn.classList.replace('bg-green-600', 'bg-blue-600');
                    }}, 3000);
                }} else throw new Error('Mislukt');
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
        opgeslagen_instellingen = get_jsonbin_data()
        needs_db_update = False # Houdt bij of Python iets automatisch moet uitvinken
        
        token = get_bol_access_token()
        headers_json = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.retailer.v10+json'
        }
        
        inventory_items = []
        page = 1
        while True:
            inv_url = f'https://api.bol.com/retailer/inventory?page={page}'
            inv_res = requests.get(inv_url, headers=headers_json)
            
            if inv_res.status_code != 200:
                raise Exception(f"Fout bij ophalen LVB inventory: {inv_res.text}")
                
            data = inv_res.json()
            items = data.get('inventory', [])
            
            if not items:
                break
                
            inventory_items.extend(items)
            page += 1
            
        for item in inventory_items:
            ean = item.get('ean', 'Onbekend')
            bol_titel = item.get('title', f"Product EAN: {ean}")
            stock_amount = item.get('regularStock', 0)
            
            # Haal instellingen op uit de database
            eigen_info = opgeslagen_instellingen.get(ean, {})
            product_naam = eigen_info.get('titel', bol_titel)
            min_voorraad = int(eigen_info.get('min_voorraad', STANDAARD_MIN_VOORRAAD))
            onderweg = bool(eigen_info.get('onderweg', False))
            
            # SLIMME LOGICA: Als het vinkje aan staat, maar de voorraad is weer aangevuld!
            if stock_amount >= min_voorraad and onderweg:
                onderweg = False
                eigen_info['onderweg'] = False
                needs_db_update = True # Geef door dat Python de database moet updaten
                
            # Controleer of we Telegram moeten sturen
            if stock_amount < min_voorraad:
                if not onderweg:
                    stuur_waarschuwings_telegram(product_naam, ean, stock_amount, min_voorraad)
                    
            # Update de data voor in het geheugen
            eigen_info['titel'] = product_naam
            eigen_info['min_voorraad'] = min_voorraad
            eigen_info['onderweg'] = onderweg
            opgeslagen_instellingen[ean] = eigen_info
                
            resultaten.append({
                'ean': ean,
                'naam': product_naam,
                'voorraad': stock_amount,
                'min_voorraad': min_voorraad,
                'onderweg': onderweg
            })
            
        # Als het script automatisch een vinkje heeft weggehaald, schrijven we dit terug naar de database!
        if needs_db_update:
            update_jsonbin_data(opgeslagen_instellingen)
            
    except Exception as e:
        error_bericht = str(e)
        print(f"Fout: {error_bericht}")
        
    genereer_html(resultaten, error_bericht)

if __name__ == '__main__':
    main()
