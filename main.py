import telebot
from telebot import types
import sqlite3
import pandas as pd
from pybit.unified_trading import HTTP
from datetime import datetime, timedelta
import ta
import os

# Константы (можно напрямую вставить токены или использовать переменные окружения)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")

bot = telebot.TeleBot(BOT_TOKEN)
session = HTTP(api_key=API_KEY, api_secret=API_SECRET)

# Подключение SQLite
conn = sqlite3.connect("predictions.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time TEXT,
    close_price REAL,
    signal TEXT,
    actual TEXT,
    votes TEXT
)
""")
conn.commit()

def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    candles = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
    return candles["result"]["list"]

def analyze_indicators(df):
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
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

def make_prediction(ind, last_close):
    votes = []

    if ind["RSI"] > 60:
        votes.append("LONG")
    elif ind["RSI"] < 40:
        votes.append("SHORT")

    votes.append("LONG" if last_close > ind["EMA21"] else "SHORT")
    if ind["ADX"] > 25:
        votes.append("LONG")

    if ind["CCI"] > 100:
        votes.append("LONG")
    elif ind["CCI"] < -100:
        votes.append("SHORT")

    if ind["Stochastic"] > 80:
        votes.append("SHORT")
    elif ind["Stochastic"] < 20:
        votes.append("LONG")

    votes.append("LONG" if ind["Momentum"] > 0 else "SHORT")

    if last_close > ind["BOLL_UP"]:
        votes.append("SHORT")
    elif last_close < ind["BOLL_LOW"]:
        votes.append("LONG")

    votes.append("LONG" if last_close > ind["SAR"] else "SHORT")
    votes.append("LONG" if ind["MACD"] > 0 else "SHORT")

    if ind["WR"] < -80:
        votes.append("LONG")
    elif ind["WR"] > -20:
        votes.append("SHORT")

    long_count = votes.count("LONG")
    short_count = votes.count("SHORT")
    signal = "LONG" if long_count > short_count else "SHORT" if short_count > long_count else "NEUTRAL"

    return signal, votes

def insert_prediction(timestamp, close, signal, votes):
    cursor.execute("INSERT INTO predictions (time, close_price, signal, actual, votes) VALUES (?, ?, ?, ?, ?)",
                   (timestamp, close, signal, None, str(votes)))
    conn.commit()

def update_verifications():
    now = datetime.utcnow()
    cursor.execute("SELECT id, time, close_price, signal FROM predictions WHERE actual IS NULL")
    rows = cursor.fetchall()
    updated = 0
    for row in rows:
        pred_time = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
        if now - pred_time >= timedelta(minutes=15):
            candles = get_candles()
            current_close = float(candles[-1][4])
            actual = "LONG" if current_close > row[2] else "SHORT" if current_close < row[2] else "NEUTRAL"
            cursor.execute("UPDATE predictions SET actual=? WHERE id=?", (actual, row[0]))
            updated += 1
    conn.commit()
    return updated

def calculate_accuracy():
    cursor.execute("SELECT signal, actual FROM predictions WHERE actual IS NOT NULL")
    rows = cursor.fetchall()
    total = len(rows)
    correct = sum(1 for r in rows if r[0] == r[1])
    accuracy = round((correct / total) * 100, 2) if total else 0
    return total, correct, accuracy

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📡 Сигнал", callback_data='signal'))
    markup.add(types.InlineKeyboardButton("📍 Проверка прогноза", callback_data='verify'))
    markup.add(types.InlineKeyboardButton("📊 Точность", callback_data='accuracy'))
    bot.send_message(message.chat.id, "Добро пожаловать! Выберите действие:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id

    if call.data == "signal":
        raw = get_candles()
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        indicators = analyze_indicators(df)
        last_close = float(df["close"].iloc[-1])
        prev_close = float(df["close"].iloc[-2])
        signal, votes = make_prediction(indicators, last_close)
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        insert_prediction(timestamp, last_close, signal, votes)

        text = f"📈 Закрытие: {last_close}\n📉 Предыдущее: {prev_close}\n"
        for key, val in indicators.items():
            text += f"🔹 {key}: {round(val, 2)}\n"
        text += f"\n📌 Прогноз на следующие 15 минут: {'🔺 LONG' if signal == 'LONG' else '🔻 SHORT' if signal == 'SHORT' else '⚪️ NEUTRAL'}\n🧠 Голоса: {votes}"
        bot.send_message(chat_id, text)

    elif call.data == "verify":
        updated = update_verifications()
        bot.send_message(chat_id, f"✅ Обновлено прогнозов: {updated}")

    elif call.data == "accuracy":
        total, correct, acc = calculate_accuracy()
        bot.send_message(chat_id, f"📊 Точность: {acc}% ({correct} из {total})")

bot.polling(none_stop=True)
