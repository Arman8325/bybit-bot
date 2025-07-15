import os
import telebot
from pybit.unified_trading import HTTP
import openai
import talib
import numpy as np

# Получаем ключи из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Проверка на пустые токены
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is missing")
if not BYBIT_API_KEY or not BYBIT_API_SECRET:
    raise ValueError("Bybit API credentials are missing")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is missing")

# Инициализация
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)
openai.api_key = OPENAI_API_KEY

# Обработчик /start
@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal, чтобы получить рекомендацию.")

# Обработчик /signal
@bot.message_handler(commands=['signal'])
def get_signal(message):
    bot.send_message(message.chat.id, "⏳ Получаю данные от Bybit...")
    try:
        candles = session.get_kline(
            category="linear",
            symbol="BTCUSDT",
            interval="15",
            limit=100
        )
        data = candles['result']['list']
        closes = np.array([float(item[4]) for item in data])

        rsi = talib.RSI(closes, timeperiod=14)
        macd, signal, _ = talib.MACD(closes)
        last_rsi = round(rsi[-1], 2)
        last_macd = round(macd[-1] - signal[-1], 2)
        last_close = closes[-1]
        prev_close = closes[-2]

        # Формируем промпт для ChatGPT
        prompt = f"""
        Analyze this market data:
        - Last Close: {last_close}
        - Previous Close: {prev_close}
        - RSI: {last_rsi}
        - MACD Histogram: {last_macd}
        Suggest if the next 15 min candle likely goes LONG or SHORT and why.
        Answer in brief.
        """

        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )
        advice = response.choices[0].message.content

        bot.send_message(
            message.chat.id,
            f"\U0001F4C8 Закрытие: {last_close}\n"
            f"\U0001F4C9 Предыдущее: {prev_close}\n"
            f"ℹ️ RSI: {last_rsi}\n"
            f"📈 MACD Histogram: {last_macd}\n"
            f"\n🤖 ChatGPT Анализ: {advice}"
        )

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка анализа: {e}")

# Запуск бота
bot.polling()


       
