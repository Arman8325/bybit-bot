import telebot
import os
from pybit.unified_trading import HTTP
import pandas as pd
import ta

# Инициализация бота и сессии
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    try:
        candles = session.get_kline(
            category="linear", symbol=symbol, interval=interval, limit=limit
        )
        return candles["result"]["list"]
    except Exception:
        return None

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal для прогноза на следующие 15 минут.")

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
        bb_mid = ta.volatility.BollingerBands(df["close"]).bollinger_mavg().iloc[-1]
        psar = ta.trend.PSARIndicator(df["high"], df["low"], df["close"]).psar().iloc[-1]
        macd = ta.trend.MACD(df["close"])
        macd_line = macd.macd().iloc[-1]
        signal_line = macd.macd_signal().iloc[-1]
        mavol = df["volume"].rolling(window=20).mean().iloc[-1]

        last_close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]

        # Прогнозная логика
        score = 0
        reasons = []

        if rsi < 30:
            score += 1
            reasons.append("RSI < 30 → перепроданность")
        elif rsi > 70:
            score -= 1
            reasons.append("RSI > 70 → перекупленность")

        if last_close > ema:
            score += 1
            reasons.append("Цена выше EMA → восходящий тренд")
        else:
            score -= 1
            reasons.append("Цена ниже EMA → нисходящий тренд")

        if macd_line > signal_line:
            score += 1
            reasons.append("MACD > сигнальной линии → бычий импульс")
        else:
            score -= 1
            reasons.append("MACD < сигнальной линии → медвежий импульс")

        if momentum > 0:
            score += 1
            reasons.append("Momentum положительный")
        else:
            score -= 1
            reasons.append("Momentum отрицательный")

        if adx > 20:
            score += 1
            reasons.append("ADX > 20 → сильный тренд")
        else:
            reasons.append("ADX < 20 → слабый тренд")

        if df["volume"].iloc[-1] > mavol:
            score += 1
            reasons.append("Объём выше MAVOL → подтверждение")
        else:
            score -= 1
            reasons.append("Объём ниже MAVOL → слабый интерес")

        # Финальный прогноз
        if score >= 2:
            forecast = "🔮 Прогноз: LONG (рост в ближайшие 15 минут)"
        elif score <= -2:
            forecast = "🔮 Прогноз: SHORT (падение в ближайшие 15 минут)"
        else:
            forecast = "🔮 Прогноз: NEUTRAL (неопределённость)"

        # Ответ
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
📊 SAR: {round(psar, 2)}
📊 MACD: {round(macd_line, 2)} / Signal: {round(signal_line, 2)}
📊 MAVOL: {round(mavol, 2)}
📌 Сигнал: {"🔺 LONG" if last_close > prev_close else "🔻 SHORT" if last_close < prev_close else "⚪️ NEUTRAL"}

{forecast}

📋 Причины:
- {chr(10).join(reasons)}
        """)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()
