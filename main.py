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
    timeframe TEXT,
    sl REAL,
    tp REAL
)
""")
conn.commit()

# === Дедупликация уведомлений ===
last_period = {}
# Для калькулятора храним состояние ожидания
user_states = {}

# === Утилиты ===
def get_candles(interval="15", limit=100):
    return session.get_kline(category="linear", symbol="BTCUSDT", interval=interval, limit=limit)["result"]["list"]

def analyze_indicators(df):
    df = df.astype({"close":"float", "high":"float", "low":"float", "volume":"float"})
    return {
        "RSI": ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1],
        "EMA21": ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1],
        "ADX": ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1],
        "CCI": ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1],
        "ATR14": ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=14).average_true_range().iloc[-1]
    }

def make_prediction(ind, last):
    votes = []
    if ind["RSI"] > 60:
        votes.append("LONG")
    elif ind["RSI"] < 40:
        votes.append("SHORT")
    votes.append("LONG" if last > ind["EMA21"] else "SHORT")
    if ind["ADX"] > 25:
        votes.append("LONG")
    if ind["CCI"] > 100:
        votes.append("LONG")
    elif ind["CCI"] < -100:
        votes.append("SHORT")
    lc, sc = votes.count("LONG"), votes.count("SHORT")
    if lc > sc:
        return "LONG", votes
    if sc > lc:
        return "SHORT", votes
    return "NEUTRAL", votes

def is_entry_opportunity(ind, last, votes):
    return votes.count("LONG") == len(votes)

# === Обработка сигнала ===
def process_signal(chat_id, interval, manual=False):
    data = get_candles(interval=interval)
    df = pd.DataFrame(data, columns=["timestamp","open","high","low","close","volume","turnover"])
    period = int(interval) * 60
    idx = int(df["timestamp"].iloc[-1]) // period
    if not manual and last_period.get(interval) == idx:
        return
    if not manual:
        last_period[interval] = idx

    ind_cur = analyze_indicators(df)
    last = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2])
    signal, votes = make_prediction(ind_cur, last)

    higher_map = {"15":"60", "30":"240", "60":"240"}
    higher_tf = higher_map.get(interval)
    if higher_tf and not manual:
        hdata = get_candles(interval=higher_tf)
        hdf = pd.DataFrame(hdata, columns=["timestamp","open","high","low","close","volume","turnover"])
        ind_high = analyze_indicators(hdf)
        if signal == "LONG" and last < ind_high["EMA21"]:
            return
        if signal == "SHORT" and last > ind_high["EMA21"]:
            return

    if not manual:
        candle_range = df["high"].iloc[-1] - df["low"].iloc[-1]
        if candle_range < ind_cur["ATR14"]:
            return

    atr = ind_cur["ATR14"]
    if signal == "LONG":
        sl = last - atr
        tp = last + 2 * atr
    elif signal == "SHORT":
        sl = last + atr
        tp = last - 2 * atr
    else:
        sl = tp = None

    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO predictions (timestamp, price, signal, actual, votes, timeframe, sl, tp) VALUES (?,?,?,?,?,?,?,?)",
        (ts, last, signal, None, ",".join(votes), interval, sl, tp)
    )
    conn.commit()

    text = f"⏱ Таймфрейм: {interval}м\n"
    text += f"📈 Закрытие: {last}  (SL={round(sl,2) if sl else '-'}, TP={round(tp,2) if tp else '-'})\n"
    text += f"📉 Предыдущее: {prev}\n"
    text += f"🔹 RSI: {round(ind_cur['RSI'],2)}, EMA21: {round(ind_cur['EMA21'],2)}\n"
    if higher_tf:
        text += f"🔹 Старший ТФ {higher_tf}м EMA21: {round(ind_high['EMA21'],2)}\n"
    text += f"🔹 ATR14: {round(atr,2)}\n"
    text += f"\n📌 Прогноз: {('🔺 LONG' if signal=='LONG' else '🔻 SHORT' if signal=='SHORT' else '⚪️ NEUTRAL')}\n"
    text += f"🧠 Голоса: {votes}\n"
    bot.send_message(chat_id, text)

    now = datetime.utcnow()
    if now.minute % int(interval) == int(interval)-1 and is_entry_opportunity(ind_cur, last, votes):
        entry = f"🔔 *Точка входа {signal}! SL={round(sl,2) if sl else '-'} TP={round(tp,2) if tp else '-'}*"
        bot.send_message(chat_id, entry, parse_mode="Markdown")

# === Калькулятор прибыли с плечом ===
@bot.message_handler(regexp=r"^Калькулятор$")
def start_calculator(m):
    if m.from_user.id != AUTHORIZED_USER_ID:
        return
    user_states[m.chat.id] = 'await_calc'
    bot.send_message(
        m.chat.id,
        "Введите баланс, цену входа, цену цели и плечо через пробел, например:
`100 20000 20100 10`"
        , parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: user_states.get(m.chat.id)=='await_calc')
def calculator(m):
    try:
        parts = m.text.split()
        if len(parts) != 4:
            raise ValueError
        bal, price_in, price_tp, lev = parts
        bal = float(bal)
        price_in = float(price_in)
        price_tp = float(price_tp)
        lev = float(lev)
        profit_pct = (price_tp - price_in) / price_in * 100
        profit_usd = bal * lev * profit_pct / 100
        bot.send_message(
            m.chat.id,
            f"При плече {int(lev)}×: Прибыль составит {round(profit_usd,2)} USD (~{round(profit_pct,2)}%)"
        )
    except:
        bot.send_message(m.chat.id, "Неверный формат. Введите четыре числа через пробел: баланс, цена входа, цена цели, плечо.")
        return
    user_states.pop(m.chat.id, None)

# === Остальные функции и хендлеры (Проверка, Точность, Экспорт, кнопки) остаются без изменений === (Проверка, Точность, Экспорт, кнопки) остаются без изменений ===

bot.polling(none_stop=True)
