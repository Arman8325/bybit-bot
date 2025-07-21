import telebot
import os
import pandas as pd
from pybit.unified_trading import HTTP
import ta

# Инициализация бота и сессии Bybit
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

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
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal для прогноза на следующие 15 минут.")

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
        volume = df["volume"]

        # Индикаторы
        rsi = ta.momentum.RSIIndicator(close).rsi().iloc[-1]
        ema = ta.trend.EMAIndicator(close, window=21).ema_indicator().iloc[-1]
        adx = ta.trend.ADXIndicator(high, low, close).adx().iloc[-1]
        cci = ta.trend.CCIIndicator(high, low, close).cci().iloc[-1]
        stoch = ta.momentum.StochasticOscillator(high, low, close).stoch().iloc[-1]
        momentum = ta.momentum.ROCIndicator(close).roc().iloc[-1]
        bb = ta.volatility.BollingerBands(close)
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        bb_middle = bb.bollinger_mavg().iloc[-1]

        last_close = close.iloc[-1]
        prev_close = close.iloc[-2]

        # Умная логика прогноза
        score = 0
        reasons = []

        if last_close > ema:
            score += 1
            reasons.append("Цена выше EMA21")
        if rsi > 50:
            score += 1
            reasons.append("RSI выше 50")
        if adx > 20:
            score += 1
            reasons.append("ADX указывает на наличие тренда")
        if cci > 0:
            score += 1
            reasons.append("CCI положительный")
        if stoch > 50:
            score += 1
            reasons.append("Стохастик выше 50")
        if momentum > 0:
            score += 1
            reasons.append("Моментум положительный")
        if last_close > bb_middle:
            score += 1
            reasons.append("Цена выше средней линии Bollinger")

        # Прогноз
        if score >= 5:
            prediction = "🔺 LONG (вверх)"
        elif score <= 2:
            prediction = "🔻 SHORT (вниз)"
        else:
            prediction = "⚪️ NEUTRAL (боковой тренд)"

        reason_text = "\n• " + "\n• ".join(reasons) if reasons else "—"

        bot.send_message(message.chat.id, (
            f"📈 Закрытие: {last_close}\n"
            f"📉 Предыдущее: {prev_close}\n"
            f"📊 RSI: {round(rsi, 2)}\n"
            f"📈 EMA21: {round(ema, 2)}\n"
            f"📊 ADX: {round(adx, 2)}\n"
            f"📊 CCI: {round(cci, 2)}\n"
            f"📊 Stochastic: {round(stoch, 2)}\n"
            f"📊 Momentum: {round(momentum, 2)}\n"
            f"📊 Bollinger Bands:\n"
            f"   🔺 Верхняя: {round(bb_upper, 2)}\n"
            f"   🔻 Нижняя: {round(bb_lower, 2)}\n"
            f"\n📌 Прогноз на следующие 15 минут: {prediction}\n"
            f"📋 Причины прогноза:{reason_text}"
        ))

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()

