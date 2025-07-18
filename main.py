import telebot
import os
from pybit.unified_trading import HTTP
import pandas as pd
import ta

# Telegram и Bybit сессия
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))

session = HTTP(
    api_key=os.getenv("BYBIT_API_KEY"),
    api_secret=os.getenv("BYBIT_API_SECRET")
)

def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    try:
        candles = session.get_kline(
            category="linear",
            symbol=symbol,
            interval=interval,
            limit=limit
        )
        return candles["result"]["list"]
    except Exception as e:
        return None

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal для прогноза на 15 минут.")

@bot.message_handler(commands=['signal'])
def send_signal(message):
    bot.send_message(message.chat.id, "📊 Получаю данные и прогнозирую на 15 минут...")

    try:
        data = get_candles()
        if data is None:
            raise ValueError("Данные с Bybit не получены.")

        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df = df.astype(float)

        # Индикаторы
        close = df["close"]
        high = df["high"]
        low = df["low"]

        signals = []

        # RSI
        rsi = ta.momentum.RSIIndicator(close).rsi().iloc[-1]
        if rsi > 70:
            signals.append("SHORT")
        elif rsi < 30:
            signals.append("LONG")

        # EMA21
        ema21 = ta.trend.EMAIndicator(close
