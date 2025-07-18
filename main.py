import telebot
import os
from pybit.unified_trading import HTTP
import pandas as pd
import ta

# Инициализация переменных
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    try:
        candles = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
        return candles["result"]["list"]
    except:
        return None

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй команду /signal для получения сигнала.")

@bot.message_handler(commands=['signal'])
def send_signal(message):
    bot.send_message(message.chat.id, "📊 Получаю данные от Bybit...")

    try:
        data = get_candles()
        if data is None:
            raise Exception("Не удалось получить данные с Bybit.")

        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["volume"] = df["volume"].astype(float)

        signals = []

        # RSI
        rsi = ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1]
        if rsi > 70:
            signals.append("short")
        elif rsi < 30:
            signals.append("long")
        else:
            signals.append("neutral")

        # EMA 21
        ema21 = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1]
        if df["close"].iloc[-1] > ema21:
            signals.append("long")
        elif df["close"].iloc[-1] < ema21:
            signals.append("short")
        else:
            signals.append("neutral")

        # ADX
        adx = ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1]
        signals.append("long" if adx > 25 else "neutral")

        # CCI
        cci = ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1]
        if cci > 100:
            signals.append("long")
        elif cci < -100:
            signals.append("short")
        else:
            signals.append("neutral")

        # Stochastic Oscillator
        stoch = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"])
        stoch_val = stoch.stoch().iloc[-1]
        if stoch_val > 80:
            signals.append("short")
        elif stoch_val < 20:
            signals.append("long")
        else:
            signals.append("neutral")

        # Momentum
        momentum = ta.momentum.MomentumIndicator(df["close"]).momentum().iloc[-1]
        if momentum > 0:
            signals.append("long")
        elif momentum < 0:
            signals.append("short")
        else:
            signals.append("neutral")

        # SMA(20)
        sma20 = ta.trend.SMAIndicator(df["close"], window=20).sma_indicator().iloc[-1]
        if df["close"].iloc[-1] > sma20:
            signals.append("long")
        elif df["close"].iloc[-1] < sma20:
            signals.append("short")
        else:
            signals.append("neutral")

        # Bollinger Bands
        bb = ta.volatility.BollingerBands(df["close"])
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        if df["close"].iloc[-1] > bb_upper:
            signals.append("short")
        elif df["close"].iloc[-1] < bb_lower:
            signals.append("long")
        else:
            signals.append("neutral")

        # Williams %R
        williams = ta.momentum.WilliamsRIndicator(df["high"], df["low"], df["close"]).williams_r().iloc[-1]
        if williams < -80:
            signals.append("long")
        elif williams > -20:
            signals.append("short")
        else:
            signals.append("neutral")

        # Итоговая логика
        long_count = signals.count("long")
        short_count = signals.count("short")

        if long_count >= 6:
            final_signal = "🔺 LONG"
        elif short_count >= 6:
            final_signal = "🔻 SHORT"
        else:
            final_signal = "➖ NEUTRAL"

        # Форматированный вывод
        bot.send_message(message.chat.id, f"""
📉 RSI: {round(rsi, 2)}
📈 EMA21: {round(ema21, 2)}
📊 ADX: {round(adx, 2)}
📊 CCI: {round(cci, 2)}
📊 Stochastic: {round(stoch_val, 2)}
📊 Momentum: {round(momentum, 2)}
📊 SMA20: {round(sma20, 2)}
📊 Bollinger Bands: Верхняя {round(bb_upper, 2)} | Нижняя {round(bb_lower, 2)}
📊 Williams %R: {round(williams, 2)}

📌 Сигнал по большинству: {final_signal}
        """)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()

