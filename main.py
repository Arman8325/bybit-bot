import os
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from pybit.unified_trading import HTTP
from openai import OpenAI

# Инициализация клиентов
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
bybit = HTTP(
    api_key=os.getenv("BYBIT_API_KEY"),
    api_secret=os.getenv("BYBIT_API_SECRET")
)
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Кнопка
markup = ReplyKeyboardMarkup(resize_keyboard=True)
markup.add(KeyboardButton("/signal"))

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal, чтобы получить анализ.", reply_markup=markup)

@bot.message_handler(commands=['signal'])
def get_signal(message):
    try:
        bot.send_message(message.chat.id, "⏳ Получаю данные от Bybit...")

        candles = bybit.get_kline(
            category="linear", symbol="BTCUSDT", interval="15", limit=100
        )

        if not candles.get('result') or not candles['result'].get('list'):
            bot.send_message(message.chat.id, "❌ Не удалось получить данные от Bybit.")
            return

        last_candle = candles['result']['list'][-1]
        prev_candle = candles['result']['list'][-2]

        close = float(last_candle[4])
        prev_close = float(prev_candle[4])

        # Пример данных для анализа
        message_text = f"Последняя свеча: {close}\nПредыдущая: {prev_close}"

        # Отправляем в OpenAI для анализа
        chat_response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты — трейдинг аналитик. Дай рекомендацию long или short."},
                {"role": "user", "content": f"{message_text}"}
            ]
        )

        gpt_reply = chat_response.choices[0].message.content

        # Отправляем пользователю
        bot.send_message(message.chat.id, f"📊 Закрытие: {close}\n📉 Предыдущее: {prev_close}\n🤖 ChatGPT:",)
        bot.send_message(message.chat.id, gpt_reply)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка анализа ChatGPT:\n{str(e)}")

bot.polling()
