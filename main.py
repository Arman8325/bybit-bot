import telebot
import os
from pybit.unified_trading import HTTP
import pandas as pd
import numpy as np
import talib

# Получение токенов из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")

# Инициализация бота и сессии Bybit
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal, чтобы получить сигнал.")

@bot.message_handler(commands=['signal'])
def signal_handler(message):
    try:
        bot.send_message(message.chat.id, "\u23f3 Получаю данные от Bybit...")

        # Получение данных свечей
        response = session.get_kline(
            category="linear",
            symbol="BTCUSDT",
            interval="15",
            limit=100
        )

        candles = response.get("result", {}).get("list", [])
        if len(candles) < 50:
            bot.send_message(message.chat.id, "❌ Недостаточно данных для анализа")
            return

        df = pd.DataFrame(candles, columns=[
            "timestamp", "open", "high", "low", "close", "volume", "turnover"
        ])

        df = df.astype(float)

        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        volume = df["volume"].values

        rsi = talib.RSI(close, timeperiod=14)[-1]
        macd, macdsignal, _ = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
        ema9 = talib.EMA(close, timeperiod=9)[-1]
        ema21 = talib.EMA(close, timeperiod=21)[-1]
        sma50 = talib.SMA(close, timeperiod=50)[-1]
        upper, middle, lower = talib.BBANDS(close, timeperiod=20)

        last_close = close[-1]
        prev_close = close[-2]

        if last_close > prev_close:
            signal = "\ud83d\udd39 LONG (вверх)"
        elif last_close < prev_close:
            signal = "\ud83d\udd3b SHORT (вниз)"
        else:
            signal = "➖ Без изменений"

        response_msg = f"""
📊 Закрытие: {last_close:.2f}
📉 Предыдущее: {prev_close:.2f}
ℹ️ RSI: {rsi:.2f}
📉 MACD: {macd[-1]:.2f}, сигнал: {macdsignal[-1]:.2f}
📈 EMA9: {ema9:.2f}, EMA21: {ema21:.2f}
📊 SMA50: {sma50:.2f}
📎 Bollinger Bands: Верхняя {upper[-1]:.2f}, Средняя {middle[-1]:.2f}, Нижняя {lower[-1]:.2f}
📌 Сигнал: {signal}
        """
        bot.send_message(message.chat.id, response_msg)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()
