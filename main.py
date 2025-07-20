import telebot
import os
from pybit.unified_trading import HTTP
import pandas as pd
import ta
import matplotlib.pyplot as plt
from io import BytesIO

# Инициализация
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    try:
        candles = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
        return candles["result"]["list"]
    except:
        return None

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal для сигнала с графиком.")

@bot.message_handler(commands=['signal'])
def send_signal(message):
    bot.send_message(message.chat.id, "📊 Получаю данные от Bybit...")

    try:
        data = get_candles()
        if not data:
            raise ValueError("Нет данных от Bybit.")

        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df["close"] = df["close"].astype(float)

        # Индикаторы
        rsi = ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1]
        ema = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1]

        last_close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]
        signal = "🔺 LONG" if last_close > prev_close else "🔻 SHORT" if last_close < prev_close else "➖ NEUTRAL"

        # Текст
        bot.send_message(message.chat.id, f"""📈 Закрытие: {last_close}
📉 Предыдущее: {prev_close}
📊 RSI: {round(rsi, 2)}
📈 EMA21: {round(ema, 2)}
📌 Сигнал: {signal}
""")

        # Построение графика
        plt.figure(figsize=(10, 4))
        plt.plot(df["close"], label="Close Price", color="blue")
        plt.plot(ta.trend.EMAIndicator(df["close"], window=21).ema_indicator(), label="EMA21", color="orange")
        plt.title("BTCUSDT — График и EMA21")
        plt.xlabel("Свечи")
        plt.ylabel("Цена")
        plt.legend()
        plt.grid()

        buf = BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()

        bot.send_photo(message.chat.id, photo=buf)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

# Запуск бота
bot.polling(none_stop=True)
