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

# === Для дедупликации сигналов по периодам ===
last_period = {}

# === Утилиты ===
def get_candles(interval="15", limit=100):
    return session.get_kline(category="linear", symbol="BTCUSDT", interval=interval, limit=limit)["result"]["list"]


def analyze_indicators(df):
    df = df.astype({"close":"float", "high":"float", "low":"float", "volume":"float"})
    inds = {
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
        "WR": ta.momentum.WilliamsRIndicator(df["high"], df["low"], df["close"]).williams_r().iloc[-1],
        "VOL_MA20": df["volume"].rolling(20).mean().iloc[-1]
    }
    return inds


def make_prediction(ind, last_close):
    votes = []
    if ind["RSI"] > 60:
        votes.append("LONG")
    elif ind["RSI"] < 40:
        votes.append("SHORT")
    votes.append("LONG" if last_close > ind["EMA21"] else "SHORT")
    if ind["ADX"] > 25:
        votes.append("LONG")
    if ind["CCI"] > 100:
        votes.append("LONG")
    elif ind["CCI"] < -100:
        votes.append("SHORT")
    if ind["Stochastic"] > 80:
        votes.append("SHORT")
    elif ind["Stochastic"] < 20:
        votes.append("LONG")
    votes.append("LONG" if ind["Momentum"] > 0 else "SHORT")
    if last_close > ind["BOLL_UP"]:
        votes.append("SHORT")
    elif last_close < ind["BOLL_LOW"]:
        votes.append("LONG")
    votes.append("LONG" if last_close > ind["SAR"] else "SHORT")
    votes.append("LONG" if ind["MACD"] > 0 else "SHORT")
    if ind["WR"] < -80:
        votes.append("LONG")
    elif ind["WR"] > -20:
        votes.append("SHORT")
    lc = votes.count("LONG")
    sc = votes.count("SHORT")
    if lc > sc:
        return "LONG", votes
    if sc > lc:
        return "SHORT", votes
    return "NEUTRAL", votes


def is_entry_opportunity(ind, last_close, votes):
    return votes.count("LONG") == len(votes)

# === Обработка сигнала ===
def process_signal(chat_id, interval, manual=False):
    data = get_candles(interval=interval)
    df = pd.DataFrame(data, columns=["timestamp","open","high","low","close","volume","turnover"])
    # дедупликация по периоду
    period = int(interval) * 60
    idx = int(df["timestamp"].iloc[-1]) // period
    if last_period.get(interval) == idx:
        return
    last_period[interval] = idx

    ind = analyze_indicators(df)
    last = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2])
    signal, votes = make_prediction(ind, last)

    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO predictions (timestamp, price, signal, actual, votes, timeframe) VALUES (?,?,?,?,?,?)",
        (ts, last, signal, None, ",".join(votes), interval)
    )
    conn.commit()

    text = (
        f"⏱ Таймфрейм: {interval}м\n"
        f"📈 Закрытие: {last}\n"
        f"📉 Предыдущее: {prev}\n"
    )
    for k, v in ind.items():
        text += f"🔹 {k}: {round(v,2)}\n"
    text += f"\n📌 Прогноз на {interval}м: "
    text += "🔺 LONG" if signal=="LONG" else "🔻 SHORT" if signal=="SHORT" else "⚪️ NEUTRAL"
    text += f"\n🧠 Голоса: {votes}"
    bot.send_message(chat_id, text)

    # авт-точка входа за 1 мин до новой свечи
    now = datetime.utcnow()
    if now.minute % int(interval) == int(interval)-1 and is_entry_opportunity(ind, last, votes):
        entry = (
            "🔔 *100% Точка входа LONG!*  \n"
            f"Цена: {last}\nГолоса: {votes}"
        )
        bot.send_message(chat_id, entry, parse_mode="Markdown")

