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
from dotenv import load_dotenv

# === Загрузка окружения ===
load_dotenv()
AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID"))
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

# === Инициализация БД ===
conn = sqlite3.connect("predictions.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    price REAL,
    signal TEXT,
    actual TEXT,
    votes TEXT,
    timeframe TEXT
)
""")
conn.commit()

# === Дедупликация сигналов ===
last_period = {}

# === Утилиты ===
def get_candles(interval="15", limit=100):
    return session.get_kline(category="linear", symbol="BTCUSDT", interval=interval, limit=limit)["result"]["list"]

def analyze_indicators(df):
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["volume"] = df["volume"].astype(float)
    # базовые индикаторы
    inds = {
        "RSI": ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1],
        "EMA21": ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1],
        "EMA100": ta.trend.EMAIndicator(df["close"], window=100).ema_indicator().iloc[-1],
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
    # фонд объема
    inds["VOL_MA20"] = df["volume"].rolling(20).mean().iloc[-1]
    return inds

# === Голосование ===
def make_prediction(ind, last):
    votes = []
    if ind["RSI"] > 60: votes.append("LONG")
    elif ind["RSI"] < 40: votes.append("SHORT")
    votes.append("LONG" if last > ind["EMA21"] else "SHORT")
    if ind["ADX"] > 25: votes.append("LONG")
    if ind["CCI"] > 100: votes.append("LONG")
    elif ind["CCI"] < -100: votes.append("SHORT")
    if ind["Stochastic"] > 80: votes.append("SHORT")
    elif ind["Stochastic"] < 20: votes.append("LONG")
    votes.append("LONG" if ind["Momentum"] > 0 else "SHORT")
    if last > ind["BOLL_UP"]: votes.append("SHORT")
    elif last < ind["BOLL_LOW"]: votes.append("LONG")
    votes.append("LONG" if last > ind["SAR"] else "SHORT")
    votes.append("LONG" if ind["MACD"] > 0 else "SHORT")
    if ind["WR"] < -80: votes.append("LONG")
    elif ind["WR"] > -20: votes.append("SHORT")
    lc, sc = votes.count("LONG"), votes.count("SHORT")
    if lc > sc: return "LONG", votes
    if sc > lc: return "SHORT", votes
    return "NEUTRAL", votes

# === Условие точки входа 100% ===
def is_entry_opportunity(ind, last, votes):
    return votes.count("LONG") == len(votes)

# === Обработка сигнала ===
def process_signal(chat_id, interval):
    raw = get_candles(interval=interval)
    df = pd.DataFrame(raw, columns=["timestamp","open","high","low","close","volume","turnover"])
    # дедупликация по 15‑минутному периоду
    period = int(interval) * 60
    last_ts = int(df["timestamp"].iloc[-1])
    idx = last_ts // period
    if last_period.get(interval) == idx:
        return
    last_period[interval] = idx

    ind = analyze_indicators(df)
    last = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2])
    signal, votes = make_prediction(ind, last)

    # Фильтр по тренду: только в направлении EMA100
    if last > ind["EMA100"] and signal != "LONG": return
    if last < ind["EMA100"] and signal != "SHORT": return
    # Фильтр по объему: текущий объем должен быть >1.5*VOL_MA20
    if df["volume"].iloc[-1] < 1.5 * ind["VOL_MA20"]:
        return

    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO predictions (timestamp, price, signal, actual, votes, timeframe) VALUES (?,?,?,?,?,?)",
        (ts, last, signal, None, ",".join(votes), interval)
    )
    conn.commit()

    # отправка
    text = f"⏱ Таймфрейм: {interval}м\n📈 Закрытие: {last}\n📉 Предыдущее: {prev}\n"
    for k,v in ind.items(): text += f"🔹 {k}: {round(v,2)}\n"
    text += f"\n📌 Прогноз на {interval}м: "
    text += "🔺 LONG" if signal=="LONG" else "🔻 SHORT" if signal=="SHORT" else "⚪️ NEUTRAL"
    text += f"\n🧠 Голоса: {votes}"
    bot.send_message(chat_id, text)

    # точка входа за 1 мин до новой свечи
    now = datetime.utcnow()
    if now.minute % int(interval) == int(interval) - 1 and is_entry_opportunity(ind, last, votes):
        entry = (
            "🔔 *100% Точка входа LONG!*  \n"
            f"Цена: {last}\nГолоса: {votes}"
        )
        bot.send_message(chat_id, entry, parse_mode="Markdown")

# === Проверка, точность, экспорт ===
def verify(chat_id): ...
def accuracy(chat_id): ...
def export_csv(m): ...
def export_excel(m): ...

def make_reply_keyboard(): ...

# === Хендлеры ===
@bot.message_handler(commands=['start'])
def start(m): ...

@bot.message_handler(func=lambda m: m.chat.id==AUTHORIZED_USER_ID)
def handler(m): ...

# === Авто‑прогноз ===
def auto_pred(): ...
threading.Thread(target=auto_pred, daemon=True).start()

# === Ежедневный отчёт ===
def daily_summary(): ...
threading.Thread(target=daily_summary, daemon=True).start()

# === Запуск ===
bot.polling(none_stop=True)
