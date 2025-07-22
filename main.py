import telebot
import os
import sqlite3
from pybit.unified_trading import HTTP
import pandas as pd
import ta
from datetime import datetime, timedelta
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

# === ИНИЦИАЛИЗАЦИЯ ===
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

# === БАЗА ДАННЫХ ===
conn = sqlite3.connect("predictions.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    close REAL,
    signal TEXT,
    actual TEXT,
    verified INTEGER DEFAULT 0
)
""")
conn.commit()

# === ПОЛУЧЕНИЕ СВЕЧЕЙ ===
def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    candles = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
    return candles["result"]["list"]

# === АНАЛИЗ ИНДИКАТОРОВ ===
def analyze_indicators(df):
    df = df.copy()
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
    }
    return indicators

# === ПРОГНОЗ ===
def make_prediction(indicators, last_close):
    votes = []

    if indicators["RSI"] > 60: votes.append("LONG")
    elif indicators["RSI"] < 40: votes.append("SHORT")

    if last_close > indicators["EMA21"]: votes.append("LONG")
    else: votes.append("SHORT")

    if indicators["ADX"] > 25: votes.append("LONG")
    if indicators["CCI"] > 100: votes.append("LONG")
    elif indicators["CCI"] < -100: votes.append("SHORT")

    if indicators["Stochastic"] > 80: votes.append("SHORT")
    elif indicators["Stochastic"] < 20: votes.append("LONG")

    if indicators["Momentum"] > 0: votes.append("LONG")
    else: votes.append("SHORT")

    long_votes = votes.count("LONG")
    short_votes = votes.count("SHORT")
    signal = "LONG" if long_votes > short_votes else "SHORT" if short_votes > long_votes else "NEUTRAL"
    return signal, votes

# === КНОПКИ ===
def get_main_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("/signal"), KeyboardButton("/verify"), KeyboardButton("/accuracy"))
    return markup

# === ОБРАБОТКА /start ===
@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "🤖 Бот запущен! Используй кнопки или команды ниже.", reply_markup=get_main_keyboard())

# === ОБРАБОТКА /signal ===
@bot.message_handler(commands=['signal'])
def signal_handler(message):
    try:
        raw = get_candles()
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        last_close = float(df["close"].iloc[-1])
        prev_close = float(df["close"].iloc[-2])
        indicators = analyze_indicators(df)
        signal, votes = make_prediction(indicators, last_close)

        # Сохраняем в БД
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO predictions (timestamp, close, signal) VALUES (?, ?, ?)", (timestamp, last_close, signal))
        conn.commit()

        # Ответ
        text = f"📈 Закрытие: {last_close}\n📉 Предыдущее: {prev_close}\n"
        for name, val in indicators.items():
            text += f"🔹 {name}: {round(val, 2)}\n"
        text += f"\n📌 Сигнал на следующие 15 минут: {'🔺 LONG' if signal=='LONG' else '🔻 SHORT' if signal=='SHORT' else '⚪️ NEUTRAL'}\n🧠 Голоса: {votes}"
        bot.send_message(message.chat.id, text)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {e}")

# === ОБРАБОТКА /verify ===
@bot.message_handler(commands=['verify'])
def verify_predictions(message):
    try:
        cursor.execute("SELECT id, timestamp, close, signal FROM predictions WHERE verified = 0")
        rows = cursor.fetchall()
        now = datetime.utcnow()

        verified = 0
        for row in rows:
            pred_id, ts_str, pred_close, pred_signal = row
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            if now - ts >= timedelta(minutes=15):
                raw = get_candles(limit=2)
                df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
                current_close = float(df["close"].iloc[-1])

                # Проверка результата
                actual_signal = "LONG" if current_close > pred_close else "SHORT" if current_close < pred_close else "NEUTRAL"
                cursor.execute("UPDATE predictions SET actual=?, verified=1 WHERE id=?", (actual_signal, pred_id))
                conn.commit()
                verified += 1

        bot.send_message(message.chat.id, f"🔍 Обновлено прогнозов: {verified}")

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка проверки: {e}")

# === ОБРАБОТКА /accuracy ===
@bot.message_handler(commands=['accuracy'])
def show_accuracy(message):
    cursor.execute("SELECT signal, actual FROM predictions WHERE verified = 1")
    rows = cursor.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "ℹ️ Пока нет проверенных прогнозов.")
        return

    total = len(rows)
    correct = sum(1 for row in rows if row[0] == row[1])
    percent = round((correct / total) * 100, 2)
    bot.send_message(message.chat.id, f"📊 Точность прогнозов: {correct}/{total} ({percent}%)")

# === ЗАПУСК ===
bot.polling(none_stop=True)
