import os
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from pybit.unified_trading import HTTP
import openai
from dotenv import load_dotenv

load_dotenv()

# Инициализация
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
openai.api_key = os.getenv("OPENAI_API_KEY")
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

# Кнопки
keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(KeyboardButton("/signal"), KeyboardButton("/status"), KeyboardButton("/help"))

@bot.message_handler(commands=['start', 'help'])
def welcome(message):
    bot.send_message(
        message.chat.id,
        "👋 Привет! Я твой торговый бот.\nНажми /signal для получения рекомендации.\n/status — для проверки состояния.",
        reply_markup=keyboard
    )

@bot.message_handler(commands=['status'])
def status(message):
    bot.send_message(message.chat.id, "✅ Бот активен и готов к анализу!")

@bot.message_handler(commands=['signal'])
def get_signal(message):
    try:
        bot.send_message(message.chat.id, "⏳ Получаю данные от Bybit...")
        candles = session.get_kline(category="linear", symbol="BTCUSDT", interval="15", limit=100)

        if 'result' not in candles or 'list' not in candles['result']:
            bot.send_message(message.chat.id, "❌ Не удалось получить данные с Bybit.")
            return

        last = candles['result']['list'][-1]
        prev = candles['result']['list'][-2]

        close = float(last[4])
        prev_close = float(prev[4])

        # Подготовка текста для ChatGPT
        prompt = f"""
        Анализируй последние свечи с Bybit:
        - Последнее закрытие: {close}
        - Предыдущее закрытие: {prev_close}
        - Таймфрейм: 15 минут

        Выводи только направление: LONG (вверх) или SHORT (вниз), а также краткое объяснение.
        """

        chat_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )

        result = chat_response['choices'][0]['message']['content']
        bot.send_message(message.chat.id, f"📈 Сигнал от ChatGPT:\n{result}")

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка анализа:\n{str(e)}")

# Запуск
bot.polling()


       
