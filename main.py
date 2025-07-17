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
    try:
        candles = session.get_kline(
            category="linear",
            symbol=symbol,
            interval=interval,
            limit=limit
        )
        return candles["result"]["list"]
    except Exception as e:
        return None

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal для получения сигнала.")

@bot.message_handler(commands=['signal'])
def send_signal(message):
    bot.send_message(message.chat.id, "📊 Получаю данные от Bybit...")

    try:
        data = get_candles()
        if data is None:
            raise ValueError("Не удалось получить данные с Bybit.")

        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["volume"] = df["volume"].astype(float)

        # RSI
        rsi = ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1]

        # EMA21
        ema21 = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1]

        # ADX
        adx = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14).adx().iloc[-1]

        # MACD
        macd = ta.trend.MACD(df["close"])
        macd_line = macd.macd().iloc[-1]
        macd_signal = macd.macd_signal().iloc[-1]

        last_close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]

        if last_close > prev_close:
            signal = "🔺 LONG"
        elif last_close < prev_close:
            signal = "🔻 SHORT"
        else:
            signal = "➖ Без изменений"

        bot.send_message(message.chat.id, f"""
📈 Закрытие: {last_close}
📉 Предыдущая: {prev_close}
📊 RSI: {round(rsi, 2)}
📈 EMA21: {round(ema21, 2)}
📊 ADX: {round(adx, 2)}
📉 MACD: {round(macd_line, 2)} / сигнал: {round(macd_signal, 2)}
📌 Сигнал: {signal}
        """)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()
