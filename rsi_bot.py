import os
import requests
import pandas as pd

# Configuration de l'API CryptoCompare
api_key = os.environ["CRYPTOCOMPARE_API_KEY"]
headers = {"authorization": f"Apikey {api_key}"}

# Configuration de Telegram
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# Fonction pour envoyer un message sur Telegram
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    requests.post(url, data=payload)

# Fonction pour récupérer les prix actuels
def fetch_current_prices(crypto_symbols):
    url = "https://min-api.cryptocompare.com/data/pricemulti"
    params = {"fsyms": ",".join(crypto_symbols), "tsyms": "USD"}
    response = requests.get(url, headers=headers, params=params)
    return response.json()

# Fonction pour récupérer les données historiques
def fetch_historical_data(symbol, limit=100):
    url = "https://min-api.cryptocompare.com/data/v2/histohour"
    params = {"fsym": symbol, "tsym": "USD", "limit": limit}
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    return [entry["close"] for entry in data["Data"]["Data"]] if "Data" in data else None

# Fonction pour calculer le RSI
def calculate_rsi(prices, period=14):
    data = pd.Series(prices)
    delta = data.diff(1)
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# Fonction principale pour afficher les infos et RSI
def display_rsi(cryptos_to_check):
    current_prices = fetch_current_prices(cryptos_to_check)
    message = ""

    for symbol in cryptos_to_check:
        if symbol not in current_prices:
            message += f"{symbol} n'est pas disponible sur CryptoCompare.\n"
            continue
        
        price = current_prices[symbol]["USD"]
        message += f"\nCrypto : {symbol}\n"
        message += f"Prix actuel : ${price:.6f}\n"
        
        # Récupérer les données historiques
        historical_prices = fetch_historical_data(symbol, 100)
        if not historical_prices:
            message += f"Pas de données historiques pour {symbol}.\n"
            continue
        
        # Calcul du RSI
        rsi_values = calculate_rsi(historical_prices)
        latest_rsi = rsi_values.iloc[-1]
        message += f"RSI : {latest_rsi:.2f}\n"
        
        # Interprétation RSI
        if latest_rsi > 70:
            message += f"{symbol} : 🚨 Surachat - Vous pourriez envisager de vendre.\n"
        elif latest_rsi < 30:
            message += f"{symbol} : 📉 Survente - Vous pourriez envisager d'acheter.\n"
        else:
            message += f"{symbol} : 📊 Zone neutre.\n"
    
    # Envoyer le message à Telegram
    send_telegram_message(message)

if __name__ == "__main__":
    cryptos_to_check = ["BTC", "APE", "trump"]  # Liste des cryptos à suivre
    display_rsi([crypto.upper().strip() for crypto in cryptos_to_check])
