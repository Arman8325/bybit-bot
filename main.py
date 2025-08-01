import os
from dotenv import load_dotenv
from telebot import TeleBot, types

# Загружаем .env (укажите путь при необходимости)
load_dotenv(dotenv_path="/mnt/data/NNV/.env")

# Пробуем получить токен
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or "7725284250:AAG7a-apzzqkoQCa1RGO0g10Y2lZB36LXYc"

print("DEBUG: TELEGRAM_TOKEN =", TELEGRAM_TOKEN)

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден! Проверьте .env")

# Запуск бота
bot = TeleBot(TELEGRAM_TOKEN)

@bot.message_handler(commands=['start'])
def cmd_start(msg: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("✅ Test Button")
    bot.send_message(msg.chat.id, "Привет! Бот запущен ✅", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "✅ Test Button")
def test_button(msg: types.Message):
    bot.reply_to(msg, "Кнопка работает! 🎉")

if __name__ == '__main__':
    print("✅ Бот запущен, ждёт сообщений...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)

