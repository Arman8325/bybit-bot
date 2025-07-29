import telebot
from telebot import types
import os
import re
import pandas as pd
from io import BytesIO
from pybit.unified_trading import HTTP
from datetime import datetime, timedelta
import ta
import sqlite3
import threading
import time
from dotenv import load_dotenv

# === Загрузка переменных окружения ===
load_dotenv()
AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID"))
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

# === БД SQLite ===
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

# === Получить свечи ===
def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    data = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
    return data["result"]["list"]

# === Анализ индикаторов ===
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

# === Голосование индикаторов ===
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
    lc = votes.count("LONG")
    sc = votes.count("SHORT")
    if lc > sc: return "LONG", votes
    if sc > lc: return "SHORT", votes
    return "NEUTRAL", votes

# === Условия лучшей точки входа (90%) ===
def is_entry_opportunity(ind, last_close, votes):
    # 1) RSI < 30
    if ind["RSI"] >= 30: return False
    # 2) цена < EMA21
    if last_close >= ind["EMA21"]: return False
    # 3) доля LONG ≥ 0.9
    if votes.count("LONG") / len(votes) < 0.9: return False
    return True

# === Обработка и отправка сигнала ===
def process_signal(chat_id, interval):
    raw = get_candles(interval=interval)
    df = pd.DataFrame(raw, columns=["timestamp","open","high","low","close","volume","turnover"])
    ind = analyze_indicators(df)
    last = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2])
    signal, votes = make_prediction(ind, last)

    # сохранить в БД
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO predictions (timestamp, price, signal, actual, votes, timeframe) VALUES (?,?,?,?,?,?)",
        (ts, last, signal, None, ",".join(votes), interval)
    )
    conn.commit()

    # текст сигнала
    text = f"📈 Закрытие: {last}\n📉 Предыдущее: {prev}\n"
    for k,v in ind.items():
        text += f"🔹 {k}: {round(v,2)}\n"
    text += f"\n📌 Прогноз: {'🔺 LONG' if signal=='LONG' else '🔻 SHORT' if signal=='SHORT' else '⚪️ NEUTRAL'}"
    text += f"\n🧠 Голоса: {votes}"
    bot.send_message(chat_id, text)

    # точка входа при 90% LONG
    if is_entry_opportunity(ind, last, votes):
        entry = (
            "🔔 *Точка входа LONG!* \n"
            f"Цена: {last}\nRSI: {round(ind['RSI'],2)}, EMA21: {round(ind['EMA21'],2)}\n"
            f"Доля LONG: {votes.count('LONG')}/{len(votes)} (≥90%)"
        )
        bot.send_message(chat_id, entry, parse_mode="Markdown")

# === Клавиатура ===
def make_reply_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("15м","30м","1ч")
    kb.row("Проверка","Точность")
    kb.row("Export CSV","Export Excel")
    return kb

@bot.message_handler(commands=['start'])
def start(m):
    if m.from_user.id != AUTHORIZED_USER_ID:
        return bot.send_message(m.chat.id, "⛔ У вас нет доступа.")
    bot.send_message(m.chat.id, "✅ Бот запущен!", reply_markup=make_reply_keyboard())

@bot.message_handler(func=lambda m: m.chat.id==AUTHORIZED_USER_ID)
def handler(m):
    t=m.text.strip()
    if t=="15м": process_signal(m.chat.id,"15")
    elif t=="30м": process_signal(m.chat.id,"30")
    elif t=="1ч": process_signal(m.chat.id,"60")
    elif t=="Проверка": verify(m.chat.id)
    elif t=="Точность": accuracy(m.chat.id)
    elif t=="Export CSV": export_csv(m)
    elif t=="Export Excel": export_excel(m)
    else: bot.send_message(m.chat.id,"ℹ️ Используй клавиатуру.",reply_markup=make_reply_keyboard())

# === Проверка ===
def verify(chat_id):
    now=datetime.utcnow()
    cursor.execute("SELECT id,timestamp,price FROM predictions WHERE actual IS NULL")
    upd=0
    for i,ts,p in cursor.fetchall():
        if now - datetime.strptime(ts,"%Y-%m-%d %H:%M:%S") >= timedelta(minutes=15):
            nc=float(get_candles()[-1][4])
            a="LONG" if nc>p else "SHORT" if nc<p else "NEUTRAL"
            cursor.execute("UPDATE predictions SET actual=? WHERE id=?",(a,i))
            upd+=1
    conn.commit()
    bot.send_message(chat_id,f"🔍 Обновлено: {upd}")

# === Точность ===
def accuracy(chat_id):
    cursor.execute("SELECT signal,actual FROM predictions WHERE actual IS NOT NULL")
    rows=cursor.fetchall()
    if not rows: return bot.send_message(chat_id,"📊 Нет проверенных.")
    total=len(rows); correct=sum(1 for s,a in rows if s==a)
    bot.send_message(chat_id,f"✅ Точность: {round(correct/total*100,2)}% ({correct}/{total})")

# === Экспорт ===
def export_csv(m):
    df=pd.read_sql("SELECT * FROM predictions",conn)
    if df.empty: return bot.send_message(m.chat.id,"📁 Пусто.")
    buf=BytesIO(); df.to_csv(buf,index=False); buf.seek(0)
    bot.send_document(m.chat.id,("signals.csv",buf))

def export_excel(m):
    df=pd.read_sql("SELECT * FROM predictions",conn)
    if df.empty: return bot.send_message(m.chat.id,"📁 Пусто.")
    buf=BytesIO(); df.to_excel(buf,index=False,sheet_name="Signals"); buf.seek(0)
    bot.send_document(m.chat.id,("signals.xlsx",buf))

# === Авто‑предсказания 15м ===
def auto_pred():
    while True:
        try:
            process_signal(AUTHORIZED_USER_ID,"15")
            time.sleep(900)
        except:
            time.sleep(900)
threading.Thread(target=auto_pred,daemon=True).start()

# === Ежедневный отчёт ===
last_date=None
def daily():
    global last_date
    while True:
        now=datetime.utcnow()
        nr=(now+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
        time.sleep((nr-now).total_seconds())
        ds=(nr-timedelta(days=1)).strftime("%Y-%m-%d")
        if last_date==ds: continue
        last_date=ds
        rows=cursor.execute("SELECT signal,actual FROM predictions WHERE timestamp LIKE ? AND actual IS NOT NULL",(ds+"%",)).fetchall()
        tot=len(rows); corr=sum(1 for s,a in rows if s==a)
        text=f"📅 Отчёт за {ds}: Всего {tot}, Попаданий {corr}, Точность {round(corr/tot*100,2)}%" if tot else f"📅 Отчёт за {ds}: нет данных"
        bot.send_message(AUTHORIZED_USER_ID,text)

threading.Thread(target=daily,daemon=True).start()
bot.polling(none_stop=True)
