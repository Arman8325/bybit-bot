import telebot
import os
import numpy as np
import talib
from pybit.unified_trading import HTTP

# Вставь токены или используй переменные среды
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(
    api_key=os.getenv("BYBIT_API_KEY"),
    api_secret=os.getenv("BYBIT_API_SECRET")
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

def analyze_indicators(candles):
    closes = np.array([float(c[4]) for c in candles], dtype=float)
    highs = np.array([float(c[2]) for c in candles], dtype=float)
    lows = np.array([float(c[3]) for c in candles], dtype=float)
    volumes = np.array([float(c[5]) for c in candles], dtype=float)

    rsi = talib.RSI(closes, timeperiod=14)[-1]
    macd, macdsignal, _ = talib.MACD(closes)
    ema9 = talib.EMA(closes, timeperiod=9)[-1]
    ema21 = talib.EMA(closes, timeperiod=21)[-1]
    sma50 = talib.SMA(closes, timeperiod=50)[-1]
    upper, middle, lower = talib.BBANDS(closes)

    # Простая логика для генерации сигнала
    if rsi < 30 and ema9 > ema21 and closes[-1] > middle[-1]:
        signal = "🔺 LONG (вверх)"
    elif rsi > 70 and ema9 < ema21 and closes[-1] < middle[-1]:
        signal = "🔻 SHORT (вниз)"
    else:
        signal = "➖ NEUTRAL"

    return {
        "close": closes[-1],
        "previous": closes[-2],
        "rsi": round(rsi, 2),
        "macd": round(macd[-1], 2),
        "macd_signal": round(macdsignal[-1], 2),
        "ema9": round(ema9, 2),
        "ema21": round(ema21, 2),
        "sma50": round(sma50, 2),
        "volume": round(volumes[-1], 2),
        "bb_upper": round(upper[-1], 2),
        "bb_middle": round(middle[-1], 2),
        "bb_lower": round(lower[-1], 2),
        "signal": signal
    }

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal, чтобы получить анализ рынка.")

@bot.message_handler(commands=['signal'])
def get_signal(message):
    bot.send_message(message.chat.id, "⏳ Получаю данные от Bybit...")
    candles = get_candles()
    if not candles:
        bot.send_message(message.chat.id, "❌ Не удалось получить данные от Bybit.")
        return

    indicators = analyze_indicators(candles)

    text = f"""
📊 Закрытие: {indicators['close']}
📉 Предыдущая: {indicators['previous']}
ℹ️ RSI: {indicators['rsi']}
📉 MACD: {indicators['macd']} | сигнал: {indicators['macd_signal']}
📈 EMA9: {indicators['ema9']} | EMA21: {indicators['ema21']}
📏 SMA50: {indicators['sma50']}
📎 BB: Верхняя {indicators['bb_upper']}, Средняя {indicators['bb_middle']}, Нижняя {indicators['bb_lower']}
🔊 Объём: {indicators['volume']}
📌 Сигнал: {indicators['signal']}
    """
    bot.send_message(message.chat.id, text.strip())

bot.polling()
