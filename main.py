import telebot
import os
from pybit.unified_trading import HTTP
import pandas as pd
import ta

# Инициализация
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    try:
        candles = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
        return candles["result"]["list"]
    except:
        return None

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй команду /signal для прогноза рынка.")

@bot.message_handler(commands=['signal'])
def send_signal(message):
    bot.send_message(message.chat.id, "📊 Анализирую рынок по 15 индикаторам...")

    try:
        data = get_candles()
        if data is None:
            raise ValueError("Не удалось получить данные с Bybit")

        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df = df.astype(float)

        # Индикаторы
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        rsi = ta.momentum.RSIIndicator(close).rsi().iloc[-1]
        ema = ta.trend.EMAIndicator(close, window=21).ema_indicator().iloc[-1]
        sma = ta.trend.SMAIndicator(close, window=20).sma_indicator().iloc[-1]
        adx = ta.trend.ADXIndicator(high, low, close).adx().iloc[-1]
        cci = ta.trend.CCIIndicator(high, low, close).cci().iloc[-1]
        stoch = ta.momentum.StochasticOscillator(high, low, close).stoch().iloc[-1]
        momentum = ta.momentum.ROCIndicator(close).roc().iloc[-1]
        bb = ta.volatility.BollingerBands(close)
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        mavol = volume.rolling(window=20).mean().iloc[-1]
        macd = ta.trend.MACD(close).macd_diff().iloc[-1]
        sar = ta.trend.PSARIndicator(high, low, close).psar().iloc[-1]
        wr = ta.momentum.WilliamsRIndicator(high, low, close).williams_r().iloc[-1]
        stoch_rsi = ta.momentum.StochRSIIndicator(close).stochrsi().iloc[-1]
        kdj = (stoch + stoch_rsi) / 2

        last_close = close.iloc[-1]
        prev_close = close.iloc[-2]

        # Логика сигнала
        reasons = []
        if last_close > ema: reasons.append("Цена выше EMA21")
        if rsi > 55: reasons.append("RSI показывает силу")
        if adx > 20: reasons.append("ADX подтверждает тренд")
        if macd > 0: reasons.append("MACD бычий")
        if sar < last_close: reasons.append("SAR под ценой")

        if last_close > prev_close and len(reasons) >= 3:
            direction = "🔺 LONG (вверх)"
        elif last_close < prev_close and (rsi < 45 or macd < 0 or sar > last_close):
            direction = "🔻 SHORT (вниз)"
        else:
            direction = "⚪️ NEUTRAL"

        bot.send_message(message.chat.id, f"""
📈 Закрытие: {last_close}
📉 Предыдущее: {prev_close}
📊 RSI: {round(rsi, 2)} | EMA21: {round(ema, 2)}
📊 ADX: {round(adx, 2)} | CCI: {round(cci, 2)}
📊 Stoch: {round(stoch, 2)} | Momentum: {round(momentum, 2)}
📊 BB: 🔺 {round(bb_upper, 2)} 🔻 {round(bb_lower, 2)}
📊 MAVOL: {round(mavol, 2)} | MACD: {round(macd, 2)}
📊 SAR: {round(sar, 2)} | WR: {round(wr, 2)}
📊 StochRSI: {round(stoch_rsi, 2)} | KDJ: {round(kdj, 2)}
📌 Прогноз на 15 минут: {direction}
📎 Причины: {'; '.join(reasons) if reasons else 'нет явных причин'}
        """)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()
