import telebot
from telebot import types
import os
import pandas as pd
from pybit.unified_trading import HTTP
from datetime import datetime, timedelta
import ta

# Инициализация
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

# Лог предсказаний
prediction_log = []

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

# Логика прогноза
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

    long_count = votes.count("LONG")
    short_count = votes.count("SHORT")
    signal = "LONG" if long_count > short_count else "SHORT" if short_count > long_count else "NEUTRAL"

    return signal, votes

# Обработчик команд /start
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📡 Получить сигнал", callback_data='signal'))
    markup.add(types.InlineKeyboardButton("📊 Точность", callback_data='accuracy'))
    markup.add(types.InlineKeyboardButton("📍 Проверить прогноз", callback_data='verify'))
    bot.send_message(message.chat.id, "🤖 Привет! Выбери действие:", reply_markup=markup)

# Получить сигнал
def process_signal(chat_id):
    raw = get_candles()
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
    indicators = analyze_indicators(df)
    last = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2])
    signal, votes = make_prediction(indicators, last)

    timestamp = datetime.utcnow()
    prediction_log.append({
        "time": timestamp,
        "price": last,
        "signal": signal,
        "actual": None,
        "votes": votes
    })

    text = f"📈 Закрытие: {last}\n📉 Предыдущее: {prev}\n"
    for key, val in indicators.items():
        text += f"🔹 {key}: {round(val, 2)}\n"
    text += f"\n📌 Прогноз на следующие 15 минут: {'🔺 LONG' if signal == 'LONG' else '🔻 SHORT' if signal == 'SHORT' else '⚪️ NEUTRAL'}\n🧠 Голоса: {votes}"
    bot.send_message(chat_id, text)

# Проверка прогноза
def verify_prediction(chat_id):
    now = datetime.utcnow()
    verified = 0
    for entry in prediction_log:
        if entry["actual"] is None and (now - entry["time"]) > timedelta(minutes=15):
            candles = get_candles()
            close_now = float(candles["result"]["list"][-1][4])
            actual = "LONG" if close_now > entry["price"] else "SHORT" if close_now < entry["price"] else "NEUTRAL"
            entry["actual"] = actual
            verified += 1
    bot.send_message(chat_id, f"🔍 Обновлено прогнозов: {verified}")

# Отображение точности
def show_accuracy(chat_id):
    total = 0
    correct = 0
    for p in prediction_log:
        if p["actual"]:
            total += 1
            if p["signal"] == p["actual"]:
                correct += 1
    if total == 0:
        bot.send_message(chat_id, "📊 Ещё нет проверенных прогнозов.")
    else:
        accuracy = round(100 * correct / total, 2)
        bot.send_message(chat_id, f"✅ Точность прогнозов: {accuracy}% ({correct} из {total})")

# Обработка нажатий кнопок
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == "signal":
        process_signal(call.message.chat.id)
    elif call.data == "accuracy":
        show_accuracy(call.message.chat.id)
    elif call.data == "verify":
        verify_prediction(call.message.chat.id)

# Запуск
bot.polling(none_stop=True)
