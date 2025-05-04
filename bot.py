import requests
import pandas as pd
import ta
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

# 🟢👇 यहाँ अपना Telegram Bot Token और Group ID भरो:
TOKEN = "YOUR_BOT_TOKEN_HERE"
CHAT_ID = -1001234567890  # 👈 यहाँ अपना Telegram group ka ID डालो (negative number से शुरू होता है)

bot = Bot(token=TOKEN)
updater = Updater(token=TOKEN, use_context=True)
dispatcher = updater.dispatcher

chart_links = {
    "BTCUSDT": "https://www.tradingview.com/symbols/BTCUSDT/",
    "XAUUSD": "https://www.tradingview.com/symbols/XAUUSD/"
}

timeframes = {
    "15m": "15m",
    "1h": "1h",
    "4h": "4h"
}

def fetch_binance_klines(symbol, interval='1h', limit=100):
    url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}'
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'num_trades',
            'taker_buy_base_vol', 'taker_buy_quote_vol', 'ignore'
        ])
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        return df
    except Exception as e:
        print(f"[ERROR] Fetching Binance data failed for {symbol}: {e}")
        return pd.DataFrame()

def fetch_open_interest(symbol):
    try:
        url = f'https://fapi.binance.com/futures/data/openInterestHist?symbol={symbol}&period=5m&limit=1'
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data:
            return float(data[-1]['sumOpenInterest'])
    except Exception as e:
        print(f"[ERROR] Fetching OI failed for {symbol}: {e}")
    return None

def generate_signal(symbol, timeframe):
    df = fetch_binance_klines(symbol, interval=timeframe)
    if df.empty:
        return {"timeframe": timeframe, "signal": "Error", "price": 0}

    df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    macd = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9)
    df['macd'] = macd.macd_diff()
    df['cci'] = ta.trend.CCIIndicator(df['high'], df['low'], df['close'], window=20).cci()
    bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_bbm'] = bb.bollinger_mavg()
    df['bb_bbh'] = bb.bollinger_hband()
    df['bb_bbl'] = bb.bollinger_lband()

    latest = df.iloc[-1]
    price = latest['close']
    signal = "No clear signal"
    entry = exit_price = sl = None

    if latest['rsi'] < 30 and latest['macd'] > 0 and latest['cci'] < -100:
        signal = "Buy"
        entry = price
        exit_price = price * 1.01
        sl = price * 0.99
    elif latest['rsi'] > 70 and latest['macd'] < 0 and latest['cci'] > 100:
        signal = "Sell"
        entry = price
        exit_price = price * 0.99
        sl = price * 1.01

    return {
        "timeframe": timeframe,
        "signal": signal,
        "price": price,
        "entry": entry,
        "exit": exit_price,
        "sl": sl
    }

def send_hourly_signal(context: CallbackContext):
    symbols = ["BTCUSDT", "XAUUSD"]
    for symbol in symbols:
        message = f"🔔 {symbol} Signals ({datetime.now().strftime('%H:%M %d-%m-%Y')}):\n"
        oi = fetch_open_interest(symbol) if "USDT" in symbol else None

        for tf_name, tf_interval in timeframes.items():
            signal_data = generate_signal(symbol, tf_interval)
            message += (
                f"\n⏱ Timeframe: {tf_name}\n"
                f"📈 Price: ${signal_data['price']:.2f}\n"
                f"🚨 Signal: {signal_data['signal']}\n"
            )
            if signal_data["entry"]:
                message += (
                    f"🔵 Entry: ${signal_data['entry']:.2f}\n"
                    f"🟢 Target: ${signal_data['exit']:.2f}\n"
                    f"🔴 Stop Loss: ${signal_data['sl']:.2f}\n"
                )

        if oi:
            message += f"\n📊 Open Interest: {oi:,.2f} Contracts"

        message += (
            f"\n\n📚 Signal is based on RSI, MACD, CCI, and Bollinger Bands.\n"
            f"📊 Live Chart: {chart_links.get(symbol, 'N/A')}"
        )

        context.bot.send_message(chat_id=CHAT_ID, text=message)

def start(update: Update, context: CallbackContext):
    update.message.reply_text("✅ Welcome! This bot sends BTC & Gold signals every hour.")

dispatcher.add_handler(CommandHandler("start", start))

scheduler = BackgroundScheduler()
scheduler.add_job(send_hourly_signal, 'interval', hours=1, args=[CallbackContext.from_bot(bot)])
scheduler.start()

# Run once at startup
send_hourly_signal(CallbackContext.from_bot(bot))

updater.start_polling()
updater.idle()
