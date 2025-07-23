import telebot
from telebot import types
import os
import pandas as pd
from pybit.unified_trading import HTTP
from datetime import datetime, timedelta
import ta
import sqlite3
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

# SQLite база
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

# Получение свечей
def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    candles = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
    return candles["result"]["list"]

# Анализ индикаторов
def analyze_indicators(df):
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    indicators = {}
    indicators["RSI"] = ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1]
    indicators["EMA21"] = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1]
    indicators["ADX"] = ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1]
    indicators["CCI"] = ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1]
    indicators["Stochastic"] = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"]).stoch().iloc[-1]
    indicators["Momentum"] = ta.momentum.ROCIndicator(df["close"]).roc().iloc[-1]
    bb = ta.volatility.BollingerBands(df["close"])
    indicators["BOLL_UP"] = bb.bollinger_hband().iloc[-1]
    indicators["BOLL_LOW"] = bb.bollinger_lband().iloc[-1]
    indicators["SAR"] = ta.trend.PSARIndicator(df["high"], df["low"], df["close"]).psar().iloc[-1]
    indicators["MACD"] = ta.trend.MACD(df["close"]).macd().iloc[-1]
    indicators["WR"] = ta.momentum.WilliamsRIndicator(df["high"], df["low"], df["close"]).williams_r().iloc[-1]
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

# Кнопки
def main_menu():
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("📡 Сигнал", callback_data='signal_15'),
        types.InlineKeyboardButton("📊 Точность", callback_data='accuracy'),
        types.InlineKeyboardButton("📍 Проверить", callback_data='verify')
    )
    markup.row(
        types.InlineKeyboardButton("🕒 15 мин", callback_data='signal_15'),
        types.InlineKeyboardButton("🕞 30 мин", callback_data='signal_30'),
        types.InlineKeyboardButton("🕕 1 час", callback_data='signal_60')
    )
    return markup

# Обработка кнопок
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data.startswith("signal_"):
        interval = call.data.split("_")[1]
        send_signal(call.message.chat.id, interval)
    elif call.data == "accuracy":
        show_accuracy(call.message.chat.id)
    elif call.data == "verify":
        verify_predictions(call.message.chat.id)

# Команда /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "🤖 Привет! Выбери действие:", reply_markup=main_menu())

# Команда /signal
@bot.message_handler(commands=['signal'])
def signal_cmd(message):
    send_signal(message.chat.id, "15")

# Команда /accuracy
@bot.message_handler(commands=['accuracy'])
def accuracy_cmd(message):
    show_accuracy(message.chat.id)

# Команда /verify
@bot.message_handler(commands=['verify'])
def verify_cmd(message):
    verify_predictions(message.chat.id)

# Отправка сигнала
def send_signal(chat_id, interval):
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
    for k, v in indicators.items():
        text += f"🔹 {k}: {round(v, 2)}\n"
    text += f"\n📌 Прогноз: {'🔺 LONG' if signal=='LONG' else '🔻 SHORT' if signal=='SHORT' else '⚪️ NEUTRAL'}\n🧠 Голоса: {votes}"
    bot.send_message(chat_id, text)

# Проверка прогноза через 15 минут
def verify_predictions(chat_id):
    now = datetime.utcnow()
    verified = 0
    cursor.execute("SELECT id, timestamp, price FROM predictions WHERE actual IS NULL")
    for row in cursor.fetchall():
        pid, ts, price = row
        ts_dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        if (now - ts_dt) >= timedelta(minutes=15):
            candles = get_candles()
            current_close = float(candles[-1][4])
            actual = "LONG" if current_close > price else "SHORT" if current_close < price else "NEUTRAL"
            cursor.execute("UPDATE predictions SET actual=? WHERE id=?", (actual, pid))
            verified += 1
    conn.commit()
    bot.send_message(chat_id, f"✅ Обновлено прогнозов: {verified}")

# Отображение точности
def show_accuracy(chat_id):
    cursor.execute("SELECT signal, actual FROM predictions WHERE actual IS NOT NULL")
    rows = cursor.fetchall()
    total = len(rows)
    correct = sum(1 for s, a in rows if s == a)
    if total == 0:
        bot.send_message(chat_id, "ℹ️ Ещё нет проверенных прогнозов.")
    else:
        acc = round((correct / total) * 100, 2)
        bot.send_message(chat_id, f"📊 Точность прогнозов: {acc}% ({correct}/{total})")

# Запуск бота
bot.polling(none_stop=True)
