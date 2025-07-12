import telebot
import os
from pybit.unified_trading import HTTP
session = HTTP(
    api_key=os.getenv("BYBIT_API_KEY"),
    api_secret=os.getenv("BYBIT_API_SECRET")
)

bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))

@bot.message_handler(commands=['signal'])
def get_signal(message):
    try:
        bot.send_message(message.chat.id, "Запрос получен. Получаю данные от Bybit...")

        candles = session.get_kline(
            category="linear", symbol="BTCUSDT", interval="15", limit=3
        )

        if not candles.get('result') or not candles['result'].get('list'):
            bot.send_message(message.chat.id, "❌ Не удалось получить данные о свечах от Bybit.")
            return

        candle_list = candles['result']['list']
        if len(candle_list) < 2:
            bot.send_message(message.chat.id, "❌ Недостаточно данных для анализа.")
            return

        last = float(candle_list[-1][4])
        prev = float(candle_list[-2][4])

        direction = "🔺 LONG (вверх)" if last > prev else "🔻 SHORT (вниз)"
        bot.send_message(
            message.chat.id,
            f"📊 Последняя свеча: {last}\n📉 Предыдущая: {prev}\n📈 Сигнал: {direction}"
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка при получении сигнала:\n{str(e)}")

    bot.send_message(message.chat.id, "Бот работает! 🚀")

bot.polling()
