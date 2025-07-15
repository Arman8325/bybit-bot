import telebot
import os
from pybit.unified_trading import HTTP
from datetime import datetime

bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))

session = HTTP(
    api_key=os.getenv("BYBIT_API_KEY"),
    api_secret=os.getenv("BYBIT_API_SECRET")
)

@bot.message_handler(commands=['start'])
def start_handler(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal, чтобы получить сигнал по рынку.")

@bot.message_handler(commands=['signal'])
def signal_handler(message):
    try:
        bot.send_message(message.chat.id, "⏳ Получаю данные от Bybit...")

        candles = session.get_kline(category="linear", symbol="BTCUSDT", interval="15", limit=3)
        candle_list = candles['result']['list']

        if len(candle_list) < 2:
            bot.send_message(message.chat.id, "❌ Недостаточно данных для анализа.")
            return

        last_close = float(candle_list[-1][4])
        prev_close = float(candle_list[-2][4])

        direction = "🔺 LONG (вверх)" if last_close > prev_close else "🔻 SHORT (вниз)"

        bot.send_message(
            message.chat.id,
            f"📊 Закрытие: {last_close}\n"
            f"📉 Предыдущее: {prev_close}\n"
            f"📌 Сигнал: {direction}"
        )

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка при получении сигнала: {str(e)}")

bot.polling()
