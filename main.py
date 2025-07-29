import telebot
from telebot import types
import os
import pandas as pd
from io import BytesIO
from pybit.unified_trading import HTTP
from datetime import datetime, timedelta
import ta
import sqlite3
import threading
import time
import csv
from dotenv import load_dotenv

# === Загрузка окружения ===
load_dotenv()
AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID"))
money = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

# === Инициализация БД ===
conn = sqlite3.connect("predictions.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute(
"""
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    price REAL,
    signal TEXT,
    actual TEXT,
    votes TEXT,
    timeframe TEXT
)"""
)
conn.commit()

# === Загрузка весов индикаторов ===
weights = {}
with open("indicator_weights.csv", newline="") as f:
    for row in csv.DictReader(f):
        weights[row["indicator"]] = float(row["weight"])

# Фиксированный порядок индикаторов
indicators = [
    "RSI","EMA21","ADX","CCI","Stochastic",
    "Momentum","BOLL_UP","BOLL_LOW","SAR","MACD","WR"
]

# === Утилиты ===
def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    return session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)["result"]["list"]

def analyze_indicators(df):
    df["close"] = df["close"].astype(float)
    df["high"]  = df["high"].astype(float)
    df["low"]   = df["low"].astype(float)
    return {
        "RSI": ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1],
        "EMA21": ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1],
        "ADX": ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1],
        "CCI": ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1],
        "Stochastic": ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"]).stoch().iloc[-1],
        "Momentum": ta.momentum.ROCIndicator(df["close"]).roc().iloc[-1],
        "BOLL_UP": ta.volatility.BollingerBands(df["close"]).bollinger_hband().iloc[-1],
        "BOLL_LOW": ta.volatility.BollingerBands(df["close"]).bollinger_lband().iloc[-1],
        "SAR": ta.trend.PSARIndicator(df["high"], df["low"], df["close"]).psar().iloc[-1],
        "MACD": ta.trend.MACD(df["close"]).macd().iloc[-1],
        "WR": ta.momentum.WilliamsRIndicator(df["high"], df["low"], df["close"]).williams_r().iloc[-1]
    }

def make_weighted_prediction(ind_vals, last_close):
    votes = []
    if ind_vals["RSI"] > 60: votes.append("LONG")
    elif ind_vals["RSI"] < 40: votes.append("SHORT")
    votes.append("LONG" if last_close > ind_vals["EMA21"] else "SHORT")
    if ind_vals["ADX"] > 25: votes.append("LONG")
    if ind_vals["CCI"] > 100: votes.append("LONG")
    elif ind_vals["CCI"] < -100: votes.append("SHORT")
    if ind_vals["Stochastic"] > 80: votes.append("SHORT")
    elif ind_vals["Stochastic"] < 20: votes.append("LONG")
    votes.append("LONG" if ind_vals["Momentum"] > 0 else "SHORT")
    if last_close > ind_vals["BOLL_UP"]: votes.append("SHORT")
    elif last_close < ind_vals["BOLL_LOW"]: votes.append("LONG")
    votes.append("LONG" if last_close > ind_vals["SAR"] else "SHORT")
    votes.append("LONG" if ind_vals["MACD"] > 0 else "SHORT")
    if ind_vals["WR"] < -80: votes.append("LONG")
    elif ind_vals["WR"] > -20: votes.append("SHORT")
    score = sum((weights.get(name,0) if vote=="LONG" else -weights.get(name,0))
                for name, vote in zip(indicators, votes))
    final = "LONG" if score>0 else "SHORT"
    return final, votes

# === Обработка сигнала ===
def process_signal(chat_id, interval):
    raw = get_candles(interval=interval)
    df = pd.DataFrame(raw, columns=["timestamp","open","high","low","close","volume","turnover"])
    ind_vals = analyze_indicators(df)
    last = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2])
    signal, votes = make_weighted_prediction(ind_vals, last)
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO predictions (timestamp, price, signal, actual, votes, timeframe) VALUES (?,?,?,?,?,?)",
        (ts, last, signal, None, ",".join(votes), interval)
    )
    conn.commit()
    text = f"📈 Закрытие: {last}\n📉 Предыдущее: {prev}\n"
    for k,v in ind_vals.items(): text+=f"🔹 {k}: {round(v,2)}\n"
    text+=f"\n📌 Сигнал: {'🔺 LONG' if signal=='LONG' else '🔻 SHORT'}"
    text+=f"\n🧠 Голоса: {votes}"
    money.send_message(chat_id, text)

# === Хендлер команды /start ===
@money.message_handler(commands=['start'])
def start_handler(message):
    if message.from_user.id != AUTHORIZED_USER_ID:
        return money.send_message(message.chat.id, "⛔ У вас нет доступа.")
    money.send_message(message.chat.id, "✅ Бот запущен! Используйте клавиатуру ниже.",
                       reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True)
                                      .row("15м","30м","1ч")
                                      .row("Проверка","Точность")
                                      .row("Export CSV","Export Excel"))

# === Обработка текстовых кнопок ===
@money.message_handler(func=lambda m: m.chat.id==AUTHORIZED_USER_ID)
def text_handler(message):
    cmd = message.text.strip()
    if cmd == "15м": process_signal(message.chat.id, "15")
    elif cmd == "30м": process_signal(message.chat.id, "30")
    elif cmd == "1ч": process_signal(message.chat.id, "60")
    elif cmd == "Проверка": verify_predictions(message.chat.id)
    elif cmd == "Точность": show_accuracy(message.chat.id)
    elif cmd == "Export CSV": export_csv(message)
    elif cmd == "Export Excel": export_excel(message)
    else:
        money.send_message(message.chat.id, "ℹ️ Используйте клавиатуру.")

# === Остальные хендлеры (verify_predictions, show_accuracy, export_csv, export_excel) ===
# ... реализованы аналогично, с money.send_message/document ...

# === Запуск поллинга ===
money.polling(none_stop=True)
```

