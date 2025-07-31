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
    return session.get_kline(category="linear", symbol="BTCUSDT", interval=interval, limit=limit)["result"]["list"]

# === Индикаторы ===
def analyze_indicators(df):
    df = df.astype({"close":"float","high":"float","low":"float","volume":"float"})
    return {
        "RSI": ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1],
        "EMA21": ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1],
        "ADX": ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1],
        "CCI": ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1],
        "ATR14": ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=14).average_true_range().iloc[-1]
    }

# === Голосуем сигнал ===
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

# === Условие 100% входа ===
def is_entry_opportunity(ind, last, votes):
    return votes.count("LONG") == len(votes)

# === Основная обработка сигнала ===
def process_signal(chat_id, interval, manual=False):
    data = get_candles(interval=interval)
    df = pd.DataFrame(data, columns=["timestamp","open","high","low","close","volume","turnover"])
    # дедуп участкового сигнала
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

    # Multi-TF EMA21: 15→60, 30→240, 60→240
    higher_map = {"15":"60","30":"240","60":"240"}
    higher_tf = higher_map.get(interval)
    if higher_tf and not manual:
        hdata = get_candles(interval=higher_tf)
        hdf = pd.DataFrame(hdata, columns=["timestamp","open","high","low","close","volume","turnover"])
        ind_high = analyze_indicators(hdf)
        if signal=="LONG" and last < ind_high["EMA21"]: return
        if signal=="SHORT" and last > ind_high["EMA21"]: return

    # ATR-фильтр
    if not manual:
        candle_range = df["high"].iloc[-1] - df["low"].iloc[-1]
        if candle_range < ind_cur["ATR14"]: return

    # SL/TP
    atr = ind_cur["ATR14"]
    if signal=="LONG":
        sl = last - atr; tp = last + 2*atr
    elif signal=="SHORT":
        sl = last + atr; tp = last - 2*atr
    else:
        sl = tp = None

    # запись
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO predictions (timestamp,price,signal,actual,votes,timeframe,sl,tp) VALUES (?,?,?,?,?,?,?,?)",
        (ts,last,signal,None,",".join(votes),interval,sl,tp)
    )
    conn.commit()

    # текст
    text  = f"⏱ Таймфрейм: {interval}м\n"
    text += f"📈 Закрытие: {last}  (SL={round(sl,2) if sl else '-'}, TP={round(tp,2) if tp else '-'})\n"
    text += f"📉 Предыдущее: {prev}\n"
    text += f"🔹 RSI: {round(ind_cur['RSI'],2)}, EMA21: {round(ind_cur['EMA21'],2)}\n"
    if higher_tf:
        text += f"🔹 EMA21 {higher_tf}м: {round(ind_high['EMA21'],2)}\n"
    text += f"🔹 ATR14: {round(atr,2)}\n\n"
    arrow = "🔺" if signal=="LONG" else "🔻" if signal=="SHORT" else "⚪️"
    text += f"📌 Прогноз: {arrow} {signal}\n🧠 Голоса: {votes}"
    bot.send_message(chat_id, text)

    # вход-уведомление за 1 мин
    now = datetime.utcnow()
    if now.minute % int(interval)==int(interval)-1 and is_entry_opportunity(ind_cur,last,votes):
        bot.send_message(
            chat_id,
            f"🔔 *Точка входа {signal}! SL={round(sl,2) if sl else '-'} TP={round(tp,2) if tp else '-'}*",
            parse_mode="Markdown"
        )

# === Калькулятор с плечом ===
@bot.message_handler(regexp=r"^Калькулятор$")
def start_calculator(m):
    if m.from_user.id!=AUTHORIZED_USER_ID: return
    user_states[m.chat.id] = 'await_calc'
    bot.send_message(
        m.chat.id,
        "Введите баланс, цену входа, цену цели и плечо через пробел, например:\n`100 20000 20100 10`",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: user_states.get(m.chat.id)=='await_calc')
def calculator(m):
    try:
        bal, price_in, price_tp, lev = map(float, m.text.split())
        profit_pct = (price_tp-price_in)/price_in*100
        profit_usd = bal*lev*profit_pct/100
        bot.send_message(
            m.chat.id,
            f"При плече {int(lev)}×: Прибыль {round(profit_usd,2)} USD (~{round(profit_pct,2)}%)"
        )
    except:
        bot.send_message(m.chat.id, "Неверный формат. Введите: баланс, вход, цель, плечо.")
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

# === /start ===
@bot.message_handler(commands=["start"])
def cmd_start(m):
    if m.from_user.id!=AUTHORIZED_USER_ID:
        return bot.send_message(m.chat.id,"⛔ У вас нет доступа.")
    bot.send_message(m.chat.id,"✅ Бот готов!",reply_markup=make_reply_keyboard())

# === Общий хендлер ===
@bot.message_handler(func=lambda m: m.chat.id==AUTHORIZED_USER_ID)
def handler(m):
    # выход из калькулятора при любом нажатии
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

# === Проверка и отчёты ===
def verify(chat_id):
    # ... ваш код без изменений

def accuracy(chat_id):
    # ... ваш код без изменений

def export_csv(m):
    # ... ваш код без изменений

def export_excel(m):
    # ... ваш код без изменений

# === Авто-прогноз 15м ===
def auto_pred():
    while True:
        try:
            process_signal(AUTHORIZED_USER_ID,"15")
            time.sleep(900)
        except:
            time.sleep(900)
threading.Thread(target=auto_pred,daemon=True).start()

# === Ежедневный отчёт ===
def daily_summary():
    # ... ваш код без изменений
threading.Thread(target=daily_summary,daemon=True).start()

bot.polling(none_stop=True)
