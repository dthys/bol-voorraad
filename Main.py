import os
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from base64 import b64encode
from datetime import datetime

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
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="nl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Bol Voorraad</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-100 p-4 font-sans antialiased">
        <div class="max-w-md mx-auto bg-white rounded-xl shadow-md overflow-hidden p-6">
            <h1 class="text-2xl font-bold text-gray-800 mb-2 text-center">Voorraad Beheer</h1>
            <p class="text-center text-xs text-gray-500 mb-6">Laatste update: {tijd_nu}</p>
    """

    if error_msg:
        html_content += f"""
        <div class="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 mb-4">
            <p class="font-bold">Foutmelding tijdens ophalen</p>
            <p>{error_msg}</p>
        </div>"""
    else:
        html_content += '<div class="space-y-4">'
        for item in resultaten:
            is_low = item['status'] == "TE LAAG"
            bg_class = "bg-red-50 border-red-200" if is_low else "bg-green-50 border-green-200"
            text_class = "text-red-600" if is_low else "text-green-600"
            html_content += f"""
            <div class="p-4 rounded-lg border {bg_class}">
                <div class="flex justify-between items-center">
                    <div>
                        <h3 class="font-semibold text-gray-800 text-sm">{item['naam']}</h3>
                        <p class="text-xs text-gray-500">EAN: {item['ean']}</p>
                    </div>
                    <div class="text-right">
                        <span class="block text-2xl font-bold {text_class}">{item['voorraad']}</span>
                        <span class="text-xs uppercase font-bold {text_class}">{item['status']}</span>
                    </div>
                </div>
            </div>"""
        html_content += '</div>'

    html_content += """
        </div>
    </body>
    </html>
    """
    
    # Sla de gegenereerde HTML op in index.html
    with open("index.html", "w", encoding="utf-8") as file:
        file.write(html_content)

def main():
    resultaten = []
    error_bericht = ""
    try:
        token = get_bol_access_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.retailer.v10+json'
        }
        
        response = requests.get('https://api.bol.com/retailer/offers', headers=headers)
        if response.status_code != 200:
            raise Exception(f"Bol API Error: {response.text}")
            
        offers = response.json().get('offers', [])
        for offer in offers:
            ean = offer.get('ean')
            offer_detail_response = requests.get(f'https://api.bol.com/retailer/offers/{offer.get("offerId")}', headers=headers)
            if offer_detail_response.status_code == 200:
                detail = offer_detail_response.json()
                stock_amount = detail.get('stock', {}).get('amount', 0)
                product_naam = detail.get('referenceCode', ean)
                
                status = "OK"
                if stock_amount < MINIMUM_VOORRAAD:
                    status = "TE LAAG"
                    stuur_waarschuwings_mail(product_naam, ean, stock_amount)
                    
                resultaten.append({
                    'ean': ean,
                    'naam': product_naam,
                    'voorraad': stock_amount,
                    'status': status
                })
    except Exception as e:
        error_bericht = str(e)
        print(f"Fout: {error_bericht}")
        
    genereer_html(resultaten, error_bericht)

if __name__ == '__main__':
    main()