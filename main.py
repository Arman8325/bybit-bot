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
    try:
        candles = session.get_kline(
            category="linear",
            symbol=symbol,
            interval=interval,
            limit=limit
        )
        return candles["result"]["list"]
    except:
        return None

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal для прогноза.")

@bot.message_handler(commands=['signal'])
def signal_handler(message):
    bot.send_message(message.chat.id, "📊 Получаю данные от Bybit...")

    try:
        data = get_candles()
        if data is None:
            raise Exception("Нет данных от Bybit.")

        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df = df.astype(float)

        close = df["close"]
        high = df["high"]
        low = df["low"]

        # Индикаторы
        rsi = ta.momentum.RSIIndicator(close).rsi().iloc[-1]
        ema21 = ta.trend.EMAIndicator(close, window=21).ema_indicator().iloc[-1]
        sma20 = ta.trend.SMAIndicator(close, window=20).sma_indicator().iloc[-1]
        adx = ta.trend.ADXIndicator(high, low, close).adx().iloc[-1]
        cci = ta.trend.CCIIndicator(high, low, close).cci().iloc[-1]
        stoch = ta.momentum.StochasticOscillator(high, low, close).stoch().iloc[-1]
        momentum = ta.momentum.ROCIndicator(close).roc().iloc[-1]
        bb = ta.volatility.BollingerBands(close)
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        williams = ta.momentum.WilliamsRIndicator(high, low, close).williams_r().iloc[-1]

        # Прогноз по индикаторам
        long_votes = 0
        short_votes = 0

        if rsi < 30: long_votes += 1
        elif rsi > 70: short_votes += 1

        if close.iloc[-1] > ema21: long_votes += 1
        else: short_votes += 1

        if close.iloc[-1] > sma20: long_votes += 1
        else: short_votes += 1

        if adx > 25:
            if close.iloc[-1] > close.iloc[-2]: long_votes += 1
            else: short_votes += 1

        if cci > 100: long_votes += 1
        elif cci < -100: short_votes += 1

        if stoch > 80: short_votes += 1
        elif stoch < 20: long_votes += 1

        if momentum > 0: long_votes += 1
        else: short_votes += 1

        if close.iloc[-1] < bb_lower: long_votes += 1
        elif close.iloc[-1] > bb_upper: short_votes += 1

        if williams < -80: long_votes += 1
        elif williams > -20: short_votes += 1

        # Финальное решение
        if long_votes > short_votes:
            decision = "🔺 LONG (вверх)"
        elif short_votes > long_votes:
            decision = "🔻 SHORT (вниз)"
        else:
            decision = "⚪️ NEUTRAL"

        # Ответ
        bot.send_message(message.chat.id, f"""
📈 Закрытие: {close.iloc[-1]}
📉 Предыдущее: {close.iloc[-2]}
📊 RSI: {round(rsi, 2)}
📈 EMA21: {round(ema21, 2)}
📈 SMA20: {round(sma20, 2)}
📊 ADX: {round(adx, 2)}
📊 CCI: {round(cci, 2)}
📊 Stochastic: {round(stoch, 2)}
📊 Momentum: {round(momentum, 2)}
📊 Bollinger Bands:
   🔺 Верхняя: {round(bb_upper, 2)}
   🔻 Нижняя: {round(bb_lower, 2)}
📊 Williams %R: {round(williams, 2)}

📌 Прогноз на 15 мин: {decision}
        """)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()
