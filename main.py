import telebot
from telebot import types
import os
import pandas as pd
from pybit.unified_trading import HTTP
from datetime import datetime, timedelta
import ta
import sqlite3
import threading
import time
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

# БД SQLite
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

# Получить свечи
def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    candles = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
    return candles["result"]["list"]

# Индикаторы
def analyze_indicators(df):
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)

    indicators = {
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
    return indicators

# Прогноз
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

    long_count = votes.count("LONG")
    short_count = votes.count("SHORT")
    signal = "LONG" if long_count > short_count else "SHORT" if short_count > long_count else "NEUTRAL"
    return signal, votes

# Отправка сигнала
def process_signal(chat_id, interval):
    raw = get_candles(interval=interval)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
    indicators = analyze_indicators(df)
    last = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2])
    signal, votes = make_prediction(indicators, last)

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO predictions (timestamp, price, signal, actual, votes, timeframe) VALUES (?, ?, ?, ?, ?, ?)",
                   (timestamp, last, signal, None, ",".join(votes), interval))
    conn.commit()

    text = f"📈 Закрытие: {last}\n📉 Предыдущее: {prev}\n"
    for key, val in indicators.items():
        text += f"🔹 {key}: {round(val, 2)}\n"
    text += f"\n📌 Прогноз на следующие {interval} минут: {'🔺 LONG' if signal == 'LONG' else '🔻 SHORT' if signal == 'SHORT' else '⚪️ NEUTRAL'}\n🧠 Голоса: {votes}"
    bot.send_message(chat_id, text)

# Кнопки выбора
def main_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("🕒 15м", callback_data="tf_15"),
        types.InlineKeyboardButton("🕞 30м", callback_data="tf_30"),
        types.InlineKeyboardButton("🕐 1ч", callback_data="tf_60")
    )
    markup.row(
        types.InlineKeyboardButton("📍 Проверка", callback_data="verify"),
        types.InlineKeyboardButton("📊 Точность", callback_data="accuracy")
    )
    return markup

# Команда /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Привет! Выбери действие:", reply_markup=main_keyboard())

# Обработка кнопок
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == "tf_15":
        process_signal(call.message.chat.id, "15")
    elif call.data == "tf_30":
        process_signal(call.message.chat.id, "30")
    elif call.data == "tf_60":
        process_signal(call.message.chat.id, "60")
    elif call.data == "verify":
        verify_predictions(call.message.chat.id)
    elif call.data == "accuracy":
        show_accuracy(call.message.chat.id)

# Проверка прогноза
def verify_predictions(chat_id):
    now = datetime.utcnow()
    cursor.execute("SELECT id, timestamp, price FROM predictions WHERE actual IS NULL")
    rows = cursor.fetchall()
    updated = 0

    for row in rows:
        id_, ts, old_price = row
        ts_time = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        if now - ts_time >= timedelta(minutes=15):
            candles = get_candles()
            new_close = float(candles[-1][4])
            actual = "LONG" if new_close > old_price else "SHORT" if new_close < old_price else "NEUTRAL"
            cursor.execute("UPDATE predictions SET actual = ? WHERE id = ?", (actual, id_))
            updated += 1

    conn.commit()
    bot.send_message(chat_id, f"🔍 Обновлено прогнозов: {updated}")

# Точность
def show_accuracy(chat_id):
    cursor.execute("SELECT signal, actual FROM predictions WHERE actual IS NOT NULL")
    rows = cursor.fetchall()
    if not rows:
        bot.send_message(chat_id, "📊 Ещё нет проверенных прогнозов.")
        return

    total = len(rows)
    correct = sum(1 for r in rows if r[0] == r[1])
    acc = round(correct / total * 100, 2)
    bot.send_message(chat_id, f"✅ Точность: {acc}% ({correct}/{total})")

# 🔁 Автообновление прогноза каждые 15 мин
def auto_predict():
    while True:
        try:
            process_signal(chat_id=YOUR_CHAT_ID, interval="15")  # ← Вставь свой chat_id!
            time.sleep(900)
        except Exception as e:
            print(f"[AutoPredict Error] {e}")

# 🔁 Запуск фонового потока
# threading.Thread(target=auto_predict).start()  # Раскомментируй и вставь chat_id!

# Запуск бота
bot.polling(none_stop=True)

