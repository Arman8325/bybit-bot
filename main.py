import telebot
import os
from pybit.unified_trading import HTTP
import openai
import talib
import numpy as np
import time

bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))

session = HTTP(
    api_key=os.getenv("BYBIT_API_KEY"),
    api_secret=os.getenv("BYBIT_API_SECRET")
)

openai.api_key = os.getenv("OPENAI_API_KEY")

def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    try:
        response = session.get_kline(
            category="linear",
            symbol=symbol,
            interval=interval,
            limit=limit
        )
        if not response.get("result") or not response["result"].get("list"):
            return None
        return response["result"]["list"]
    except Exception as e:
        return None

def analyze_indicators(candle_data):
    closes = np.array([float(c[4]) for c in candle_data], dtype=float)
    highs = np.array([float(c[2]) for c in candle_data], dtype=float)
    lows = np.array([float(c[3]) for c in candle_data], dtype=float)
    volumes = np.array([float(c[5]) for c in candle_data], dtype=float)

    rsi = talib.RSI(closes, timeperiod=14)[-1]
    macd, macdsignal, _ = talib.MACD(closes, fastperiod=12, slowperiod=26, signalperiod=9)
    ema9 = talib.EMA(closes, timeperiod=9)[-1]
    ema21 = talib.EMA(closes, timeperiod=21)[-1]
    sma50 = talib.SMA(closes, timeperiod=50)[-1]
    upper, middle, lower = talib.BBANDS(closes, timeperiod=20)

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
        "bb_lower": round(lower[-1], 2)
    }

def chatgpt_analysis(indicators):
    prompt = f"""
    Дай торговую рекомендацию на 15 минут на основе следующих индикаторов:
    - Цена закрытия: {indicators['close']}
    - Предыдущая цена: {indicators['previous']}
    - RSI: {indicators['rsi']}
    - MACD: {indicators['macd']}, сигнал MACD: {indicators['macd_signal']}
    - EMA9: {indicators['ema9']}, EMA21: {indicators['ema21']}
    - SMA50: {indicators['sma50']}
    - Объём: {indicators['volume']}
    - Полосы Боллинджера: Верхняя {indicators['bb_upper']}, Средняя {indicators['bb_middle']}, Нижняя {indicators['bb_lower']}
    
    Выводи: LONG / SHORT / NEUTRAL и объяснение.
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты торговый аналитик Bybit."},
                {"role": "user", "content": prompt}
            ]
        )
        return response["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ Ошибка анализа ChatGPT:\n{str(e)}"

@bot.message_handler(commands=['signal'])
def get_signal(message):
    bot.send_message(message.chat.id, "⏳ Получаю данные от Bybit...")
    candle_data = get_candles()
    if candle_data is None:
        bot.send_message(message.chat.id, "❌ Ошибка получения данных от Bybit")
        return

    indicators = analyze_indicators(candle_data)
    response = chatgpt_analysis(indicators)

    formatted = f"""
📊 Закрытие: {indicators['close']}
📉 Предыдущее: {indicators['previous']}
ℹ️ RSI: {indicators['rsi']}
📉 MACD: {indicators['macd']}, сигнал: {indicators['macd_signal']}
📈 EMA9: {indicators['ema9']}, EMA21: {indicators['ema21']}
📊 SMA50: {indicators['sma50']}
📊 Volume: {indicators['volume']}
📎 Bollinger Bands: Верхняя {indicators['bb_upper']}, Средняя {indicators['bb_middle']}, Нижняя {indicators['bb_lower']}
🔎 Рекомендация ChatGPT:
{response}
    """
    bot.send_message(message.chat.id, formatted)

bot.polling()

