import os
import requests
import pandas as pd

# Configuration API
api_key = os.environ["CRYPTOCOMPARE_API_KEY"]
headers = {"authorization": f"Apikey {api_key}"}
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": message})

def fetch_current_prices(crypto_symbols):
    url = "https://min-api.cryptocompare.com/data/pricemulti"
    params = {"fsyms": ",".join(crypto_symbols), "tsyms": "USD"}
    response = requests.get(url, headers=headers, params=params)
    return response.json()

def fetch_historical_data(symbol, limit=200):
    url = "https://min-api.cryptocompare.com/data/v2/histohour"
    params = {"fsym": symbol, "tsym": "USD", "limit": limit}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200 or "Data" not in response.json():
        return None
    data = response.json()["Data"]["Data"]
    return {
        "prices": [entry["close"] for entry in data],
        "volumes": [entry["volumeto"] for entry in data]
    }

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

def display_rsi(cryptos_to_check):
    current_prices = fetch_current_prices(cryptos_to_check)
    message = ""
    status_report = "🔍 Rapport des cryptos surveillées :\n\n"

    for symbol in cryptos_to_check:
        if symbol not in current_prices:
            status_report += f"- {symbol} : Non disponible\n"
            continue

        price = current_prices[symbol]["USD"]
        historical_data = fetch_historical_data(symbol)
        if not historical_data:
            status_report += f"- {symbol} : Données manquantes\n"
            continue

        prices = historical_data["prices"]
        volumes = historical_data["volumes"]
        
        rsi = calculate_rsi(prices).iloc[-1]
        sma = calculate_sma(prices).iloc[-1]
        macd_line, signal_line = calculate_macd(prices)
        volume_alert = analyze_volume(volumes)

        buy_signal = (rsi < 33) and (price > sma) and (macd_line.iloc[-1] > signal_line.iloc[-1]) and volume_alert
        sell_signal = (rsi > 67) and (price < sma) and (macd_line.iloc[-1] < signal_line.iloc[-1]) and volume_alert

        if buy_signal:
            message += f"🚀 **ACHAT {symbol}**\n"
            message += f"- Prix: ${price:.6f} (SMA70: ${sma:.6f})\n"
            message += f"- RSI: {rsi:.1f} | MACD: {macd_line.iloc[-1]:.4f} > {signal_line.iloc[-1]:.4f}\n"
            message += f"- Volume: 🔥 {volumes[-1]/1e6:.1f}M USD\n\n"
        elif sell_signal:
            message += f"🔻 **VENTE {symbol}**\n"
            message += f"- Prix: ${price:.6f} (SMA70: ${sma:.6f})\n"
            message += f"- RSI: {rsi:.1f} | MACD: {macd_line.iloc[-1]:.4f} < {signal_line.iloc[-1]:.4f}\n"
            message += f"- Volume: 💨 {volumes[-1]/1e6:.1f}M USD\n\n"

        status_report += f"- {symbol} : ${price:.6f} | RSI {rsi:.1f} | MACD {macd_line.iloc[-1]:.4f} | Vol {volumes[-1]/1e6:.1f}M\n"

    if message:
        send_telegram_message(message)
    send_telegram_message(status_report)

if __name__ == "__main__":
    cryptos_to_check = ["APE", "GTC", "LOKA", "MBOX","floki"]
    display_rsi([crypto.upper().strip() for crypto in cryptos_to_check])