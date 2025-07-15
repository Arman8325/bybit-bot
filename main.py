import telebot
import os
from pybit.unified_trading import HTTP
from dotenv import load_dotenv

load_dotenv()  # Загрузка переменных из .env файла

# Инициализация бота
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Инициализация Bybit-сессии
session = HTTP(
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET
)

@bot.message_handler(commands=['start'])
def start_command(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal, чтобы получить рекомендацию.")

@bot.message_handler(commands=['signal'])
def signal_command(message):
    try:
        bot.send_message(message.chat.id, "⏳ Получаю данные от Bybit...")

        candles = session.get_kline(
            category="linear",
            symbol="BTCUSDT",
            interval="15",
            limit=3
        )

        candle_list = candles['result']['list']
        if len(candle_list) < 2:
            bot.send_message(message.chat.id, "❌ Недостаточно данных для анализа.")
            return

        last = float(candle_list[-1][4])   # Закрытие последней свечи
        prev = float(candle_list[-2][4])   # Закрытие предыдущей свечи

        if last > prev:
            signal = "🔺 LONG (вверх)"
        elif last < prev:
            signal = "🔻 SHORT (вниз)"
        else:
            signal = "➖ Боковое движение"

        response = (
            f"📊 Закрытие: {last}\n"
            f"📉 Предыдущее: {prev}\n"
            f"📌 Сигнал: {signal}"
        )

        bot.send_message(message.chat.id, response)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

# Запуск бота
bot.polling()

