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
    except Exception:
        return None

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal для получения сигнала.")

@bot.message_handler(commands=['signal'])
def send_signal(message):
    bot.send_message(message.chat.id, "📊 Получаю данные от Bybit...")

    try:
        data = get_candles()
        if data is None:
            raise ValueError("Не удалось получить данные с Bybit.")

        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df = df.astype(float)

        # Индикаторы
        rsi = ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1]
        ema = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1]
        adx = ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1]
        cci = ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1]
        stoch = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"]).stoch().iloc[-1]
        momentum = ta.momentum.ROCIndicator(df["close"]).roc().iloc[-1]
        sma20 = ta.trend.SMAIndicator(df["close"], window=20).sma_indicator().iloc[-1]
        bb = ta.volatility.BollingerBands(df["close"])
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        wr = ta.momentum.WilliamsRIndicator(df["high"], df["low"], df["close"]).williams_r().iloc[-1]
        mavol = df["volume"].rolling(window=20).mean().iloc[-1]
        kdj_k = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"]).stoch().iloc[-1]
        stoch_rsi = ta.momentum.StochRSIIndicator(df["close"]).stochrsi().iloc[-1]

        last_close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]

        # Простая логика сигнала
        signal = "⚪️ NEUTRAL"
        reasons = []

        if last_close > ema and rsi > 50 and adx > 20:
            signal = "🔺 LONG (вверх)"
            reasons.append("EMA < цена")
            reasons.append("RSI > 50")
            reasons.append("ADX > 20")
        elif last_close < ema and rsi < 50 and adx > 20:
            signal = "🔻 SHORT (вниз)"
            reasons.append("EMA > цена")
            reasons.append("RSI < 50")
            reasons.append("ADX > 20")

        prediction_text = "📈 Прогноз: В следующие 15 минут, вероятно, "
        if signal.startswith("🔺"):
            prediction_text += "цена пойдёт вверх."
        elif signal.startswith("🔻"):
            prediction_text += "цена пойдёт вниз."
        else:
            prediction_text += "сильного движения не ожидается."

        bot.send_message(message.chat.id, f"""
📈 Закрытие: {last_close}
📉 Предыдущее: {prev_close}
📊 RSI: {round(rsi, 2)}
📈 EMA21: {round(ema, 2)}
📊 ADX: {round(adx, 2)}
📊 CCI: {round(cci, 2)}
📊 Stochastic: {round(stoch, 2)}
📊 Momentum: {round(momentum, 2)}
📊 SMA20: {round(sma20, 2)}
📊 Williams %R: {round(wr, 2)}
📊 MAVOL(20): {round(mavol, 2)}
📊 KDJ (K): {round(kdj_k, 2)}
📊 StochRSI: {round(stoch_rsi, 2)}
📊 Bollinger Bands:
   🔺 Верхняя: {round(bb_upper, 2)}
   🔻 Нижняя: {round(bb_lower, 2)}
📌 Сигнал: {signal}
📣 Причины: {", ".join(reasons) if reasons else 'Нет чётких подтверждений'}
{prediction_text}
        """)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()
