import telebot
import os
from pybit.unified_trading import HTTP

bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(
    api_key=os.getenv("BYBIT_API_KEY"),
    api_secret=os.getenv("BYBIT_API_SECRET")
)

def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        if delta > 0:
            gains.append(delta)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(-delta)
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот активен. Используй /signal для получения сигнала.")

@bot.message_handler(commands=['signal'])
def get_signal(message):
    try:
        bot.send_message(message.chat.id, "⏳ Получаю данные от Bybit...")

        candles = session.get_kline(
            category="linear",
            symbol="BTCUSDT",
            interval="15",
            limit=100
        )

        data = candles.get("result", {}).get("list", [])
        if len(data) < 15:
            bot.send_message(message.chat.id, "❌ Недостаточно данных.")
            return

        closes = [float(c[4]) for c in data[-15:]]
        rsi = calculate_rsi(closes)

        last_close = closes[-1]
        prev_close = closes[-2]

        trend = "🔺 LONG (вверх)" if last_close > prev_close else "🔻 SHORT (вниз)"

        rsi_comment = (
            f"📈 RSI: {round(rsi, 2)} – Перепродан 👇" if rsi < 30 else
            f"📉 RSI: {round(rsi, 2)} – Перекуплен ☝" if rsi > 70 else
            f"ℹ️ RSI: {round(rsi, 2)} – Нейтрально ➖"
        )

        bot.send_message(message.chat.id, f"📊 Закрытие: {last_close}\n📉 Предыдущее: {prev_close}\n{rsi_comment}\n📌 Сигнал: {trend}")

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()
