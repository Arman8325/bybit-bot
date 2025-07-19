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

        # 1. RSI
        rsi = ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1]

        # 2. EMA21
        ema = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1]

        # 3. ADX
        adx = ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1]

        # 4. CCI
        cci = ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1]

        # 5. Stochastic
        stoch = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"]).stoch().iloc[-1]

        # 6. Momentum (ROC)
        momentum = ta.momentum.ROCIndicator(df["close"]).roc().iloc[-1]

        # 7. SMA(20)
        sma20 = ta.trend.SMAIndicator(df["close"], window=20).sma_indicator().iloc[-1]

        # 8. Bollinger Bands
        bb = ta.volatility.BollingerBands(df["close"])
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        bb_mid = bb.bollinger_mavg().iloc[-1]

        # 9. Williams %R
        williams_r = ta.momentum.WilliamsRIndicator(df["high"], df["low"], df["close"]).williams_r().iloc[-1]

        # 10. MAVOL (объёмная скользящая)
        mavol = df["volume"].rolling(window=20).mean().iloc[-1]

        # 11. KDJ
        low_min = df["low"].rolling(window=14).min()
        high_max = df["high"].rolling(window=14).max()
        rsv = (df["close"] - low_min) / (high_max - low_min) * 100
        df["K"] = rsv.ewm(alpha=1/3).mean()
        df["D"] = df["K"].ewm(alpha=1/3).mean()
        df["J"] = 3 * df["K"] - 2 * df["D"]
        kdj_k = df["K"].iloc[-1]
        kdj_d = df["D"].iloc[-1]
        kdj_j = df["J"].iloc[-1]

        # Сигнал
        last_close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]
        if last_close > prev_close:
            signal = "🔺 LONG (вверх)"
        elif last_close < prev_close:
            signal = "🔻 SHORT (вниз)"
        else:
            signal = "⚪️ NEUTRAL"

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
📊 SMA(20): {round(sma20, 2)}
📊 Bollinger Mid: {round(bb_mid, 2)}
📊 Williams %R: {round(williams_r, 2)}
📊 MAVOL(20): {round(mavol, 2)}
📊 KDJ:
   🔹 K: {round(kdj_k, 2)}
   🔸 D: {round(kdj_d, 2)}
   🔻 J: {round(kdj_j, 2)}
📌 Сигнал: {signal}
        """)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()
