import telebot
import os
from pybit.unified_trading import HTTP
import pandas as pd
import ta

# Инициализация переменных окружения и сессии
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
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal для прогноза по рынку.")

@bot.message_handler(commands=['signal'])
def send_signal(message):
    bot.send_message(message.chat.id, "📊 Получаю данные от Bybit...")

    try:
        data = get_candles()
        if data is None:
            raise ValueError("Не удалось получить данные с Bybit.")

        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df[["close", "high", "low", "volume"]] = df[["close", "high", "low", "volume"]].astype(float)

        # Индикаторы
        rsi = ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1]
        ema = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1]
        adx = ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1]
        cci = ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1]
        stoch = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"]).stoch().iloc[-1]
        momentum = ta.momentum.ROCIndicator(df["close"]).roc().iloc[-1]
        sma = ta.trend.SMAIndicator(df["close"], window=20).sma_indicator().iloc[-1]
        bb = ta.volatility.BollingerBands(df["close"])
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        wr = ta.momentum.WilliamsRIndicator(df["high"], df["low"], df["close"]).williams_r().iloc[-1]
        macd = ta.trend.MACD(df["close"]).macd_diff().iloc[-1]
        sar = ta.trend.PSARIndicator(df["high"], df["low"], df["close"]).psar().iloc[-1]

        last_close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]

        # Сигнальная логика
        long_signals = 0
        short_signals = 0

        if last_close > ema: long_signals += 1
        else: short_signals += 1

        if rsi > 60: long_signals += 1
        elif rsi < 40: short_signals += 1

        if cci > 100: long_signals += 1
        elif cci < -100: short_signals += 1

        if stoch > 70: long_signals += 1
        elif stoch < 30: short_signals += 1

        if momentum > 0: long_signals += 1
        elif momentum < 0: short_signals += 1

        if last_close > sma: long_signals += 1
        else: short_signals += 1

        if last_close > bb_upper: short_signals += 1
        elif last_close < bb_lower: long_signals += 1

        if wr < -80: long_signals += 1
        elif wr > -20: short_signals += 1

        if macd > 0: long_signals += 1
        elif macd < 0: short_signals += 1

        if last_close > sar: long_signals += 1
        else: short_signals += 1

        if long_signals > short_signals:
            prediction = "🔺 LONG (вверх) — прогноз на следующие 15 минут"
        elif short_signals > long_signals:
            prediction = "🔻 SHORT (вниз) — прогноз на следующие 15 минут"
        else:
            prediction = "⚪️ NEUTRAL — недостаточно сигнала"

        # Ответ пользователю
        bot.send_message(message.chat.id, f"""
📈 Закрытие: {last_close}
📉 Предыдущее: {prev_close}
📊 RSI: {round(rsi, 2)}
📈 EMA21: {round(ema, 2)}
📊 ADX: {round(adx, 2)}
📊 CCI: {round(cci, 2)}
📊 Stochastic: {round(stoch, 2)}
📊 Momentum: {round(momentum, 2)}
📊 SMA(20): {round(sma, 2)}
📊 Bollinger:
   🔺 Верхняя: {round(bb_upper, 2)}
   🔻 Нижняя: {round(bb_lower, 2)}
📊 Williams %R: {round(wr, 2)}
📊 MACD: {round(macd, 2)}
📊 SAR: {round(sar, 2)}

📌 Сигнал: {prediction}
        """)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()
