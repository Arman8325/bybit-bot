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
def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    return session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)["result"]["list"]

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

# === Голосование ===
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
    lc, sc = votes.count("LONG"), votes.count("SHORT")
    if lc > sc: return "LONG", votes
    if sc > lc: return "SHORT", votes
    return "NEUTRAL", votes

# === Условие входа 90% ===
def is_entry_opportunity(ind, last_close, votes):
    if ind["RSI"] >= 30: return False
    if last_close >= ind["EMA21"]: return False
    if votes.count("LONG")/len(votes) < 0.9: return False
    return True

# === process_signal, экспорт, статистика и клавиатура (как было) ===
def process_signal(chat_id, interval): ...
def verify(chat_id): ...
def accuracy(chat_id): ...
def export_csv(m): ...
def export_excel(m): ...
def make_reply_keyboard(): ...

@bot.message_handler(commands=['start'])
def start(m):
    if m.from_user.id!=AUTHORIZED_USER_ID:
        return bot.send_message(m.chat.id,"⛔ У вас нет доступа.")
    bot.send_message(m.chat.id, "✅ Бот запущен!", reply_markup=make_reply_keyboard())

@bot.message_handler(func=lambda m:m.chat.id==AUTHORIZED_USER_ID)
def handler(m):
    t=m.text.strip()
    if t=="15м": process_signal(m.chat.id,"15")
    elif t=="30м": process_signal(m.chat.id,"30")
    elif t=="1ч": process_signal(m.chat.id,"60")
    elif t=="Проверка": verify(m.chat.id)
    elif t=="Точность": accuracy(m.chat.id)
    elif t=="Export CSV": export_csv(m)
    elif t=="Export Excel": export_excel(m)
    else: bot.send_message(m.chat.id,"ℹ️ Клавиатуру!",reply_markup=make_reply_keyboard())

# === Авто‑прогнозы 15м ===
def auto_pred():
    while True:
        try:
            process_signal(AUTHORIZED_USER_ID,"15")
            time.sleep(900)
        except:
            time.sleep(900)
threading.Thread(target=auto_pred,daemon=True).start()

# === Авто‑входовые уведомления за 1 мин до новой свечи ===
entry_triggered = False
entry_time = None
COOLDOWN = 15*60

def auto_entry_signal():
    global entry_triggered, entry_time
    while True:
        now = datetime.utcnow()
        # проверяем только в ту минуту, когда minute %15 ==14
        if now.minute % 15 == 14:
            raw = get_candles(interval="15")
            df = pd.DataFrame(raw, columns=["timestamp","open","high","low","close","volume","turnover"])
            ind = analyze_indicators(df)
            last = float(df["close"].iloc[-1])
            _, votes = make_prediction(ind, last)
            can = is_entry_opportunity(ind, last, votes)
            ts = time.time()
            if can and (not entry_triggered or (entry_time and ts-entry_time>=COOLDOWN)):
                txt = (
                    "🔔 *Точка входа LONG!*  \n"
                    f"Цена: {last}\nRSI: {round(ind['RSI'],2)}, EMA21: {round(ind['EMA21'],2)}\n"
                    f"Доля LONG: {votes.count('LONG')}/{len(votes)} (≥90%)"
                )
                bot.send_message(AUTHORIZED_USER_ID, txt, parse_mode="Markdown")
                entry_triggered = True
                entry_time = ts
            if not can:
                entry_triggered = False
                entry_time = None
            # подождём окончание этой минуты
            time.sleep(60-now.second)
        else:
            # ждём до начала следующей минуты
            time.sleep(60-now.second)

threading.Thread(target=auto_entry_signal,daemon=True).start()

# === Ежедневный отчёт ===
last_summary_date=None
def daily_summary():
    while True:
        now = datetime.utcnow()
        nxt = (now+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
        time.sleep((nxt-now).total_seconds())
        ds=(nxt-timedelta(days=1)).strftime("%Y-%m-%d")
        if ds!=last_summary_date:
            global last_summary_date; last_summary_date=ds
            rows=cursor.execute(
                "SELECT signal,actual FROM predictions WHERE timestamp LIKE ? AND actual IS NOT NULL",
                (ds+"%",)
            ).fetchall()
            tot=len(rows); corr=sum(1 for s,a in rows if s==a)
            txt=(f"📅 Отчёт за {ds}: Всего {tot}, Попаданий {corr}, Точность {round(corr/tot*100,2)}%" 
                 if tot else f"📅 Отчёт за {ds}: нет данных")
            bot.send_message(AUTHORIZED_USER_ID, txt)

threading.Thread(target=daily_summary,daemon=True).start()

# === Старт поллинга ===
bot.polling(none_stop=True)
