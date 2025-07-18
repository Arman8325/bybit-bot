import os
import telebot
import pandas as pd
from pybit.unified_trading import HTTP
import ta

# Инициализация переменных окружения и сессий
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
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй команду /signal для получения сигнала.")

@bot.message_handler(commands=['signal'])
def send_signal(message):
    bot.send_message(message.chat.id, "📊 Получаю данные от Bybit...")

    try:
        data = get_candles()
        if data is None:
            raise ValueError("Не удалось получить данные с Bybit.")

        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df = df.astype(float)

        close = df["close"]
        high = df["high"]
        low = df["low"]

        last_close = close.iloc[-1]
        prev_close = close.iloc[-2]

        # Расчет индикаторов
        rsi = ta.momentum.RSIIndicator(close).rsi().iloc[-1]
        ema = ta.trend.EMAIndicator(close, window=21).ema_indicator().iloc[-1]
        adx = ta.trend.ADXIndicator(high, low, close).adx().iloc[-1]
        cci = ta.trend.CCIIndicator(high, low, close).cci().iloc[-1]
        stochastic = ta.momentum.StochasticOscillator(high, low, close).stoch().iloc[-1]
        momentum = ta.momentum.ROCIndicator(close).roc().iloc[-1]
        bb = ta.volatility.BollingerBands(close)
        bb_mid = bb.bollinger_mavg().iloc[-1]

        # Логика принятия решений
        long_conditions = [
            rsi > 50,
            last_close > ema,
            adx > 20,
            cci > 0,
            stochastic > 50,
            momentum > 0,
            last_close > bb_mid,
            last_close > prev_close,
            last_close > ema
        ]
        short_conditions = [
            rsi < 50,
            last_close < ema,
            adx > 20,
            cci < 0,
            stochastic < 50,
            momentum < 0,
            last_close < bb_mid,
            last_close < prev_close,
            last_close < ema
        ]

        if sum(long_conditions) >= 6:
            signal = "🔺 LONG (вверх)"
        elif sum(short_conditions) >= 6:
            signal = "🔻 SHORT (вниз)"
        else:
            signal = "⚪️ NEUTRAL"

        # Ответ пользователю
        bot.send_message(message.chat.id, f"""
📈 Закрытие: {round(last_close, 2)}
📉 Предыдущее: {round(prev_close, 2)}
📊 RSI: {round(rsi, 2)}
📈 EMA21: {round(ema, 2)}
📊 ADX: {round(adx, 2)}
📊 CCI: {round(cci, 2)}
📊 Stochastic: {round(stochastic, 2)}
📊 Momentum: {round(momentum, 2)}
📊 Bollinger Mid: {round(bb_mid, 2)}
📌 Сигнал: {signal}
        """)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()
