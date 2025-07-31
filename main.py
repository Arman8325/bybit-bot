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

# === Состояния и дедупликация ===
last_period = {}
user_states = {}

# === Утилиты ===
def get_candles(interval="15", limit=100):
    resp = session.get_kline(category="linear", symbol="BTCUSDT", interval=interval, limit=limit)
    return resp["result"]["list"]

# === Индикаторы ===
def analyze_indicators(df):
    df = df.astype({"close":"float","high":"float","low":"float"})
    return {
        "RSI": ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1],
        "EMA21": ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1],
        "ADX": ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1],
        "CCI": ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1],
        "ATR14": ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=14).average_true_range().iloc[-1]
    }

# === Формируем голосование ===
def make_prediction(ind, last):
    votes = []
    if ind["RSI"] > 60: votes.append("LONG")
    elif ind["RSI"] < 40: votes.append("SHORT")
    votes.append("LONG" if last > ind["EMA21"] else "SHORT")
    if ind["ADX"] > 25: votes.append("LONG")
    if ind["CCI"] > 100: votes.append("LONG")
    elif ind["CCI"] < -100: votes.append("SHORT")
    lc, sc = votes.count("LONG"), votes.count("SHORT")
    if lc > sc: return "LONG", votes
    if sc > lc: return "SHORT", votes
    return "NEUTRAL", votes

# === Условие точки входа (100%) ===
def is_entry_opportunity(ind, last, votes):
    return votes.count("LONG") == len(votes)

# === Основная обработка сигнала ===
def process_signal(chat_id, interval, manual=False):
    # --- базовый прогноз (всегда отправляем) ---
    data = get_candles(interval=interval)
    df = pd.DataFrame(data, columns=["timestamp","open","high","low","close","volume","turnover"])
    last = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2])
    ind_cur = analyze_indicators(df)
    signal, votes = make_prediction(ind_cur, last)

    # считаем SL/TP
    atr = ind_cur["ATR14"]
    if signal == "LONG":
        sl = last - atr; tp = last + 2*atr
    elif signal == "SHORT":
        sl = last + atr; tp = last - 2*atr
    else:
        sl = tp = None

    # сохраняем
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO predictions (timestamp,price,signal,actual,votes,timeframe,sl,tp) VALUES (?,?,?,?,?,?,?,?)",
        (ts, last, signal, None, ",".join(votes), interval, sl, tp)
    )
    conn.commit()

    # отправляем базовый прогноз
    arrow = "🔺" if signal=="LONG" else "🔻" if signal=="SHORT" else "⚪️"
    text = (
        f"⏱ Таймфрейм: {interval}м    {arrow} {signal}\n"
        f"📈 Закрытие: {last}  (SL={round(sl,2) if sl else '-'}  TP={round(tp,2) if tp else '-'})\n"
        f"📉 Предыдущее: {prev}\n"
        f"🔹 RSI: {round(ind_cur['RSI'],2)}, EMA21: {round(ind_cur['EMA21'],2)}, ATR14: {round(atr,2)}\n"
        f"🧠 Голоса: {votes}"
    )
    bot.send_message(chat_id, text)

    # если ручной запрос — сразу выходим, фильтры не применяются
    if manual:
        return

    # --- авто-режим: привязка к границе свечи ---
    now = datetime.utcnow()
    rem = now.minute % int(interval)
    wait = (int(interval) - rem)*60 - now.second
    if wait > 0:
        time.sleep(wait)

    # после границы снова берём данные
    df2 = pd.DataFrame(get_candles(interval=interval), columns=df.columns)
    last2 = float(df2["close"].iloc[-1])

    # Multi-TF EMA21
    higher_map = {"15":"60", "30":"240", "60":"240"}
    higher_tf = higher_map.get(interval)
    if higher_tf:
        hdf = pd.DataFrame(get_candles(interval=higher_tf),
                           columns=["timestamp","open","high","low","close","volume","turnover"])
        ind_high = analyze_indicators(hdf)
        if (signal=="LONG" and last2 < ind_high["EMA21"]) or \
           (signal=="SHORT" and last2 > ind_high["EMA21"]):
            return

    # ATR-фильтр
    candle_range = float(df2["high"].iloc[-1]) - float(df2["low"].iloc[-1])
    if candle_range < ind_cur["ATR14"]:
        return

    # точка входа
    if is_entry_opportunity(ind_cur, last2, votes):
        bot.send_message(
            chat_id,
            f"🔔 *Точка входа {signal}! SL={round(sl,2)}  TP={round(tp,2)}*",
            parse_mode="Markdown"
        )

