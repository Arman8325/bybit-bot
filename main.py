import telebot
from telebot import types
import os
import pandas as pd
import ta
import threading
import time
import sqlite3
from dotenv import load_dotenv
from pybit.unified_trading import HTTP
from datetime import datetime, timedelta

# Загрузка .env переменных
load_dotenv()

bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

# Подключение к SQLite
conn = sqlite3.connect("predictions.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    price REAL,
    signal TEXT,
    actual TEXT,
    votes TEXT
)
""")
conn.commit()

# Получение свечей с Bybit
def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    data = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
    return data["result"]["list"]

# Технический анализ
def analyze_indicators(df):
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)

    ind = {}
    ind["RSI"] = ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1]
    ind["EMA21"] = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1]
    ind["ADX"] = ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1]
    ind["CCI"] = ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1]
    ind["Stochastic"] = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"]).stoch().iloc[-1]
    ind["Momentum"] = ta.momentum.ROCIndicator(df["close"]).roc().iloc[-1]
    bb = ta.volatility.BollingerBands(df["close"])
    ind["BOLL_UP"] = bb.bollinger_hband().iloc[-1]
    ind["BOLL_LOW"] = bb.bollinger_lband().iloc[-1]
    ind["SAR"] = ta.trend.PSARIndicator(df["high"], df["low"], df["close"]).psar().iloc[-1]
    ind["MACD"] = ta.trend.MACD(df["close"]).macd().iloc[-1]
    ind["WR"] = ta.momentum.WilliamsRIndicator(df["high"], df["low"], df["close"]).williams_r().iloc[-1]
    return ind

# Прогноз на основе голосования индикаторов
def make_prediction(ind, last_close):
    votes = []

    if ind["RSI"] > 60: votes.append("LONG")
    elif ind["RSI"] < 40: votes.append("SHORT")
    votes.append("LONG" if last_close > ind["EMA21"] else "SHORT")
    if ind["ADX"] > 25: votes.append("LONG")
    if ind["CCI"] > 100: votes.append("LONG")
    elif ind["CCI"] < -100: votes.append("SHORT")
    if ind["Stochastic"] > 80: votes.append("SHORT")
    elif ind["Stochastic"] < 20: votes.append("LONG")
    votes.append("LONG" if ind["Momentum"] > 0 else "SHORT")
    if last_close > ind["BOLL_UP"]: votes.append("SHORT")
    elif last_close < ind["BOLL_LOW"]: votes.append("LONG")
    votes.append("LONG" if last_close > ind["SAR"] else "SHORT")
    votes.append("LONG" if ind["MACD"] > 0 else "SHORT")
    if ind["WR"] < -80: votes.append("LONG")
    elif ind["WR"] > -20: votes.append("SHORT")

    long_count = votes.count("LONG")
    short_count = votes.count("SHORT")
    signal = "LONG" if long_count > short_count else "SHORT" if short_count > long_count else "NEUTRAL"
    return signal, votes

# Автообновление прогноза каждые 15 минут
def auto_update():
    while True:
        send_auto_signal()
        time.sleep(900)  # каждые 15 минут (900 сек)

# Функция отправки сигнала
def send_auto_signal():
    candles = get_candles()
    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
    ind = analyze_indicators(df)
    last = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2])
    signal, votes = make_prediction(ind, last)

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO predictions (timestamp, price, signal, actual, votes) VALUES (?, ?, ?, ?, ?)",
        (timestamp, last, signal, None, ",".join(votes))
    )
    conn.commit()

    text = f"📈 Закрытие: {last}\n📉 Предыдущее: {prev}\n"
    for k, v in ind.items():
        text += f"🔹 {k}: {round(v, 2)}\n"
    text += f"\n📌 Прогноз на следующие 15 минут: {'🔺 LONG' if signal == 'LONG' else '🔻 SHORT' if signal == 'SHORT' else '⚪️ NEUTRAL'}\n🧠 Голоса: {votes}"
    
    # Отправим всем, кто запускал /start (для упрощения — пока в 1 чат)
    if last_chat_id:
        bot.send_message(last_chat_id, text)

# Проверка прогноза
def verify_predictions(chat_id):
    now = datetime.utcnow()
    updated = 0
    cursor.execute("SELECT id, timestamp, price, signal FROM predictions WHERE actual IS NULL")
    for row in cursor.fetchall():
        pid, ts, price, signal = row
        ts_dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        if (now - ts_dt) >= timedelta(minutes=15):
            candles = get_candles()
            current = float(candles[-1][4])
            actual = "LONG" if current > price else "SHORT" if current < price else "NEUTRAL"
            cursor.execute("UPDATE predictions SET actual = ? WHERE id = ?", (actual, pid))
            updated += 1
    conn.commit()
    bot.send_message(chat_id, f"🔍 Обновлено прогнозов: {updated}")

# Точность
def show_accuracy(chat_id):
    cursor.execute("SELECT signal, actual FROM predictions WHERE actual IS NOT NULL")
    results = cursor.fetchall()
    if not results:
        bot.send_message(chat_id, "📊 Ещё нет проверенных прогнозов.")
        return
    total = len(results)
    correct = sum(1 for s, a in results if s == a)
    accuracy = round((correct / total) * 100, 2)
    bot.send_message(chat_id, f"✅ Точность прогнозов: {accuracy}% ({correct} из {total})")

# Последний чат
last_chat_id = None

# Старт и кнопки
@bot.message_handler(commands=["start"])
def start_handler(message):
    global last_chat_id
    last_chat_id = message.chat.id
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📡 Получить сигнал", callback_data="signal"))
    markup.add(types.InlineKeyboardButton("📊 Точность", callback_data="accuracy"))
    markup.add(types.InlineKeyboardButton("📍 Проверка прогноза", callback_data="verify"))
    bot.send_message(message.chat.id, "👋 Добро пожаловать! Выберите действие:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    global last_chat_id
    last_chat_id = call.message.chat.id
    if call.data == "signal":
        send_auto_signal()
    elif call.data == "accuracy":
        show_accuracy(call.message.chat.id)
    elif call.data == "verify":
        verify_predictions(call.message.chat.id)

# Запускаем автообновление в фоне
threading.Thread(target=auto_update, daemon=True).start()

# Запуск бота
bot.polling(none_stop=True)
