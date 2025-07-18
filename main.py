import telebot
import os
from pybit.unified_trading import HTTP
import pandas as pd
import ta

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
    except Exception:
        return None

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Напиши /signal для прогноза.")

@bot.message_handler(commands=['signal'])
def send_signal(message):
    bot.send_message(message.chat.id, "📊 Получаю данные от Bybit...")

    try:
        data = get_candles()
        if data is None:
            raise ValueError("❌ Не удалось получить данные с Bybit.")

        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df = df.astype(float)

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # Индикаторы
        rsi = ta.momentum.RSIIndicator(close).rsi().iloc[-1]
        ema21 = ta.trend.EMAIndicator(close, window=21).ema_indicator().iloc[-1]
        adx = ta.trend.ADXIndicator(high, low, close).adx().iloc[-1]
        cci = ta.trend.CCIIndicator(high, low, close).cci().iloc[-1]
        stoch = ta.momentum.StochasticOscillator(high, low, close).stoch().iloc[-1]
        momentum = ta.momentum.ROCIndicator(close).roc().iloc[-1]
        bb = ta.volatility.BollingerBands(close)
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]

        last = close.iloc[-1]
        prev = close.iloc[-2]

        # Умная логика
        long_conditions = [
            rsi < 70,
            last > ema21,
            adx > 20,
            cci > 0,
            stoch > 50,
            momentum > 0,
            last > bb_lower
        ]
        short_conditions = [
            rsi > 30,
            last < ema21,
            adx > 20,
            cci < 0,
            stoch < 50,
            momentum < 0,
            last < bb_upper
        ]

        if all(long_conditions):
            signal = "🟢 LONG"
        elif all(short_conditions):
            signal = "🔴 SHORT"
        else:
            signal = "⚪️ NEUTRAL"

        bot.send_message(message.chat.id, f"""
📈 Закрытие: {round(last, 2)}
📉 Предыдущее: {round(prev, 2)}
📊 RSI: {round(rsi, 2)}
📈 EMA21: {round(ema21, 2)}
📊 ADX: {round(adx, 2)}
📊 CCI: {round(cci, 2)}
📊 Stochastic: {round(stoch, 2)}
📊 Momentum: {round(momentum, 2)}
📊 Bollinger Bands:
   🔺 Верхняя: {round(bb_upper, 2)}
   🔻 Нижняя: {round(bb_lower, 2)}
📌 Сигнал: {signal}
        """)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()