# === Проверка, точность, экспорт ===
def verify(chat_id):
    now = datetime.utcnow()
    cursor.execute("SELECT id, timestamp, price FROM predictions WHERE actual IS NULL")
    updated = 0
    for _id, ts, price in cursor.fetchall():
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        if now - dt >= timedelta(minutes=15):
            nc = float(get_candles(interval="15")[-1][4])
            actual = "LONG" if nc>price else "SHORT" if nc<price else "NEUTRAL"
            cursor.execute("UPDATE predictions SET actual=? WHERE id=?", (actual, _id))
            updated += 1
    conn.commit()
    bot.send_message(chat_id, f"🔍 Обновлено прогнозов: {updated}")

# === Точность ===
def accuracy(chat_id):
    cursor.execute("SELECT signal, actual FROM predictions WHERE actual IS NOT NULL")
    rows = cursor.fetchall()
    if not rows:
        return bot.send_message(chat_id, "📊 Нет проверенных.")
    total = len(rows)
    correct = sum(1 for s,a in rows if s==a)
    bot.send_message(chat_id, f"✅ Точность: {round(correct/total*100,2)}% ({correct}/{total})")

# === Экспорт ===
def export_csv(m):
    df = pd.read_sql_query("SELECT * FROM predictions", conn)
    if df.empty:
        return bot.send_message(m.chat.id, "📁 Нет данных.")
    buf = BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    bot.send_document(m.chat.id, ("signals.csv", buf))

def export_excel(m):
    df = pd.read_sql_query("SELECT * FROM predictions", conn)
    if df.empty:
        return bot.send_message(m.chat.id, "📁 Нет данных.")
    buf = BytesIO()
    df.to_excel(buf, index=False, sheet_name="Signals")
    buf.seek(0)
    bot.send_document(m.chat.id, ("signals.xlsx", buf))

# === Клавиатура ===
def make_reply_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("15м","30м","1ч")
    kb.row("Проверка","Точность")
    kb.row("Export CSV","Export Excel")
    return kb

# === Хендлеры ===
@bot.message_handler(commands=['start'])
def start(m):
    if m.from_user.id != AUTHORIZED_USER_ID:
        return bot.send_message(m.chat.id, "⛔ У вас нет доступа.")
    bot.send_message(m.chat.id, "✅ Бот запущен!", reply_markup=make_reply_keyboard())

@bot.message_handler(func=lambda m: m.chat.id==AUTHORIZED_USER_ID)
def handler(m):
    cmd = m.text.strip()
    if cmd == "15м":
        process_signal(m.chat.id, "15", manual=True)
    elif cmd == "30м":
        process_signal(m.chat.id, "30", manual=True)
    elif cmd == "1ч":
        process_signal(m.chat.id, "60", manual=True)
    elif cmd == "Проверка":
        verify(m.chat.id)
    elif cmd == "Точность":
        accuracy(m.chat.id)
    elif cmd == "Export CSV":
        export_csv(m)
    elif cmd == "Export Excel":
        export_excel(m)
    else:
        bot.send_message(m.chat.id, "ℹ️ Используйте клавиатуру.", reply_markup=make_reply_keyboard())

# === Авто‑прогноз 15м ===
def auto_pred():
    while True:
        try:
            process_signal(AUTHORIZED_USER_ID, "15")
            time.sleep(900)
        except:
            time.sleep(900)
threading.Thread(target=auto_pred, daemon=True).start()

# === Ежедневный отчёт ===
last_summary_date = None

def daily_summary():
    global last_summary_date
    while True:
        now = datetime.utcnow()
        nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        time.sleep((nxt-now).total_seconds())
        ds = (nxt - timedelta(days=1)).strftime("%Y-%m-%d")
        if ds != last_summary_date:
            last_summary_date = ds
            rows = cursor.execute(
                "SELECT signal,actual FROM predictions WHERE timestamp LIKE ? AND actual IS NOT NULL",
                (ds+"%",)
            ).fetchall()
            tot = len(rows)
            corr = sum(1 for s,a in rows if s==a)
            txt = (
                f"📅 Отчёт за {ds}: Всего {tot}, Попаданий {corr}, Точность {round(corr/tot*100,2)}%"
                if tot else f"📅 Отчёт за {ds}: нет данных"
            )
            bot.send_message(AUTHORIZED_USER_ID, txt)
threading.Thread(target=daily_summary, daemon=True).start()

# === Запуск ===
bot.polling(none_stop=True)
