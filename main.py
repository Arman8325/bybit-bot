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
        df["volume"] = df["volume"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)

        # RSI, EMA, ADX, CCI, Stochastic, Momentum уже были добавлены
        rsi = ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1]
        ema = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1]
        adx = ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1]
        cci = ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1]
        stoch = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"]).stoch().iloc[-1]
        mom = ta.momentum.MomentumIndicator(df["close"]).momentum().iloc[-1]

        # ✅ Новый индикатор — Bollinger Bands
        bb = ta.volatility.BollingerBands(df["close"])
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_middle = bb.bollinger_mavg().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]

        last_close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]

        if last_close > prev_close:
            signal = "🔺 LONG"
        elif last_close < prev_close:
            signal = "🔻 SHORT"
        else:
            signal = "➖ Без изменений"

        # Ответ пользователю
        bot.send_message(message.chat.id, f"""
📈 Закрытие: {last_close}
📉 Предыдущая: {prev_close}
📊 RSI: {round(rsi, 2)} | EMA21: {round(ema, 2)}
📉 ADX: {round(adx, 2)} | CCI: {round(cci, 2)}
📈 Stochastic: {round(stoch, 2)} | Momentum: {round(mom, 2)}
📎 Bollinger Bands:
   🔼 Верхняя: {round(bb_upper, 2)}
   🔹 Средняя: {round(bb_middle, 2)}
   🔽 Нижняя: {round(bb_lower, 2)}
📌 Сигнал: {signal}
        """)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()
