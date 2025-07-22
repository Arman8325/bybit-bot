import telebot
import os
from pybit.unified_trading import HTTP
import pandas as pd
import ta
from datetime import datetime, timedelta
import sqlite3
import threading
import time

# Инициализация бота и сессии
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

# Подключение к базе данных
conn = sqlite3.connect("signals.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        close REAL,
        signal TEXT,
        verified INTEGER DEFAULT 0,
        result TEXT,
        votes TEXT
    )
''')
conn.commit()

def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    candles = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
    return candles["result"]["list"]

def analyze_indicators(df):
    results = {}
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)

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

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal для прогноза.")

@bot.message_handler(commands=['signal'])
def send_signal(message):
    try:
        raw_data = get_candles()
        df = pd.DataFrame(raw_data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        indicators = analyze_indicators(df)
        last_close = float(df["close"].iloc[-1])
        prev_close = float(df["close"].iloc[-2])
        signal, votes = make_prediction(indicators, last_close)

        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute('''
            INSERT INTO predictions (timestamp, close, signal, votes)
            VALUES (?, ?, ?, ?)
        ''', (timestamp, last_close, signal, str(votes)))
        conn.commit()

        text = f"📈 Закрытие: {last_close}\n📉 Предыдущее: {prev_close}\n"
        for key in indicators:
            text += f"🔹 {key}: {round(indicators[key], 2)}\n"
        text += f"\n📌 Сигнал на следующие 15 минут: {'🔺 LONG' if signal == 'LONG' else '🔻 SHORT' if signal == 'SHORT' else '⚪️ NEUTRAL'}\n🧠 Голоса: {votes}"
        bot.send_message(message.chat.id, text)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

def verify_predictions():
    while True:
        time.sleep(60)  # Проверка раз в минуту
        cursor.execute('''
            SELECT id, timestamp, close, signal FROM predictions WHERE verified = 0
        ''')
        rows = cursor.fetchall()
        for row in rows:
            pid, ts, prev_close, signal = row
            prediction_time = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            if datetime.utcnow() >= prediction_time + timedelta(minutes=15):
                try:
                    candles = get_candles(limit=2)
                    new_close = float(candles[-1][4])
                    result = "HIT" if (signal == "LONG" and new_close > prev_close) or (signal == "SHORT" and new_close < prev_close) else "MISS"
                    cursor.execute('''
                        UPDATE predictions SET verified = 1, result = ? WHERE id = ?
                    ''', (result, pid))
                    conn.commit()
                except:
                    continue

# Запуск фоновой проверки
threading.Thread(target=verify_predictions, daemon=True).start()

bot.polling(none_stop=True)
