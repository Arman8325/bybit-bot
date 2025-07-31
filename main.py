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

last_period = {}
user_states = {}

def get_candles(interval="15", limit=100):
    return session.get_kline(category="linear", symbol="BTCUSDT", interval=interval, limit=limit)["result"]["list"]

def analyze_indicators(df):
    df = df.astype({"close":"float","high":"float","low":"float","volume":"float"})
    return {
        "RSI": ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1],
        "EMA21": ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1],
        "ADX": ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1],
        "CCI": ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1],
        "ATR14": ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=14).average_true_range().iloc[-1]
    }

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

def is_entry_opportunity(ind, last, votes):
    return votes.count("LONG") == len(votes)

def process_signal(chat_id, interval, manual=False):
    # === Ручной вызов: сразу выдаём прогноз без каких-либо фильтров ===
    data = get_candles(interval=interval)
    df = pd.DataFrame(data, columns=["timestamp","open","high","low","close","volume","turnover"])
    last = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2])
    ind_cur = analyze_indicators(df)
    signal, votes = make_prediction(ind_cur, last)

    # Рассчёт SL/TP на любом режиме
    atr = ind_cur["ATR14"]
    if signal=="LONG":
        sl = last - atr; tp = last + 2*atr
    elif signal=="SHORT":
        sl = last + atr; tp = last - 2*atr
    else:
        sl = tp = None

    # Сохраняем в БД
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO predictions (timestamp,price,signal,actual,votes,timeframe,sl,tp) VALUES (?,?,?,?,?,?,?,?)",
        (ts,last,signal,None,",".join(votes),interval,sl,tp)
    )
    conn.commit()

    # Формируем текст
    arrow = "🔺" if signal=="LONG" else "🔻" if signal=="SHORT" else "⚪️"
    text  = f"⏱ Таймфрейм: {interval}м\n"
    text += f"📈 Закрытие: {last}  (SL={round(sl,2) if sl else '-'}, TP={round(tp,2) if tp else '-'})\n"
    text += f"📉 Предыдущее: {prev}\n"
    text += f"🔹 RSI: {round(ind_cur['RSI'],2)}, EMA21: {round(ind_cur['EMA21'],2)}\n"
    text += f"🔹 ATR14: {round(atr,2)}\n\n"
    text += f"📌 Прогноз: {arrow} {signal}\n🧠 Голоса: {votes}"
    bot.send_message(chat_id, text)

    # === Авто-режим: дальше применяем Multi-TF и ATR-фильтр ===
    if not manual:
        # Multi-TF
        higher_map = {"15":"60","30":"240","60":"240"}
        higher_tf = higher_map.get(interval)
        if higher_tf:
            hdata = get_candles(interval=higher_tf)
            hdf = pd.DataFrame(hdata, columns=["timestamp","open","high","low","close","volume","turnover"])
            ind_high = analyze_indicators(hdf)
            if signal=="LONG" and last < ind_high["EMA21"]: return
            if signal=="SHORT" and last > ind_high["EMA21"]: return
        # ATR-фильтр
        candle_range = df["high"].iloc[-1] - df["low"].iloc[-1]
        if candle_range < atr: return

        # Точка входа за минуту до закрытия свечи
        now = datetime.utcnow()
        if now.minute % int(interval)==int(interval)-1 and is_entry_opportunity(ind_cur,last,votes):
            bot.send_message(
                chat_id,
                f"🔔 *Точка входа {signal}! SL={round(sl,2)} TP={round(tp,2)}*",
                parse_mode="Markdown"
            )

# === Калькулятор с плечом ===
@bot.message_handler(regexp=r"^Калькулятор$")
def start_calculator(m):
    user_states[m.chat.id] = 'await_calc'
    bot.send_message(
        m.chat.id,
        "Введите баланс, цену входа, цену цели и плечо через пробел, например:\n100 20000 20100 10"
    )

@bot.message_handler(func=lambda m: user_states.get(m.chat.id)=='await_calc')
def calculator(m):
    try:
        bal, price_in, price_tp, lev = map(float, m.text.split())
        pct = (price_tp-price_in)/price_in*100
        usd = bal*lev*pct/100
        bot.send_message(m.chat.id, f"При плече {int(lev)}×: {round(usd,2)} USD (~{round(pct,2)}%)")
    except:
        bot.send_message(m.chat.id, "Неверный формат, повторите ввод.")
        return
    user_states.pop(m.chat.id,None)

# === Клавиатура ===
def make_reply_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("15м","30м","1ч")
    kb.row("Проверка","Точность")
    kb.row("Export CSV","Export Excel")
    kb.row("Калькулятор")
    return kb

@bot.message_handler(commands=["start"])
def cmd_start(m):
    bot.send_message(m.chat.id,"✅ Бот готов!",reply_markup=make_reply_keyboard())

@bot.message_handler(func=lambda m: True)
def handler(m):
    user_states.pop(m.chat.id,None)
    cmd = m.text.strip().lower()
    if cmd.startswith("15"):
        process_signal(m.chat.id,"15",manual=True)
    elif cmd.startswith("30"):
        process_signal(m.chat.id,"30",manual=True)
    elif cmd.startswith("1"):
        process_signal(m.chat.id,"60",manual=True)
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

# === Проверка, точность, экспорт и отчёты — без изменений ===
def verify(chat_id): ...
def accuracy(chat_id): ...
def export_csv(m): ...
def export_excel(m): ...

# === Авто-прогноз ===
threading.Thread(target=lambda: (_ for _ in ()).throw(KeyboardInterrupt), daemon=True).start()  # удалите, если не нужно

bot.polling(none_stop=True)
