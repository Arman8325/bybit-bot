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

# === Получить свечи ===
def get_candles(interval="15", limit=100):
    return session.get_kline(category="linear", symbol="BTCUSDT", interval=interval, limit=limit)["result"]["list"]

# === Анализ индикаторов ===
def analyze_indicators(df):
    df = df.astype({'close':'float','high':'float','low':'float'})
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

# === Собираем голоса ===
def make_prediction(ind, last):
    votes=[]
    if ind["RSI"]>60: votes.append("LONG")
    elif ind["RSI"]<40: votes.append("SHORT")
    votes.append("LONG" if last>ind["EMA21"] else "SHORT")
    if ind["ADX"]>25: votes.append("LONG")
    if ind["CCI"]>100: votes.append("LONG")
    elif ind["CCI"]<-100: votes.append("SHORT")
    if ind["Stochastic"]>80: votes.append("SHORT")
    elif ind["Stochastic"]<20: votes.append("LONG")
    votes.append("LONG" if ind["Momentum"]>0 else "SHORT")
    if last>ind["BOLL_UP"]: votes.append("SHORT")
    elif last<ind["BOLL_LOW"]: votes.append("LONG")
    votes.append("LONG" if last>ind["SAR"] else "SHORT")
    votes.append("LONG" if ind["MACD"]>0 else "SHORT")
    if ind["WR"]<-80: votes.append("LONG")
    elif ind["WR"]>-20: votes.append("SHORT")
    return ("LONG" if votes.count("LONG")>votes.count("SHORT") else 
            "SHORT" if votes.count("SHORT")>votes.count("LONG") else "NEUTRAL",
            votes)

# === Новое условие 100% LONG ===
def is_entry_opportunity(ind, last, votes):
    # все индикаторы должны дать LONG
    return votes.count("LONG")==len(votes)

# === Обработка сигнала ===
def process_signal(chat_id, interval):
    raw=get_candles(interval)
    df=pd.DataFrame(raw,columns=["timestamp","open","high","low","close","volume","turnover"])
    ind=analyze_indicators(df)
    last=float(df["close"].iloc[-1])
    prev=float(df["close"].iloc[-2])
    signal,votes=make_prediction(ind,last)
    ts=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO predictions (timestamp,price,signal,actual,votes,timeframe) VALUES (?,?,?,?,?,?)",
        (ts,last,signal,None,",".join(votes),interval)
    )
    conn.commit()

    # отправка базового прогноза
    text=f"📈 Закрытие: {last}\n📉 Предыдущее: {prev}\n"
    for k,v in ind.items(): text+=f"🔹 {k}: {round(v,2)}\n"
    text+=f"\n📌 Прогноз: {'🔺LONG' if signal=='LONG' else '🔻SHORT' if signal=='SHORT' else '⚪️NEUTRAL'}"
    text+=f"\n🧠 Голоса: {votes}"
    bot.send_message(chat_id,text)

# === Клавиатура ===
def make_reply_keyboard():
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("15м","30м","1ч")
    kb.row("Проверка","Точность")
    kb.row("Export CSV","Export Excel")
    return kb

@bot.message_handler(commands=['start'])
def start(m):
    if m.from_user.id!=AUTHORIZED_USER_ID:
        return bot.send_message(m.chat.id,"⛔ У вас нет доступа.")
    bot.send_message(m.chat.id,"✅ Бот запущен!",reply_markup=make_reply_keyboard())

@bot.message_handler(func=lambda m:m.chat.id==AUTHORIZED_USER_ID)
def handler(m):
    t=m.text.strip()
    if t=="15м": process_signal(m.chat.id,"15")
    elif t=="30м": process_signal(m.chat.id,"30")
    elif t=="1ч": process_signal(m.chat.id,"60")
    # ... сюда ваши verify, accuracy, export handlers ...

# === Авто‑вход за 1 мин до новой свечи с 100% условием ===
entry_flag=False
entry_time=0
COOLDOWN=15*60

def auto_entry_signal():
    global entry_flag, entry_time
    while True:
        now=datetime.utcnow()
        # минута перед новой 15‑мин свечей: %15==14
        if now.minute%15==14:
            raw=get_candles("15")
            df=pd.DataFrame(raw,columns=["timestamp","open","high","low","close","volume","turnover"])
            ind=analyze_indicators(df)
            last=float(df["close"].iloc[-1])
            _,votes=make_prediction(ind,last)
            can=is_entry_opportunity(ind,last,votes)
            ts=time.time()
            if can and (not entry_flag or ts-entry_time>=COOLDOWN):
                msg=(
                    "🔔 *100% Точка входа LONG!*  \n"
                    f"Цена: {last}\n"
                    f"Голоса: {votes}"
                )
                bot.send_message(AUTHORIZED_USER_ID,msg,parse_mode="Markdown")
                entry_flag=True
                entry_time=ts
            if not can:
                entry_flag=False
                entry_time=0
            time.sleep(60-now.second)
        else:
            time.sleep(60-now.second)

threading.Thread(target=auto_entry_signal,daemon=True).start()

# === Запуск ===
bot.polling(none_stop=True)
