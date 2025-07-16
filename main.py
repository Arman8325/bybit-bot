import telebot
import os
from pybit.unified_trading import HTTP

# Создаём сессию Bybit
session = HTTP(
    api_key=os.getenv("BYBIT_API_KEY"),
    api_secret=os.getenv("BYBIT_API_SECRET")
)

# Создаём Telegram-бота
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal, чтобы получить рекомендацию.")

@bot.message_handler(commands=['signal'])
def get_signal(message):
    try:
        bot.send_message(message.chat.id, "⏳ Получаю данные от Bybit...")

        candles = session.get_kline(
            category="linear",
            symbol="BTCUSDT",
            interval="15",
            limit=2
        )

        candle_list = candles['result']['list']
        last_close = float(candle_list[-1][4])
        prev_close = float(candle_list[-2][4])

        if last_close > prev_close:
            signal = "🔺 LONG (вверх)"
        elif last_close < prev_close:
            signal = "🔻 SHORT (вниз)"
        else:
            signal = "➖ Без изменений"

        message_text = (
            f"📊 Последняя свеча: {last_close}\n"
            f"📉 Предыдущая: {prev_close}\n"
            f"📈 Сигнал: {signal}"
        )

        bot.send_message(message.chat.id, message_text)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка при получении сигнала:\n{str(e)}")

bot.polling()
