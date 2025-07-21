import telebot
import os
from pybit.unified_trading import HTTP
import pandas as pd
import ta
from datetime import datetime

# Инициализация бота и сессии
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

# Хранилище статистики
prediction_log = []

def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    candles = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
    return candles["result"]["list"]

def analyze_indicators(df):
    results = {}
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["volume"] = df["volume"].astype(float)

    results["RSI"] = ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1]
    results["EMA21"] = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1]
    results["MA20"] = ta.trend.SMAIndicator(df["close"], window=20).sma_indicator().iloc[-1]
    results["ADX"] = ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1]
    results["CCI"] = ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1]
    results["Stochastic"] = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"]).stoch().iloc[-1]
    results["Momentum"] = ta.momentum.ROCIndicator(df["close"]).roc().iloc[-1]
    bb = ta.volatility.BollingerBands(df["close"])
    results["BOLL_UP"] = bb.bollinger_hband().iloc[-1]
    results["BOLL_LOW"] = bb.bollinger_lband().iloc[-1]
    results["SAR"] = ta.trend.PSARIndicator(df["high"], df["low"], df["close"]).psar().iloc[-1]
    results["MACD"] = ta.trend.MACD(df["close"]).macd().iloc[-1]
    results["KDJ"] = results["Stochastic"]  # Псевдо-представление
    results["WR"] = ta.momentum.WilliamsRIndicator(df["high"], df["low"], df["close"]).williams_r().iloc[-1]
    return results

def make_prediction(indicators, last_close):
    votes = []

    if indicators["RSI"] > 60:
        votes.append("LONG")
    elif indicators["RSI"] < 40:
        votes.append("SHORT")

    if last_close > indicators["EMA21"]:
        votes.append("LONG")
    else:
        votes.append("SHORT")

    if indicators["ADX"] > 25:
        votes.append("LONG")

    if indicators["CCI"] > 100:
        votes.append("LONG")
    elif indicators["CCI"] < -100:
        votes.append("SHORT")

    if indicators["Stochastic"] > 80:
        votes.append("SHORT")
    elif indicators["Stochastic"] < 20:
        votes.append("LONG")

    if indicators["Momentum"] > 0:
        votes.append("LONG")
    else:
        votes.append("SHORT")

    if last_close > indicators["BOLL_UP"]:
        votes.append("SHORT")
    elif last_close < indicators["BOLL_LOW"]:
        votes.append("LONG")

    if last_close > indicators["SAR"]:
        votes.append("LONG")
    else:
        votes.append("SHORT")

    if indicators["MACD"] > 0:
        votes.append("LONG")
    else:
        votes.append("SHORT")

    if indicators["WR"] < -80:
        votes.append("LONG")
    elif indicators["WR"] > -20:
        votes.append("SHORT")

    # Мажоритарное голосование
    long_votes = votes.count("LONG")
    short_votes = votes.count("SHORT")
    signal = "LONG" if long_votes > short_votes else "SHORT" if short_votes > long_votes else "NEUTRAL"

    return signal, votes

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй команду /signal для прогноза.")

@bot.message_handler(commands=['signal'])
def send_signal(message):
    try:
        raw_data = get_candles()
        df = pd.DataFrame(raw_data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        indicators = analyze_indicators(df)
        last_close = float(df["close"].iloc[-1])
        prev_close = float(df["close"].iloc[-2])
        signal, votes = make_prediction(indicators, last_close)

        text = f"📈 Закрытие: {last_close}\n📉 Предыдущее: {prev_close}\n"
        for key in indicators:
            text += f"🔹 {key}: {round(indicators[key], 2)}\n"
        text += f"\n📌 Сигнал на следующие 15 минут: {'🔺 LONG' if signal == 'LONG' else '🔻 SHORT' if signal == 'SHORT' else '⚪️ NEUTRAL'}\n🧠 Основано на: {votes}"

        # Сохраняем прогноз
        prediction_log.append({
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "close": last_close,
            "signal": signal,
            "votes": votes
        })

        bot.send_message(message.chat.id, text)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

@bot.message_handler(commands=['stats'])
def send_stats(message):
    if not prediction_log:
        bot.send_message(message.chat.id, "ℹ️ Пока нет статистики.")
        return
    total = len(prediction_log)
    long_count = sum(1 for p in prediction_log if p["signal"] == "LONG")
    short_count = sum(1 for p in prediction_log if p["signal"] == "SHORT")
    neutral_count = total - long_count - short_count
    bot.send_message(
        message.chat.id,
        f"📊 Прогнозов: {total}\n🔺 LONG: {long_count}\n🔻 SHORT: {short_count}\n⚪️ NEUTRAL: {neutral_count}"
    )

bot.polling(none_stop=True)
