import telebot
import os
import sqlite3
from datetime import datetime, timedelta
from pybit.unified_trading import HTTP
import pandas as pd
import ta

# Инициализация переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")

# Инициализация бота и сессии Bybit
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

# Инициализация базы данных SQLite
conn = sqlite3.connect("predictions.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    close_price REAL,
    signal TEXT,
    votes TEXT,
    result_price REAL,
    accuracy TEXT
)
""")
conn.commit()

# Получение свечей
def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    candles = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
    return candles["result"]["list"]

# Анализ индикаторов
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
    results["KDJ"] = results["Stochastic"]
    results["WR"] = ta.momentum.WilliamsRIndicator(df["high"], df["low"], df["close"]).williams_r().iloc[-1]
    return results

# Логика прогноза
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

    long_votes = votes.count("LONG")
    short_votes = votes.count("SHORT")
    signal = "LONG" if long_votes > short_votes else "SHORT" if short_votes > long_votes else "NEUTRAL"

    return signal, votes

# Команда /start
@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен. Используй /signal для прогноза.")

# Команда /signal
@bot.message_handler(commands=['signal'])
def send_signal(message):
    try:
        data = get_candles()
        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        indicators = analyze_indicators(df)
        last_close = float(df["close"].iloc[-1])
        prev_close = float(df["close"].iloc[-2])
        signal, votes = make_prediction(indicators, last_close)

        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO predictions (timestamp, close_price, signal, votes) VALUES (?, ?, ?, ?)",
                       (timestamp, last_close, signal, ",".join(votes)))
        conn.commit()

        text = f"📈 Закрытие: {last_close}\n📉 Предыдущее: {prev_close}\n"
        for key in indicators:
            text += f"🔹 {key}: {round(indicators[key], 2)}\n"
        text += f"\n📌 Сигнал на следующие 15 минут: {'🔺 LONG' if signal == 'LONG' else '🔻 SHORT' if signal == 'SHORT' else '⚪️ NEUTRAL'}\n🧠 Голоса: {votes}"

        bot.send_message(message.chat.id, text)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

# Команда /verify - проверить точность предыдущих прогнозов
@bot.message_handler(commands=['verify'])
def verify_predictions(message):
    try:
        cursor.execute("SELECT id, timestamp, close_price, signal FROM predictions WHERE result_price IS NULL")
        rows = cursor.fetchall()
        now = datetime.utcnow()

        updated = 0
        for row in rows:
            pid, ts_str, close_price, signal = row
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            if now - ts >= timedelta(minutes=15):
                # Получить фактическую цену
                candles = get_candles(limit=1)
                result_price = float(candles[-1][4])  # close

                # Определить точность
                if signal == "LONG" and result_price > close_price:
                    accuracy = "✅"
                elif signal == "SHORT" and result_price < close_price:
                    accuracy = "✅"
                elif signal == "NEUTRAL":
                    accuracy = "N/A"
                else:
                    accuracy = "❌"

                cursor.execute("UPDATE predictions SET result_price = ?, accuracy = ? WHERE id = ?",
                               (result_price, accuracy, pid))
                updated += 1
        conn.commit()

        bot.send_message(message.chat.id, f"🔍 Обновлено прогнозов: {updated}")

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка при проверке: {str(e)}")

# Команда /stats
@bot.message_handler(commands=['stats'])
def send_stats(message):
    cursor.execute("SELECT COUNT(*), SUM(accuracy = '✅'), SUM(accuracy = '❌') FROM predictions WHERE accuracy IS NOT NULL")
    total, correct, incorrect = cursor.fetchone()
    correct = correct or 0
    incorrect = incorrect or 0
    bot.send_message(
        message.chat.id,
        f"📊 Всего проверено: {total}\n✅ Верных: {correct}\n❌ Ошибочных: {incorrect}"
    )

bot.polling(none_stop=True)
