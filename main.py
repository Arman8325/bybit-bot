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

        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["volume"] = df["volume"].astype(float)

        # Индикаторы
        rsi = ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1]
        ema = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1]
        adx = ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1]
        cci = ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1]
        stoch = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"]).stoch().iloc[-1]
        momentum = ta.momentum.ROCIndicator(df["close"]).roc().iloc[-1]
        bb = ta.volatility.BollingerBands(df["close"])
        bb_mid = bb.bollinger_mavg().iloc[-1]

        last_close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]

        # Сигнал на текущий момент
        if last_close > prev_close:
            signal = "🔺 LONG (вверх)"
        elif last_close < prev_close:
            signal = "🔻 SHORT (вниз)"
        else:
            signal = "➖ Без изменений"

        # Прогноз на следующие 15 минут
        forecast = "NEUTRAL"
        reasons = []

        if adx > 20:
            if momentum > 0 and rsi > 55 and cci > 50 and last_close > ema:
                forecast = "LONG"
                reasons.append("Цена выше EMA, индикаторы показывают силу роста")
            elif momentum < 0 and rsi < 45 and cci < -50 and last_close < ema:
                forecast = "SHORT"
                reasons.append("Цена ниже EMA, индикаторы указывают на снижение")
            else:
                reasons.append("Несовпадение индикаторов, нет ясного сигнала")
        else:
            forecast = "NEUTRAL"
            reasons.append("ADX < 20 — слабый тренд, возможен флэт")

        bot.send_message(message.chat.id, f"""
📈 Закрытие: {last_close}
📉 Предыдущее: {prev_close}
📊 RSI: {round(rsi, 2)}
📈 EMA21: {round(ema, 2)}
📊 ADX: {round(adx, 2)}
📊 CCI: {round(cci, 2)}
📊 Stochastic: {round(stoch, 2)}
📊 Momentum: {round(momentum, 2)}
📊 Bollinger Mid: {round(bb_mid, 2)}
📌 Сигнал: {signal}
🔮 Прогноз на следующие 15 минут: {forecast}
ℹ️ Причина прогноза: {', '.join(reasons)}
        """)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()
