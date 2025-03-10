import os
import requests
import pandas as pd
import json
from datetime import datetime

# Configuration API
api_key = os.environ["CRYPTOCOMPARE_API_KEY"]
headers = {"authorization": f"Apikey {api_key}"}
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# ================= FONCTIONS DE GESTION =================
def load_tracked_cryptos():
    try:
        with open("tracked_cryptos.json", "r") as f:
            return json.load(f).get("cryptos", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_tracked_cryptos(cryptos):
    with open("tracked_cryptos.json", "w") as f:
        json.dump({"cryptos": cryptos}, f)

def load_last_update_id():
    try:
        with open("last_update_id.txt", "r") as f:
            return int(f.read().strip())
    except FileNotFoundError:
        return 0

def save_last_update_id(update_id):
    with open("last_update_id.txt", "w") as f:
        f.write(str(update_id))

# Communication Telegram
def send_telegram_message(message, chat_id=CHAT_ID):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": message})

def get_telegram_updates(last_update_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    return requests.get(url, params={"offset": last_update_id + 1}).json()

def process_telegram_commands():
    last_update_id = load_last_update_id()
    updates = get_telegram_updates(last_update_id)
    new_update_id = last_update_id

    cryptos = load_tracked_cryptos()
    modified = False

    for update in updates.get("result", []):
        message = update.get("message", {})
        text = message.get("text", "")
        chat_id = str(message.get("chat", {}).get("id"))

        if chat_id != CHAT_ID or not text:
            continue

        new_update_id = max(new_update_id, update["update_id"])
        parts = text.split()
        command = parts[0].lower()

        if command == "/add" and len(parts) > 1:
            crypto = parts[1].upper().strip()
            if crypto not in cryptos and len(cryptos) < 4:  # Limite de 4 cryptos
                cryptos.append(crypto)
                send_telegram_message(f"✅ {crypto} ajouté à la liste.", chat_id)
                modified = True
        elif command == "/remove" and len(parts) > 1:
            crypto = parts[1].upper().strip()
            if crypto in cryptos:
                cryptos.remove(crypto)
                send_telegram_message(f"❌ {crypto} retiré de la liste.", chat_id)
                modified = True
        elif command == "/list":
            send_telegram_message(f"📊 Cryptos suivies : {', '.join(cryptos) if cryptos else 'Aucune'}", chat_id)

    if modified:
        save_tracked_cryptos(cryptos)
    save_last_update_id(new_update_id)

# ================= FONCTIONS D'ANALYSE =================
def fetch_current_prices(symbols):
    url = "https://min-api.cryptocompare.com/data/pricemulti"
    response = requests.get(url, headers=headers, params={"fsyms": ",".join(symbols), "tsyms": "USD"})
    return response.json() if response.status_code == 200 else {}

def fetch_historical_data(symbol, limit=200):
    url = "https://min-api.cryptocompare.com/data/v2/histohour"
    params = {"fsym": symbol, "tsym": "USD", "limit": limit}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        return None
    data = response.json().get("Data", {}).get("Data", [])
    return {
        "prices": [entry["close"] for entry in data],
        "volumes": [entry["volumeto"] for entry in data]
    }

def calculate_rsi(prices, period=14):
    delta = pd.Series(prices).diff().dropna()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, 1)  # Évite division par zéro
    return 100 - (100 / (1 + rs))

def calculate_sma(prices, window=50):
    return pd.Series(prices).rolling(window).mean()

def calculate_macd(prices, fast=12, slow=26, signal=9):
    prices_series = pd.Series(prices)
    ema_fast = prices_series.ewm(span=fast, adjust=False).mean()
    ema_slow = prices_series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line

def analyze_volume(volumes, window=14):
    if len(volumes) < window:
        return False
    avg_volume = pd.Series(volumes).rolling(window).mean().iloc[-1]
    current_volume = volumes[-1]
    return current_volume > avg_volume * 1.75 and current_volume > 1_000_000

# ================= SIGNAL D'ACHAT/VENTE =================
def generate_signals(symbol):
    data = fetch_historical_data(symbol)
    if not data:
        return None
        
    prices = data["prices"]
    volumes = data["volumes"]
    
    # Calcul des indicateurs
    rsi = calculate_rsi(prices).iloc[-1]
    sma = calculate_sma(prices).iloc[-1]
    macd_line, signal_line = calculate_macd(prices)
    volume_alert = analyze_volume(volumes)
    
    # Conditions individuelles pour l'achat
    buy_conditions = [
        rsi < 30,
        prices[-1] > sma,
        macd_line.iloc[-1] > signal_line.iloc[-1],
        volume_alert
    ]

    # Conditions individuelles pour la vente
    sell_conditions = [
        rsi > 70,
        prices[-1] < sma,
        macd_line.iloc[-1] < signal_line.iloc[-1],
        volume_alert
    ]

    # Génération des signaux : au moins 3 conditions doivent être vraies
    buy_signal = sum(buy_conditions) >= 3
    sell_signal = sum(sell_conditions) >= 3

    
    return {
        "price": prices[-1],
        "rsi": rsi,
        "sma": sma,
        "macd_diff": macd_line.iloc[-1] - signal_line.iloc[-1],
        "volume_alert": volume_alert,
        "buy_signal": buy_signal,
        "sell_signal": sell_signal
    }

# ================= RAPPORT TELEGRAM =================
def send_analysis_report():
    cryptos = load_tracked_cryptos()
    if not cryptos:
        send_telegram_message("⚠️ Aucune crypto suivie. Utilisez /add <symbole>")
        return
    
    message = f"📊 Rapport à {datetime.now().strftime('%H:%M')}:\n\n"
    
    for symbol in cryptos:
        signals = generate_signals(symbol)
        if not signals:
            message += f"⚠️ {symbol} : Données indisponibles\n"
            continue
            
        # Construction du message
        if signals["buy_signal"]:
            message += (
                f"🚀 **ACHAT {symbol}**\n"
                f"- Prix: ${signals['price']:.6f} (SMA50: ${signals['sma']:.6f})\n"
                f"- RSI: {signals['rsi']:.1f} (<30/70)\n"
                f"- MACD: {signals['macd_diff']:.4f} ↑\n"
                f"- Volume: 🔥\n\n"
            )
        elif signals["sell_signal"]:
            message += (
                f"🔻 **VENTE {symbol}**\n"
                f"- Prix: ${signals['price']:.6f} (SMA50: ${signals['sma']:.6f})\n"
                f"- RSI: {signals['rsi']:.1f} (<30/70)\n"
                f"- MACD: {signals['macd_diff']:.4f} ↓\n"
                f"- Volume: 💨\n\n"
            )
        else:
            message += (
                f"• {symbol} : ${signals['price']:.6f}\n"
                f"  RSI: {signals['rsi']:.1f} | MACD: {signals['macd_diff']:.4f}\n"
                f"  Volume: {'🔥' if signals['volume_alert'] else '⏳'}\n\n"
            )
    
    send_telegram_message(message)

# ================= EXECUTION PRINCIPALE =================
if __name__ == "__main__":
    process_telegram_commands() 
    send_analysis_report()
