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

# Получение данных по свечам
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

# Взвешенные веса (можно обновлять по результатам анализа в будущем)
indicator_weights = {
    "rsi": 0.9,
    "ema": 0.8,
    "adx": 0.75,
    "cci": 0.7,
    "stoch": 0.85,
    "momentum": 0.65,
    "bb": 0.8,
    "wr": 0.6,
    "sma": 0.7
}

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal для прогноза на 15 минут.")

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

        # Вычисление индикаторов
        rsi = ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1]
        ema = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1]
        adx = ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1]
        cci = ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1]
        stoch = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"]).stoch().iloc[-1]
        momentum = ta.momentum.ROCIndicator(df["close"]).roc().iloc[-1]
        bb = ta.volatility.BollingerBands(df["close"])
        bb_mid = bb.bollinger_mavg().iloc[-1]
        wr = ta.momentum.WilliamsRIndicator(df["high"], df["low"], df["close"]).williams_r().iloc[-1]
        sma = ta.trend.SMAIndicator(df["close"], window=20).sma_indicator().iloc[-1]

        last_close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]

        # Логика прогноза (взвешенное голосование)
        score = 0
        total_weight = 0

        def apply_vote(condition, weight):
            nonlocal score, total_weight
            score += weight if condition else -weight
            total_weight += weight

        apply_vote(rsi > 50, indicator_weights["rsi"])
        apply_vote(last_close > ema, indicator_weights["ema"])
        apply_vote(adx > 20, indicator_weights["adx"])
        apply_vote(cci > 0, indicator_weights["cci"])
        apply_vote(stoch > 50, indicator_weights["stoch"])
        apply_vote(momentum > 0, indicator_weights["momentum"])
        apply_vote(last_close > bb_mid, indicator_weights["bb"])
        apply_vote(wr > -50, indicator_weights["wr"])
        apply_vote(last_close > sma, indicator_weights["sma"])

        signal_strength = score / total_weight

        if signal_strength > 0.25:
            forecast = "🟢 Прогноз: Уверенный рост (LONG)"
        elif signal_strength < -0.25:
            forecast = "🔴 Прогноз: Уверенное падение (SHORT)"
        else:
            forecast = "⚪️ Прогноз: Нейтрально / неопределённо"

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
📊 Bollinger Mid: {round(bb_mid, 2)}
📊 Williams %R: {round(wr, 2)}
📊 SMA20: {round(sma, 2)}
📌 {forecast}
        """)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()