# === Калькулятор прибыли с плечом ===
@bot.message_handler(regexp=r"^Калькулятор$")
def start_calculator(m):
    user_states[m.chat.id] = 'await_calc'
    bot.send_message(m.chat.id, "Введите три числа + плечо: баланс, вход, цель, плечо")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id)=='await_calc')
def calculator(m):
    try:
        bal, price_in, price_tp, lev = map(float, m.text.split())
        pct = (price_tp - price_in)/price_in*100
        usd = bal * lev * pct / 100
        bot.send_message(m.chat.id, f"При плече {int(lev)}×: {round(usd,2)} USD (~{round(pct,2)}%)")
    except:
        bot.send_message(m.chat.id, "Формат: баланс вход цель плечо")
        return
    user_states.pop(m.chat.id, None)

# === Клавиатура ===
def make_reply_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("15м","30м","1ч")
    kb.row("Проверка","Точность")
    kb.row("Export CSV","Export Excel")
    kb.row("Калькулятор")
    return kb

# === /start ===
@bot.message_handler(commands=["start"])
def cmd_start(m):
    if m.from_user.id != AUTHORIZED_USER_ID:
        return bot.send_message(m.chat.id,"⛔ Нет доступа")
    bot.send_message(m.chat.id,"✅ Бот готов!", reply_markup=make_reply_keyboard())

# === Общий хендлер ===
@bot.message_handler(func=lambda m: m.chat.id==AUTHORIZED_USER_ID)
def handler(m):
    user_states.pop(m.chat.id, None)
    cmd = m.text.strip().lower()
    if cmd.startswith("15"):
        process_signal(m.chat.id, "15", manual=True)
    elif cmd.startswith("30"):
        process_signal(m.chat.id, "30", manual=True)
    elif cmd.startswith("1"):
        process_signal(m.chat.id, "60", manual=True)
    elif cmd=="проверка":
        verify(m.chat.id)
    elif cmd=="точность":
        accuracy(m.chat.id)
    elif cmd=="export csv":
        export_csv(m)
    elif cmd=="export excel":
        export_excel(m)
    elif cmd=="калькулятор":
        start_calculator(m)
    else:
        bot.send_message(m.chat.id,"ℹ️ Используйте кнопки.",reply_markup=make_reply_keyboard())

# === Проверка / Точность / Экспорт / Ежедневный отчёт ===
def verify(chat_id):
    now = datetime.utcnow()
    cursor.execute("SELECT id,timestamp,price FROM predictions WHERE actual IS NULL")
    cnt = 0
    for _id, ts, price in cursor.fetchall():
        dt = datetime.strptime(ts,"%Y-%m-%d %H:%M:%S")
        if now - dt >= timedelta(minutes=15):
            nc = float(get_candles(interval="15")[-1][4])
            actual = "LONG" if nc>price else "SHORT" if nc<price else "NEUTRAL"
            cursor.execute("UPDATE predictions SET actual=? WHERE id=?", (actual,_id))
            cnt += 1
    conn.commit()
    bot.send_message(chat_id, f"🔍 Обновлено: {cnt}")

def accuracy(chat_id):
    cursor.execute("SELECT signal,actual FROM predictions WHERE actual IS NOT NULL")
    rows = cursor.fetchall()
    if not rows:
        return bot.send_message(chat_id,"📊 Нет проверенных")
    tot = len(rows)
    corr = sum(1 for s,a in rows if s==a)
    bot.send_message(chat_id, f"✅ Точность: {round(corr/tot*100,2)}% ({corr}/{tot})")

def export_csv(m):
    df = pd.read_sql_query("SELECT * FROM predictions",conn)
    if df.empty:
        return bot.send_message(m.chat.id,"📁 Нет данных")
    buf = BytesIO(); df.to_csv(buf,index=False); buf.seek(0)
    bot.send_document(m.chat.id,("signals.csv",buf))

def export_excel(m):
    df = pd.read_sql_query("SELECT * FROM predictions",conn)
    if df.empty:
        return bot.send_message(m.chat.id,"📁 Нет данных")
    buf = BytesIO(); df.to_excel(buf,index=False,sheet_name="Signals"); buf.seek(0)
    bot.send_document(m.chat.id,("signals.xlsx",buf))

# === Поток авто-прогноза не нужен, все внутри process_signal ===

bot.polling(none_stop=True)
