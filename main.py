import telebot
import os
from pybit.unified_trading import HTTP
import pandas as pd
import ta
import sqlite3
from datetime import datetime

# Инициализация бота и Bybit API
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

# Инициализация SQLite
conn = sqlite3.connect("prediction_stats.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    predicted TEXT,
    actual TEXT,
    result TEXT,
    indicators TEXT
)
''')
conn.commit()

def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    try:
        candles = session.get_kline(
            category="linear",
            symbol=symbol,
            interval=interval,
            limit=limit
        )
        return candles["result"]["list"]
    except Exception:
        return None

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal для прогноза.")

@bot.message_handler(commands=['signal'])
def send_signal(message):
    bot.send_message(message.chat.id, "📊 Получаю данные от Bybit...")

    try:
        data = get_candles()
        if data is None:
            raise ValueError("❌ Не удалось получить данные с Bybit.")

        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)

        # Технические индикаторы
        rsi = ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1]
        ema = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1]
        adx = ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1]
        cci = ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1]
        stoch = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"]).stoch().iloc[-1]
        momentum = ta.momentum.ROCIndicator(df["close"]).roc().iloc[-1]
        bb = ta.volatility.BollingerBands(df["close"])
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        last = df["close"].iloc[-1]
        prev = df["close"].iloc[-2]

        # Голосование по логике
        long_votes, short_votes = 0, 0

        if rsi > 60: long_votes += 1
        elif rsi < 40: short_votes += 1

        if last > ema: long_votes += 1
        elif last < ema: short_votes += 1

        if adx > 20: long_votes += 1
        if cci > 100: long_votes += 1
        elif cci < -100: short_votes += 1

        if stoch > 80: short_votes += 1
        elif stoch < 20: long_votes += 1

        if momentum > 0: long_votes += 1
        elif momentum < 0: short_votes += 1

        if last > bb_upper: short_votes += 1
        elif last < bb_lower: long_votes += 1

        if long_votes > short_votes:
            signal = "🔺 LONG"
            prediction = "LONG"
        elif short_votes > long_votes:
            signal = "🔻 SHORT"
            prediction = "SHORT"
        else:
            signal = "⚪️ NEUTRAL"
            prediction = "NEUTRAL"

        # Сохраняем прогноз
        cursor.execute('''
        INSERT INTO predictions (timestamp, predicted, actual, result, indicators)
        VALUES (?, ?, ?, ?, ?)
        ''', (
            datetime.utcnow().isoformat(),
            prediction,
            "-", "-", "RSI, EMA21, ADX, CCI, Stochastic, Momentum, Bollinger Bands"
        ))
        conn.commit()

        # Ответ пользователю
        bot.send_message(message.chat.id, f"""
📈 Закрытие: {last}
📉 Предыдущее: {prev}
📊 RSI: {round(rsi, 2)}
📈 EMA21: {round(ema, 2)}
📊 ADX: {round(adx, 2)}
📊 CCI: {round(cci, 2)}
📊 Stochastic: {round(stoch, 2)}
📊 Momentum: {round(momentum, 2)}
📊 Bollinger Bands:
   🔺 Верхняя: {round(bb_upper, 2)}
   🔻 Нижняя: {round(bb_lower, 2)}
📌 Прогноз на следующие 15 минут: {signal}
        """)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()
