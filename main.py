import telebot
import os
from pybit.unified_trading import HTTP
import pandas as pd
import ta

# Инициализация бота и сессии
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))

session = HTTP(
    api_key=os.getenv("BYBIT_API_KEY"),
    api_secret=os.getenv("BYBIT_API_SECRET")
)

def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    candles = session.get_kline(
        category="linear",
        symbol=symbol,
        interval=interval,
        limit=limit
    )
    return candles["result"]["list"]

@bot.message_handler(commands=['signal'])
def send_signal(message):
    bot.send_message(message.chat.id, "📊 Получаю данные от Bybit...")

    try:
        data = get_candles()
df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
df["close"] = df["close"].astype(float)
df["volume"] = df["volume"].astype(float)

# Индикаторы
rsi = ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1]
ema = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1]

last_close = df["close"].iloc[-1]
prev_close = df["close"].iloc[-2]

direction = "➖ Без изменений"
if last_close > prev_close:
    direction = "🔺 LONG"
elif last_close < prev_close:
    direction = "🔻 SHORT"


        # Ответ
        bot.send_message(message.chat.id, f"""
📈 Цена закрытия: {last_close}
📉 Предыдущая: {prev_close}
📊 RSI: {round(rsi, 2)}
📈 EMA21: {round(ema, 2)}
📌 Сигнал: {direction}
        """)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()
