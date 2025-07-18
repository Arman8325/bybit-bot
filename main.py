import telebot
import os
from pybit.unified_trading import HTTP
import pandas as pd
import ta

# Инициализация
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(
    api_key=os.getenv("BYBIT_API_KEY"),
    api_secret=os.getenv("BYBIT_API_SECRET")
)

def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    candles = session.get_kline(
        category="linear", symbol=symbol, interval=interval, limit=limit
    )
    return candles["result"]["list"]

@bot.message_handler(commands=['start'])
def start_msg(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal для получения сигнала.")

@bot.message_handler(commands=['signal'])
def send_signal(message):
    bot.send_message(message.chat.id, "📊 Получаю данные от Bybit...")

    try:
        data = get_candles()
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume", "turnover"
        ])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["volume"] = df["volume"].astype(float)

        # Индикаторы
        rsi = ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1]
        ema21 = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1]
        adx = ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1]
        cci = ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1]
        stochastic = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"]).stoch().iloc[-1]
        momentum = ta.momentum.MomentumIndicator(df["close"]).momentum().iloc[-1]
        sma20 = ta.trend.SMAIndicator(df["close"], window=20).sma_indicator().iloc[-1]
        bb = ta.volatility.BollingerBands(df["close"], window=20)
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        williams = ta.momentum.WilliamsRIndicator(df["high"], df["low"], df["close"]).williams_r().iloc[-1]

        # Сигнал
        last_close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]
        signal = "➖ Без изменений"
        if last_close > prev_close:
            signal = "🔺 LONG"
        elif last_close < prev_close:
            signal = "🔻 SHORT"

        # Ответ
        bot.send_message(message.chat.id, f"""
📈 Закрытие: {last_close}
📉 Предыдущая: {prev_close}
📊 RSI: {round(rsi, 2)}
📈 EMA21: {round(ema21, 2)}
📊 ADX: {round(adx, 2)}
📊 CCI: {round(cci, 2)}
📊 Stochastic: {round(stochastic, 2)}
📊 Momentum: {round(momentum, 2)}
📊 SMA(20): {round(sma20, 2)}
📊 Bollinger Bands:
   🔺 Верхняя: {round(bb_upper, 2)}
   🔻 Нижняя: {round(bb_lower, 2)}
📊 Williams %R: {round(williams, 2)}
📌 Сигнал: {signal}
        """)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()
