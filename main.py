import telebot
from telebot import types
import os
import pandas as pd
from pybit.unified_trading import HTTP
from datetime import datetime, timedelta
import ta

# 🔐 Безопасно подключаем токены
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")

bot = telebot.TeleBot(BOT_TOKEN)
session = HTTP(api_key=API_KEY, api_secret=API_SECRET)

# 📊 Хранилище для прогнозов
prediction_log = []

# 📉 Получение данных с Bybit
def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    candles = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
    return candles["result"]["list"]

# 📈 Расчёт индикаторов
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

# 🤖 Логика голосов
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

    long_votes = votes.count("LONG")
    short_votes = votes.count("SHORT")
    signal = "LONG" if long_votes > short_votes else "SHORT" if short_votes > long_votes else "NEUTRAL"
    return signal, votes

# 🟢 Команда /start с кнопками
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📡 Сигнал", callback_data='signal'))
    markup.add(types.InlineKeyboardButton("📊 Точность", callback_data='accuracy'))
    markup.add(types.InlineKeyboardButton("📍 Проверить прогноз", callback_data='verify'))
    bot.send_message(message.chat.id, "👋 Привет! Выбери действие:", reply_markup=markup)

# 📡 Команда получения сигнала
def process_signal(chat_id):
    raw = get_candles()
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
    indicators = analyze_indicators(df)
    last = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2])
    signal, votes = make_prediction(indicators, last)

    prediction_log.append({
        "time": datetime.utcnow(),
        "price": last,
        "signal": signal,
        "actual": None,
        "votes": votes
    })

    text = f"📈 Закрытие: {last}\n📉 Предыдущее: {prev}\n"
    for key, val in indicators.items():
        text += f"🔹 {key}: {round(val, 2)}\n"
    text += f"\n📌 Прогноз: {'🔺 LONG' if signal == 'LONG' else '🔻 SHORT' if signal == 'SHORT' else '⚪️ NEUTRAL'}\n🧠 Голоса: {votes}"
    bot.send_message(chat_id, text)

# 🕒 Команда проверки прогноза
def verify_prediction(chat_id):
    now = datetime.utcnow()
    verified = 0
    for entry in prediction_log:
        if entry["actual"] is None and (now - entry["time"]) > timedelta(minutes=15):
            candles = get_candles()
            close_now = float(candles[-1][4])
            actual = "LONG" if close_now > entry["price"] else "SHORT" if close_now < entry["price"] else "NEUTRAL"
            entry["actual"] = actual
            verified += 1
    bot.send_message(chat_id, f"🔍 Обновлено прогнозов: {verified}")

# 📊 Команда точности
def show_accuracy(chat_id):
    total = sum(1 for p in prediction_log if p["actual"])
    correct = sum(1 for p in prediction_log if p["actual"] == p["signal"])
    if total == 0:
        bot.send_message(chat_id, "📊 Ещё нет проверенных прогнозов.")
    else:
        accuracy = round(100 * correct / total, 2)
        bot.send_message(chat_id, f"✅ Точность: {accuracy}% ({correct} из {total})")

# ☑️ Обработка кнопок
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == "signal":
        process_signal(call.message.chat.id)
    elif call.data == "accuracy":
        show_accuracy(call.message.chat.id)
    elif call.data == "verify":
        verify_prediction(call.message.chat.id)

# ✅ Запуск бота
bot.polling(none_stop=True)
