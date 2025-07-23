# 🔁 Установи зависимости, если запускаешь в Google Colab:
# !pip install pyTelegramBotAPI ta pybit

import telebot
from telebot import types
import os
import pandas as pd
from pybit.unified_trading import HTTP
from datetime import datetime, timedelta
import ta
import sqlite3

# 🔐 Переменные окружения
TELEGRAM_BOT_TOKEN = "ТВОЙ_ТОКЕН_ОТ_Бота"
BYBIT_API_KEY = "ТВОЙ_API_KEY"
BYBIT_API_SECRET = "ТВОЙ_API_SECRET"

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

# 📊 База данных SQLite
conn = sqlite3.connect("predictions.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time TEXT,
    price REAL,
    signal TEXT,
    actual TEXT,
    votes TEXT
)
""")
conn.commit()

# 📈 Получение свечей
def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    candles = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
    return candles["result"]["list"]

# 📊 Анализ индикаторов
def analyze_indicators(df):
    df = df.astype(float)
    indicators = {}
    indicators["RSI"] = ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1]
    indicators["EMA21"] = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1]
    indicators["ADX"] = ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1]
    indicators["CCI"] = ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1]
    indicators["Stochastic"] = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"]).stoch().iloc[-1]
    indicators["Momentum"] = ta.momentum.ROCIndicator(df["close"]).roc().iloc[-1]
    bb = ta.volatility.BollingerBands(df["close"])
    indicators["BOLL_UP"] = bb.bollinger_hband().iloc[-1]
    indicators["BOLL_LOW"] = bb.bollinger_lband().iloc[-1]
    indicators["SAR"] = ta.trend.PSARIndicator(df["high"], df["low"], df["close"]).psar().iloc[-1]
    indicators["MACD"] = ta.trend.MACD(df["close"]).macd().iloc[-1]
    indicators["WR"] = ta.momentum.WilliamsRIndicator(df["high"], df["low"], df["close"]).williams_r().iloc[-1]
    return indicators

# 🤖 Прогноз
def make_prediction(ind, close):
    votes = []
    if ind["RSI"] > 60: votes.append("LONG")
    elif ind["RSI"] < 40: votes.append("SHORT")
    votes.append("LONG" if close > ind["EMA21"] else "SHORT")
    if ind["ADX"] > 25: votes.append("LONG")
    if ind["CCI"] > 100: votes.append("LONG")
    elif ind["CCI"] < -100: votes.append("SHORT")
    if ind["Stochastic"] > 80: votes.append("SHORT")
    elif ind["Stochastic"] < 20: votes.append("LONG")
    votes.append("LONG" if ind["Momentum"] > 0 else "SHORT")
    if close > ind["BOLL_UP"]: votes.append("SHORT")
    elif close < ind["BOLL_LOW"]: votes.append("LONG")
    votes.append("LONG" if close > ind["SAR"] else "SHORT")
    votes.append("LONG" if ind["MACD"] > 0 else "SHORT")
    if ind["WR"] < -80: votes.append("LONG")
    elif ind["WR"] > -20: votes.append("SHORT")

    long_votes = votes.count("LONG")
    short_votes = votes.count("SHORT")
    signal = "LONG" if long_votes > short_votes else "SHORT" if short_votes > long_votes else "NEUTRAL"
    return signal, votes

# 🚀 Команда /start с кнопками
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("/signal"), types.KeyboardButton("/verify"), types.KeyboardButton("/accuracy"))
    bot.send_message(message.chat.id, "🤖 Добро пожаловать! Выберите команду:", reply_markup=markup)

# 🔮 Команда /signal
@bot.message_handler(commands=['signal'])
def signal(message):
    raw = get_candles()
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
    df = df.astype(float)
    indicators = analyze_indicators(df)
    close = df["close"].iloc[-1]
    prev = df["close"].iloc[-2]
    signal, votes = make_prediction(indicators, close)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("INSERT INTO predictions (time, price, signal, actual, votes) VALUES (?, ?, ?, ?, ?)",
                   (now, close, signal, None, str(votes)))
    conn.commit()

    text = f"📈 Закрытие: {close}\n📉 Предыдущее: {prev}\n"
    for k, v in indicators.items():
        text += f"🔹 {k}: {round(v, 2)}\n"
    text += f"\n📌 Прогноз: {'🔺 LONG' if signal == 'LONG' else '🔻 SHORT' if signal == 'SHORT' else '⚪ NEUTRAL'}\n🧠 Голоса: {votes}"
    bot.send_message(message.chat.id, text)

# 🔍 Команда /verify
@bot.message_handler(commands=['verify'])
def verify(message):
    now = datetime.utcnow()
    cursor.execute("SELECT id, time, price FROM predictions WHERE actual IS NULL")
    rows = cursor.fetchall()
    updated = 0
    for r in rows:
        pred_time = datetime.strptime(r[1], "%Y-%m-%d %H:%M:%S")
        if now - pred_time >= timedelta(minutes=15):
            candles = get_candles()
            new_price = float(candles[-1][4])
            actual = "LONG" if new_price > r[2] else "SHORT" if new_price < r[2] else "NEUTRAL"
            cursor.execute("UPDATE predictions SET actual=? WHERE id=?", (actual, r[0]))
            updated += 1
    conn.commit()
    bot.send_message(message.chat.id, f"✅ Обновлено прогнозов: {updated}")

# 📊 Команда /accuracy
@bot.message_handler(commands=['accuracy'])
def accuracy(message):
    cursor.execute("SELECT signal, actual FROM predictions WHERE actual IS NOT NULL")
    rows = cursor.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "ℹ️ Нет проверенных прогнозов.")
        return
    total = len(rows)
    correct = sum(1 for s, a in rows if s == a)
    percent = round(100 * correct / total, 2)
    bot.send_message(message.chat.id, f"📊 Точность: {percent}% ({correct} из {total})")

# ▶️ Запуск бота
bot.polling(none_stop=True)
