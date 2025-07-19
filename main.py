import requests
import pandas as pd

import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ✅ List of coins to monitor
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "SEIUSDT", "POLUSDT"]

# ✅ Volume confirmation toggle
REQUIRE_HIGH_VOLUME = True  # Set to False to allow entries even on normal volume

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    requests.post(url, data=payload)

def get_binance_candles(symbol, interval='1m', limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        resp = requests.get(url, timeout=5).json()
        df = pd.DataFrame(resp, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "number_of_trades",
            "taker_buy_base_vol", "taker_buy_quote_vol", "ignore"
        ])
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit='ms')
        return df
    except Exception as e:
        print(f"❌ Error fetching Binance candles for {symbol}: {e}")
        return pd.DataFrame()

def get_coindcx_prices():
    url = "https://api.coindcx.com/exchange/ticker"
    try:
        response = requests.get(url, timeout=5).json()
        prices = {}
        for item in response:
            market = item.get('market')
            last_price = item.get('last_price')
            if market and last_price:
                try:
                    prices[market] = float(last_price)
                except ValueError:
                    continue
        return prices
    except Exception as e:
        print(f"❌ Error fetching CoinDCX prices: {e}")
        return {}

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def analyze_coin(symbol, coindcx_prices):
    df = get_binance_candles(symbol)
    if df.empty or len(df) < 50:
        print(f"❌ Not enough candle data for {symbol}")
        return

    df["ema20"] = df["close"].ewm(span=20).mean()
    df["ema50"] = df["close"].ewm(span=50).mean()
    df["rsi"] = calculate_rsi(df["close"])
    df["vol_avg"] = df["volume"].rolling(window=20).mean()

    last = df.iloc[-1]
    ema20 = last["ema20"]
    ema50 = last["ema50"]
    rsi = round(last["rsi"], 1)
    vol = last["volume"]
    vol_avg = last["vol_avg"]

    live_price = coindcx_prices.get(symbol)
    if live_price is None:
        print(f"❌ Live price not found for {symbol}")
        return

    buffer = 0.001
    above_ema20 = live_price > ema20 * (1 + buffer)
    below_ema20 = live_price < ema20 * (1 - buffer)
    above_ema50 = live_price > ema50 * (1 + buffer)
    below_ema50 = live_price < ema50 * (1 - buffer)

    last3 = df.tail(3)
    trend_up = all(last3["ema20"] > last3["ema50"])
    trend_down = all(last3["ema20"] < last3["ema50"])
    high_volume = vol > 1.5 * vol_avg

    coin_display = f"{symbol[:-4]}/{symbol[-4:]}"
    header = f"\n📊 Analyzing: {coin_display}"
    price_line = f"➡️ Live Price: `{live_price:.5f}`"
    ema20_line = f"📈 EMA20: `{ema20:.5f}` → {'Above' if live_price > ema20 else 'Below'}"
    ema50_line = f"📉 EMA50: `{ema50:.5f}` → {'Above' if live_price > ema50 else 'Below'}"
    rsi_line = f"📊 RSI(14): `{rsi}` → {'Bullish Momentum ✅' if rsi > 55 else 'Bearish Momentum ❌'}"
    vol_line = f"🔊 Volume: `{vol:.2f}` (Avg: `{vol_avg:.2f}`) → {'🔥 High Volume' if high_volume else 'Normal Volume'}"

    signal_line = "🎯 Strategy Signal: ❌ No signal"

    if above_ema20 and above_ema50 and rsi > 55 and trend_up:
        if REQUIRE_HIGH_VOLUME and not high_volume:
            signal_line = "🎯 Strategy Signal: ⚠️ LONG Valid but Low Volume"
        else:
            signal_line = "🎯 Strategy Signal: 📈 LONG Entry ✅"
    elif below_ema20 and below_ema50 and rsi < 45 and trend_down:
        if REQUIRE_HIGH_VOLUME and not high_volume:
            signal_line = "🎯 Strategy Signal: ⚠️ SHORT Valid but Low Volume"
        else:
            signal_line = "🎯 Strategy Signal: 📉 SHORT Entry ✅"

    message = "\n".join([
        header,
        price_line,
        ema20_line,
        ema50_line,
        rsi_line,
        vol_line,
        signal_line
    ])

    print(message)

    if "LONG" in signal_line or "SHORT" in signal_line:
        send_telegram(message)

# --- Run the analysis ---
if __name__ == "__main__":
    coindcx_prices = get_coindcx_prices()
    for symbol in COINS:
        analyze_coin(symbol, coindcx_prices)
