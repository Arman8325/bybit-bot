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

# Инициализация
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

# База данных
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

# Кнопки выбора таймфрейма
def create_timeframe_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("🕒 15 минут", callback_data='tf_15'),
        types.InlineKeyboardButton("🕞 30 минут", callback_data='tf_30'),
        types.InlineKeyboardButton("🕕 1 час", callback_data='tf_60')
    )
    return markup

# Команда /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "🤖 Привет! Выбери таймфрейм:", reply_markup=create_timeframe_keyboard())

# Получить сигнал
def process_signal(chat_id, interval):
    raw = get_candles(interval=interval)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
    indicators = analyze_indicators(df)
    last = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2])
    signal, votes = make_prediction(indicators, last)

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO predictions (timestamp, price, signal, actual, votes, timeframe) VALUES (?, ?, ?, ?, ?, ?)",
        (timestamp, last, signal, None, ",".join(votes), interval)
    )
    conn.commit()

    text = f"📈 Закрытие: {last}\n📉 Предыдущее: {prev}\n"
    for key, val in indicators.items():
        text += f"🔹 {key}: {round(val, 2)}\n"
    text += f"\n📌 Прогноз на следующие {interval} минут: {'🔺 LONG' if signal == 'LONG' else '🔻 SHORT' if signal == 'SHORT' else '⚪️ NEUTRAL'}\n🧠 Голоса: {votes}"
    bot.send_message(chat_id, text)

# Обработка кнопок
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == "tf_15":
        process_signal(call.message.chat.id, "15")
    elif call.data == "tf_30":
        process_signal(call.message.chat.id, "30")
    elif call.data == "tf_60":
        process_signal(call.message.chat.id, "60")

bot.polling(none_stop=True)
