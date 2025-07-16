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
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй команду /signal для получения сигнала.")

@bot.message_handler(commands=['signal'])
def send_signal(message):
    bot.send_message(message.chat.id, "📊 Получаю данные от Bybit...")

    try:
        data = get_candles()
        if data is None:
            raise ValueError("Не удалось получить данные с Bybit.")

        # Создаём DataFrame с нужными колонками
        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df = df.astype({"open": float, "high": float, "low": float, "close": float, "volume": float})

        # Основные значения
        last_close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]

        # Индикаторы с безопасной обработкой
        try:
            rsi = round(ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1], 2)
        except:
            rsi = "n/a"

        try:
            ema = round(ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1], 2)
        except:
            ema = "n/a"

        try:
            sma = round(ta.trend.SMAIndicator(df["close"], window=21).sma_indicator().iloc[-1], 2)
        except:
            sma = "n/a"

        # Направление
        if last_close > prev_close:
            signal = "🔺 LONG"
        elif last_close < prev_close:
            signal = "🔻 SHORT"
        else:
            signal = "➖ Без изменений"

        # Ответ пользователю
        bot.send_message(message.chat.id, f"""
📈 Закрытие: {last_close}
📉 Предыдущая: {prev_close}
📊 RSI: {rsi}
📈 EMA21: {ema}
📉 SMA21: {sma}
📌 Сигнал: {signal}
        """)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()
