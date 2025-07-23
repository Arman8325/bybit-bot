import telebot
from telebot import types
import os
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
from pybit.unified_trading import HTTP
import ta

# Инициализация переменных
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

# Инициализация базы данных
conn = sqlite3.connect("predictions.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        time TEXT,
        price REAL,
        signal TEXT,
        actual TEXT,
        votes TEXT
    )
''')
conn.commit()

# Получение свечей
def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    candles = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
    return candles["result"]["list"]

# Индикаторы
def analyze_indicators(df):
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)

    ind = {}
    ind["RSI"] = ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1]
    ind["EMA21"] = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1]
    ind["ADX"] = ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1]
    ind["CCI"] = ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1]
    ind["Stoch"] = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"]).stoch().iloc[-1]
    ind["Momentum"] = ta.momentum.ROCIndicator(df["close"]).roc().iloc[-1]
    bb = ta.volatility.BollingerBands(df["close"])
    ind["BOLL_UP"] = bb.bollinger_hband().iloc[-1]
    ind["BOLL_LOW"] = bb.bollinger_lband().iloc[-1]
    ind["SAR"] = ta.trend.PSARIndicator(df["high"], df["low"], df["close"]).psar().iloc[-1]
    ind["MACD"] = ta.trend.MACD(df["close"]).macd().iloc[-1]
    ind["WR"] = ta.momentum.WilliamsRIndicator(df["high"], df["low"], df["close"]).williams_r().iloc[-1]
    return ind

# Логика прогноза
def make_prediction(ind, close):
    votes = []

    if ind["RSI"] > 60:
        votes.append("LONG")
    elif ind["RSI"] < 40:
        votes.append("SHORT")

    votes.append("LONG" if close > ind["EMA21"] else "SHORT")
    if ind["ADX"] > 25:
        votes.append("LONG")
    if ind["CCI"] > 100:
        votes.append("LONG")
    elif ind["CCI"] < -100:
        votes.append("SHORT")
    if ind["Stoch"] > 80:
        votes.append("SHORT")
    elif ind["Stoch"] < 20:
        votes.append("LONG")
    votes.append("LONG" if ind["Momentum"] > 0 else "SHORT")
    if close > ind["BOLL_UP"]:
        votes.append("SHORT")
    elif close < ind["BOLL_LOW"]:
        votes.append("LONG")
    votes.append("LONG" if close > ind["SAR"] else "SHORT")
    votes.append("LONG" if ind["MACD"] > 0 else "SHORT")
    if ind["WR"] < -80:
        votes.append("LONG")
    elif ind["WR"] > -20:
        votes.append("SHORT")

    long_count = votes.count("LONG")
    short_count = votes.count("SHORT")
    signal = "LONG" if long_count > short_count else "SHORT" if short_count > long_count else "NEUTRAL"
    return signal, votes

# Обработка команд
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton("/signal"),
        types.KeyboardButton("/verify"),
        types.KeyboardButton("/accuracy")
    )
    bot.send_message(message.chat.id, "👋 Добро пожаловать! Выберите команду:", reply_markup=markup)


# Генерация сигнала
def process_signal(chat_id):
    raw = get_candles()
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
    indicators = analyze_indicators(df)
    close = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2])
    signal, votes = make_prediction(indicators, close)

    cursor.execute('''
        INSERT INTO predictions (time, price, signal, actual, votes)
        VALUES (?, ?, ?, ?, ?)
    ''', (datetime.utcnow().isoformat(), close, signal, None, ",".join(votes)))
    conn.commit()

    msg = f"📈 Закрытие: {close}\n📉 Предыдущее: {prev}\n"
    for k, v in indicators.items():
        msg += f"🔹 {k}: {round(v, 2)}\n"
    msg += f"\n📌 Прогноз: {'🔺 LONG' if signal == 'LONG' else '🔻 SHORT' if signal == 'SHORT' else '⚪️ NEUTRAL'}\n🧠 Голоса: {votes}"
    bot.send_message(chat_id, msg)

# Проверка прогноза
def verify_prediction(chat_id):
    candles = get_candles()
    close_now = float(candles[-1][4])
    verified = 0

    cursor.execute("SELECT id, time, price, signal FROM predictions WHERE actual IS NULL")
    for row in cursor.fetchall():
        pid, time_str, entry_price, signal = row
        time_dt = datetime.fromisoformat(time_str)
        if datetime.utcnow() - time_dt > timedelta(minutes=15):
            actual = "LONG" if close_now > entry_price else "SHORT" if close_now < entry_price else "NEUTRAL"
            cursor.execute("UPDATE predictions SET actual = ? WHERE id = ?", (actual, pid))
            verified += 1
    conn.commit()
    bot.send_message(chat_id, f"🔍 Обновлено прогнозов: {verified}")

# Показать точность
def show_accuracy(chat_id):
    cursor.execute("SELECT signal, actual FROM predictions WHERE actual IS NOT NULL")
    rows = cursor.fetchall()
    if not rows:
        bot.send_message(chat_id, "📊 Нет проверенных прогнозов.")
        return
    total = len(rows)
    correct = sum(1 for s, a in rows if s == a)
    acc = round(100 * correct / total, 2)
    bot.send_message(chat_id, f"📈 Точность: {acc}% ({correct}/{total})")

# Кнопки
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == "signal":
        process_signal(call.message.chat.id)
    elif call.data == "verify":
        verify_prediction(call.message.chat.id)
    elif call.data == "accuracy":
        show_accuracy(call.message.chat.id)

# Защита от сообщений
@bot.message_handler(func=lambda message: True)
def block_text(message):
    bot.send_message(message.chat.id, "⚙️ Используй кнопки ниже или команду /start.")

# Запуск бота
bot.polling(none_stop=True)
