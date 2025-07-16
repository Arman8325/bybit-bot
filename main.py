import telebot

bot = telebot.TeleBot("ТВОЙ_ТОКЕН_ЗДЕСЬ")

@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.send_message(message.chat.id, "✅ Бот работает!")

print("🚀 Бот запущен")
bot.polling()
