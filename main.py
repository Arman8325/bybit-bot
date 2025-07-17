import telebot
import os
from pybit.unified_trading import HTTP
import pandas as pd
import ta

# Инициализация бота и сессии
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
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal для получения сигнала.")

@bot.message_handler(commands=['signal'])
def send_signal(message):
    bot.send_message(message.chat.id, "📊 Получаю данные от Bybit...")

    try:
        data = get_candles()
        if data is None:
            raise ValueError("Не удалось получить данные с Bybit.")

        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)

        # Индикаторы
        stoch = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"])
        stoch_k = stoch.stoch().iloc[-1]
        stoch_d = stoch.stoch_signal().iloc[-1]

        last_close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]

        signal = "🔺 LONG" if last_close > prev_close else "🔻 SHORT" if last_close < prev_close else "➖ Без изменений"

        bot.send_message(message.chat.id, f"""
📈 Закрытие: {last_close}
📉 Предыдущая: {prev_close}
📊 Stochastic Oscillator:
%K = {round(stoch_k, 2)}
%D = {round(stoch_d, 2)}
📌 Сигнал: {signal}
        """)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()
