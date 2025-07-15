import openai
import os
import telebot
from telebot import types
from pybit.unified_trading import HTTP

# Инициализация API ключей из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)
openai.api_key = OPENAI_API_KEY

# Получение базового сигнала
def get_market_data():
    try:
        candles = session.get_kline(category="linear", symbol="BTCUSDT", interval="15", limit=200)
        last_close = float(candles['result']['list'][-1][4])
        prev_close = float(candles['result']['list'][-2][4])
        change = last_close - prev_close
        direction = "🔺 LONG (вверх)" if change > 0 else "🔻 SHORT (вниз)"
        return f"📊 Закрытие: {last_close}\n📉 Предыдущее: {prev_close}\n📈 Сигнал: {direction}"
    except Exception as e:
        return f"❌ Ошибка получения данных: {e}"

# Стартовое сообщение с кнопкой
@bot.message_handler(commands=['start'])
def start_message(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("/signal")
    markup.add(btn1)
    bot.send_message(message.chat.id, "👋 Привет! Нажми кнопку ниже, чтобы получить сигнал.", reply_markup=markup)

# Команда /signal
@bot.message_handler(commands=['signal'])
def send_signal(message):
    bot.send_message(message.chat.id, "⏳ Получаю данные от Bybit...")
    market_info = get_market_data()

    # Отправка в ChatGPT
    try:
        completion = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Ты опытный криптотрейдер. Анализируй данные и предскажи направление рынка."},
                {"role": "user", "content": f"Анализируй на основе:\n{market_info}"}
            ]
        )
        chatgpt_response = completion['choices'][0]['message']['content']
        bot.send_message(message.chat.id, f"🤖 Анализ ChatGPT:\n{chatgpt_response}")
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка анализа ChatGPT:\n{e}")

# Запуск бота
bot.polling(none_stop=True)
