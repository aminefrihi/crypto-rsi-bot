import os
import json
import requests
import pandas as pd
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, CallbackContext

# Configuration
API_KEY = os.environ["CRYPTOCOMPARE_API_KEY"]
HEADERS = {"authorization": f"Apikey {API_KEY}"}
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
CRYPTO_FILE = "tracked_cryptos.json"

# Initialisation du bot Telegram
bot = Bot(token=TELEGRAM_TOKEN)

# Gestion de la liste des cryptos
def load_cryptos():
    try:
        with open(CRYPTO_FILE, "r") as f:
            return json.load(f).get("cryptos", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_cryptos(cryptos):
    with open(CRYPTO_FILE, "w") as f:
        json.dump({"cryptos": cryptos}, f)

# Commandes Telegram
def start(update: Update, context: CallbackContext):
    if str(update.effective_chat.id) != CHAT_ID:
        return
    update.message.reply_text(
        "🤖 Crypto Trading Bot Pro\n\n"
        "📌 Commandes disponibles:\n"
        "/add [SYMBOLE] - Ajouter une crypto\n"
        "/delete [SYMBOLE] - Supprimer une crypto\n"
        "/list - Liste des cryptos suivies\n"
        "/checkinfo [SYMBOLE] - Analyse instantanée\n"
        "/runnow - Exécuter l'analyse maintenant"
    )

def add_crypto(update: Update, context: CallbackContext):
    if str(update.effective_chat.id) != CHAT_ID:
        return
    try:
        symbol = update.message.text.split()[1].upper()
    except IndexError:
        update.message.reply_text("❌ Usage: /add [SYMBOLE]")
        return

    cryptos = load_cryptos()
    if symbol in cryptos:
        update.message.reply_text(f"⚠️ {symbol} est déjà dans la liste.")
        return

    # Vérification de l'existence de la crypto
    url = f"https://min-api.cryptocompare.com/data/price?fsym={symbol}&tsyms=USD"
    response = requests.get(url, headers=HEADERS)
    if "USD" not in response.json():
        update.message.reply_text(f"❌ {symbol} non trouvé sur CryptoCompare")
        return

    cryptos.append(symbol)
    save_cryptos(cryptos)
    update.message.reply_text(f"✅ {symbol} ajouté avec succès!")

def delete_crypto(update: Update, context: CallbackContext):
    if str(update.effective_chat.id) != CHAT_ID:
        return
    try:
        symbol = update.message.text.split()[1].upper()
    except IndexError:
        update.message.reply_text("❌ Usage: /delete [SYMBOLE]")
        return

    cryptos = load_cryptos()
    if symbol not in cryptos:
        update.message.reply_text(f"❌ {symbol} non trouvé dans la liste.")
        return

    cryptos.remove(symbol)
    save_cryptos(cryptos)
    update.message.reply_text(f"✅ {symbol} supprimé avec succès!")

def list_cryptos(update: Update, context: CallbackContext):
    if str(update.effective_chat.id) != CHAT_ID:
        return
    cryptos = load_cryptos()
    if not cryptos:
        update.message.reply_text("📭 La liste est vide")
        return
    update.message.reply_text("📋 Cryptos suivies:\n" + "\n".join(cryptos))

# Analyse technique
def calculate_rsi(prices, period=14):
    delta = pd.Series(prices).diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_sma(prices, window=70):
    return pd.Series(prices).rolling(window).mean()

def calculate_macd(prices, fast=12, slow=26, signal=9):
    prices_series = pd.Series(prices)
    ema_fast = prices_series.ewm(span=fast, adjust=False).mean()
    ema_slow = prices_series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line

def analyze_volume(volumes, window=20):
    avg_volume = pd.Series(volumes).rolling(window).mean().iloc[-1]
    current_volume = volumes[-1]
    return current_volume > avg_volume * 2.25 and current_volume > 2_500_000

def get_crypto_data(symbol):
    try:
        # Prix actuel
        price_url = f"https://min-api.cryptocompare.com/data/price?fsym={symbol}&tsyms=USD"
        price_data = requests.get(price_url, headers=HEADERS).json()
        current_price = price_data.get("USD")

        # Données historiques
        hist_url = "https://min-api.cryptocompare.com/data/v2/histohour"
        params = {"fsym": symbol, "tsym": "USD", "limit": 200}
        hist_data = requests.get(hist_url, headers=HEADERS, params=params).json()
        prices = [entry["close"] for entry in hist_data["Data"]["Data"]]
        volumes = [entry["volumeto"] for entry in hist_data["Data"]["Data"]]

        return {
            "price": current_price,
            "prices": prices,
            "volumes": volumes,
            "error": None
        }
    except Exception as e:
        return {"error": str(e)}

def generate_signal(symbol):
    data = get_crypto_data(symbol)
    if data["error"]:
        return {"error": data["error"]}

    try:
        rsi = calculate_rsi(data["prices"]).iloc[-1]
        sma = calculate_sma(data["prices"], 70).iloc[-1]
        macd_line, signal_line = calculate_macd(data["prices"])
        volume_alert = analyze_volume(data["volumes"])

        buy_signal = (rsi < 33) and (data["price"] > sma) and (macd_line.iloc[-1] > signal_line.iloc[-1]) and volume_alert
        sell_signal = (rsi > 67) and (data["price"] < sma) and (macd_line.iloc[-1] < signal_line.iloc[-1]) and volume_alert

        recommendation = ""
        if buy_signal:
            recommendation = "🚀 FORT POTENTIEL D'ACHAT"
        elif sell_signal:
            recommendation = "🔻 SIGNAL DE VENTE"
        else:
            recommendation = "🟡 NEUTRE"

        return {
            "symbol": symbol,
            "price": data["price"],
            "rsi": rsi,
            "sma": sma,
            "macd": macd_line.iloc[-1],
            "signal_line": signal_line.iloc[-1],
            "volume_status": "🔥 Élevé" if volume_alert else "💤 Normal",
            "recommendation": recommendation,
            "error": None
        }
    except Exception as e:
        return {"error": str(e)}

def check_crypto_info(update: Update, context: CallbackContext):
    if str(update.effective_chat.id) != CHAT_ID:
        return

    try:
        symbol = update.message.text.split()[1].upper()
    except IndexError:
        update.message.reply_text("❌ Usage: /checkinfo [SYMBOLE]")
        return

    result = generate_signal(symbol)
    if result.get("error"):
        update.message.reply_text(f"❌ Erreur: {result['error']}")
        return

    message = (
        f"📊 Analyse de {symbol}\n"
        f"▫️ Prix actuel: ${result['price']:.6f}\n"
        f"▫️ RSI (14): {result['rsi']:.2f}\n"
        f"▫️ SMA70: ${result['sma']:.6f}\n"
        f"▫️ MACD: {result['macd']:.4f} | Signal: {result['signal_line']:.4f}\n"
        f"▫️ Volume: {result['volume_status']}\n"
        f"🔍 Recommandation: {result['recommendation']}"
    )
    update.message.reply_text(message)

def run_analysis_now(update: Update, context: CallbackContext):
    if str(update.effective_chat.id) != CHAT_ID:
        return

    cryptos = load_cryptos()
    if not cryptos:
        update.message.reply_text("ℹ️ Aucune crypto à analyser")
        return

    message = "🔎 Analyse en temps réel :\n\n"
    for symbol in cryptos:
        result = generate_signal(symbol)
        if result.get("error"):
            message += f"❌ {symbol}: {result['error']}\n"
        else:
            message += (
                f"{result['recommendation']} pour {symbol}\n"
                f"- Prix: ${result['price']:.6f} | RSI: {result['rsi']:.2f}\n\n"
            )

    update.message.reply_text(message)

def send_telegram_message(text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text}
    )

def main():
   
   from telegram.ext import Application, CommandHandler
   app = Application.builder().token(TELEGRAM_TOKEN).build()

   app.add_handler(CommandHandler("start", start))
   app.add_handler(CommandHandler("add", add_crypto))
   app.add_handler(CommandHandler("delete", delete_crypto))
   app.add_handler(CommandHandler("list", list_cryptos))
   app.add_handler(CommandHandler("checkinfo", check_crypto_info))
   app.add_handler(CommandHandler("runnow", run_analysis_now))

   app.run_polling()

if __name__ == "__main__":
    main()