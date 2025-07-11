import telebot
import os

bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))

@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(message.chat.id, "Бот работает! 🚀")

bot.polling()
