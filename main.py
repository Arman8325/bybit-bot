```python
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

# === Взвешенное голосование ===
def make_weighted_prediction(ind_vals, last_close):
    votes = []
    ind = ind_vals
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
    score = sum((weights.get(name,0) if vote=="LONG" else -weights.get(name,0))
                for name, vote in zip(indicators, votes))
    final = "LONG" if score>0 else "SHORT"
    return final, votes

# === Сигнал и база ===
entry_triggered = False
last_summary_date = None

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

# === Проверка прогнозов ===
def verify_predictions(chat_id):
    now = datetime.utcnow()
    cursor.execute("SELECT id,timestamp,price FROM predictions WHERE actual IS NULL")
    upd=0
    for i,ts,p in cursor.fetchall():
        t0=datetime.strptime(ts,"%Y-%m-%d %H:%M:%S")
        if now-t0>=timedelta(minutes=15):
            nc=float(get_candles()[-1][4])
            a="LONG" if nc>p else "SHORT" if nc<p else "NEUTRAL"
            cursor.execute("UPDATE predictions SET actual=? WHERE id=?",(a,i))
            upd+=1
    conn.commit()
    money.send_message(chat_id,f"🔍 Обновлено: {upd}")

# === Точность ===
def show_accuracy(chat_id):
    cursor.execute("SELECT signal,actual FROM predictions WHERE actual IS NOT NULL")
    rows=cursor.fetchall()
    if not rows: return money.send_message(chat_id,"📊 Нет проверенных.")
    total=len(rows);correct=sum(1 for s,a in rows if s==a)
    money.send_message(chat_id,f"✅ Точность: {round(correct/total*100,2)}% ({correct}/{total})")

# === Экспорт CSV/Excel ===
def export_csv(m):
    df=pd.read_sql_query("SELECT * FROM predictions",conn)
    if df.empty: return money.send_message(m.chat.id,"📁 Пусто.")
    buf=BytesIO();df.to_csv(buf,index=False);buf.seek(0)
    money.send_document(m.chat.id,("signals.csv",buf))

def export_excel(m):
    df=pd.read_sql_query("SELECT * FROM predictions",conn)
    if df.empty: return money.send_message(m.chat.id,"📁 Пусто.")
    buf=BytesIO();df.to_excel(buf,index=False,sheet_name="Signals");buf.seek(0)
    money.send_document(m.chat.id,("signals.xlsx",buf))

# === Авто-предсказание 15м ===
def auto_predict():
    while True:
        try:
            process_signal(AUTHORIZED_USER_ID,"15")
            time.sleep(900)
        except:
            time.sleep(900)
threading.Thread(target=auto_predict,daemon=True).start()

# === Авто-вход уведомления ===
def auto_entry_signal():
    global entry_triggered
    while True:
        try:
            raw=get_candles(interval="15")
            df=pd.DataFrame(raw,columns=["timestamp","open","high","low","close","volume","turnover"])
            ind=analyze_indicators(df)
            last=float(df["close"].iloc[-1])
            _,votes=make_weighted_prediction(ind,last)
            can_enter = (ind["RSI"]<30 and last<ind["EMA21"] and votes.count("LONG")/len(votes)>=0.9)
            if can_enter and not entry_triggered:
                et=("🔔 *Точка входа LONG!*\n"+f"Цена: {last}\n"+f"RSI: {round(ind['RSI'],2)}, EMA21: {round(ind['EMA21'],2)}\n"+f"Доля LONG: {votes.count('LONG')}/{len(votes)}")
                money.send_message(AUTHORIZED_USER_ID,et,parse_mode="Markdown")
                entry_triggered=True
            if not can_enter: entry_triggered=False
            time.sleep(60)
        except:
            time.sleep(60)
threading.Thread(target=auto_entry_signal,daemon=True).start()

# === Ежедневный отчёт ===
def daily_summary():
    global last_summary_date
    while True:
        now=datetime.utcnow()
        nr=(now+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
        time.sleep((nr-now).total_seconds())
        ds=(nr-timedelta(days=1)).strftime("%Y-%m-%d")
        if last_summary_date==ds: continue
        last_summary_date=ds
        rows=cursor.execute("SELECT signal,actual FROM predictions WHERE timestamp LIKE ? AND actual IS NOT NULL",(ds+"%",)).fetchall()
        tot=len(rows);corr=sum(1 for s,a in rows if s==a)
        txt=(f"📅 Отчёт за {ds}: Всего {tot}, Попаданий {corr}, Точность {round(corr/tot*100,2)}%" if tot else f"📅 Отчёт за {ds}: нет данных")
        money.send_message(AUTHORIZED_USER_ID,txt)
threading.Thread(target=daily_summary,daemon=True).start()

# === Клавиатура и хендлеры ===

def make_reply_keyboard():
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("15м","30м","1ч")
    kb.row("Проверка","Точность")
    kb.row("Export CSV","Export Excel")
    return kb

@money.message_handler(commands=['start'])
def start(message):
    if message.from_user.id!=AUTHORIZED_USER_ID:
        return money.send_message(message.chat.id,"⛔ Доступ запрещён.")
    money.send_message(message.chat.id,"✅ Бот запущен!",reply_markup=make_reply_keyboard())

@money.message_handler(func=lambda m: m.chat.id==AUTHORIZED_USER_ID)
def handle_buttons(message):
    t=message.text.strip()
    if t=="15м": process_signal(message.chat.id,"15")
    elif t=="30м": process_signal(message.chat.id,"30")
    elif t=="1ч": process_signal(message.chat.id,"60")
    elif t=="Проверка": verify_predictions(message.chat.id)
    elif t=="Точность": show_accuracy(message.chat.id)
    elif t=="Export CSV": export_csv(message)
    elif t=="Export Excel": export_excel(message)
    else: money.send_message(message.chat.id,"ℹ️ Используй клавиатуру.",reply_markup=make_reply_keyboard())

money.polling(none_stop=True)
```
