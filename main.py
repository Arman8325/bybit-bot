import telebot
import os
import pandas as pd
import pandas_ta as ta
import numpy as np
from pybit.unified_trading import HTTP

# === Временно вставленные токены (замени переменные на os.getenv("...") при необходимости) ===
TELEGRAM_BOT_TOKEN = "7725284250:AAFQi1jp4yWefZJExHlXOoLQWEPLdrnuk4w"
BYBIT_API_KEY = "IyFHgr8YtnCz60D27D"
BYBIT_API_SECRET = "kxj3fry4US9lZq2nyDZIVKMgSaTd7U7vPp53"

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

session = HTTP(
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET
)

def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    try:
        response = session.get_kline(
            category="linear",
            symbol=symbol,
            interval=interval,
            limit=limit
        )
        return response["result"]["list"]
    except Exception as e:
        return None

def analyze_indicators(candle_data):
    closes = [float(c[4]) for c in candle_data]
    highs = [float(c[2]) for c in candle_data]
    lows = [float(c[3]) for c in candle_data]
    volumes = [float(c[5]) for c in candle_data]

    df = pd.DataFrame({
        "close": closes,
        "high": highs,
        "low": lows,
        "volume": volumes
    })

    df["rsi"] = ta.rsi(df["close"], length=14)
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    df = pd.concat([df, macd], axis=1)
    df["ema9"] = ta.ema(df["close"], length=9)
    df["ema21"] = ta.ema(df["close"], length=21)
    df["sma50"] = ta.sma(df["close"], length=50)
    bb = ta.bbands(df["close"], length=20)
    df = pd.concat([df, bb], axis=1)

    latest = df.iloc[-1]
    previous = df.iloc[-2]

    trend = "LONG" if latest["close"] > previous["close"] else "SHORT" if latest["close"] < previous["close"] else "NEUTRAL"

    return {
        "close": latest["close"],
        "previous": previous["close"],
        "rsi": round(latest["rsi"], 2),
        "macd": round(latest["MACD_12_26_9"], 2),
        "macd_signal": round(latest["MACDs_12_26_9"], 2),
        "ema9": round(latest["ema9"], 2),
        "ema21": round(latest["ema21"], 2),
        "sma50": round(latest["sma50"], 2),
        "volume": round(latest["volume"], 2),
        "bb_upper": round(latest["BBU_20_2.0"], 2),
        "bb_middle": round(latest["BBM_20_2.0"], 2),
        "bb_lower": round(latest["BBL_20_2.0"], 2),
        "signal": trend
    }

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal, чтобы получить анализ.")

@bot.message_handler(commands=['signal'])
def get_signal(message):
    bot.send_message(message.chat.id, "⏳ Получаю данные от Bybit...")
    candle_data = get_candles()
    if not candle_data:
        bot.send_message(message.chat.id, "❌ Ошибка получения данных от Bybit")
        return

    indicators = analyze_indicators(candle_data)

    formatted = f"""
📊 Закрытие: {indicators['close']}
📉 Предыдущее: {indicators['previous']}
ℹ️ RSI: {indicators['rsi']}
📉 MACD: {indicators['macd']}, сигнал: {indicators['macd_signal']}
📈 EMA9: {indicators['ema9']}, EMA21: {indicators['ema21']}
📊 SMA50: {indicators['sma50']}
📊 Объём: {indicators['volume']}
📎 Bollinger Bands: Верхняя {indicators['bb_upper']}, Средняя {indicators['bb_middle']}, Нижняя {indicators['bb_lower']}
📌 Сигнал: {'🔺 LONG' if indicators['signal'] == 'LONG' else '🔻 SHORT' if indicators['signal'] == 'SHORT' else '➖ NEUTRAL'}
"""

    bot.send_message(message.chat.id, formatted)

bot.polling()
