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
        bot.send_message(message.chat.id, "\u23f3 Получаю данные от Bybit...")

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
            signal = "\ud83d\udd39 LONG (вверх)"
        elif last_close < prev_close:
            signal = "\ud83d\udd3b SHORT (вниз)"
        else:
            signal = "➖ Без изменений"

        bot.send_message(
            message.chat.id,
            f"\ud83d\udcca Последняя свеча: {last_close}\n\ud83d\udcc9 Предыдущая: {prev_close}\n\ud83d\udcc8 Сигнал: {signal}"
        )

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка при получении сигнала: {str(e)}")

bot.polling()

