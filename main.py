import os
import io
import telebot
import pandas as pd
import matplotlib.pyplot as plt
from pybit.unified_trading import HTTP
import ta

# Инициализация
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    candles = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
    return candles["result"]["list"]

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal для прогноза и графика.")

@bot.message_handler(commands=['signal'])
def send_signal(message):
    bot.send_message(message.chat.id, "📊 Получаю данные от Bybit...")
    try:
        data = get_candles()
        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df = df.astype(float)

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # Индикаторы
        rsi = ta.momentum.RSIIndicator(close).rsi().iloc[-1]
        ema21 = ta.trend.EMAIndicator(close, 21).ema_indicator().iloc[-1]
        adx = ta.trend.ADXIndicator(high, low, close).adx().iloc[-1]
        cci = ta.trend.CCIIndicator(high, low, close).cci().iloc[-1]
        stoch = ta.momentum.StochasticOscillator(high, low, close).stoch().iloc[-1]
        momentum = ta.momentum.ROCIndicator(close).roc().iloc[-1]
        bb = ta.volatility.BollingerBands(close)
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        wr = ta.momentum.WilliamsRIndicator(high, low, close).williams_r().iloc[-1]
        ma = close.rolling(window=20).mean().iloc[-1]
        obv = ta.volume.OnBalanceVolumeIndicator(close, volume).on_balance_volume().iloc[-1]
        macd = ta.trend.MACD(close).macd().iloc[-1]
        mavol = volume.rolling(window=20).mean().iloc[-1]
        kdj = ((close - low.rolling(14).min()) / (high.rolling(14).max() - low.rolling(14).min()) * 100).iloc[-1]
        stochrsi = ta.momentum.StochRSIIndicator(close).stochrsi().iloc[-1]
        sar = ta.trend.PSARIndicator(high, low, close).psar().iloc[-1]

        last_close = close.iloc[-1]
        prev_close = close.iloc[-2]

        # Логика прогноза
        long_conditions = [
            rsi > 50,
            ema21 < last_close,
            adx > 20,
            cci > 0,
            stoch > 50,
            momentum > 0,
            last_close > bb.bollinger_mavg().iloc[-1],
            wr > -50,
            macd > 0,
            kdj > 50,
            stochrsi > 0.5,
            last_close > sar
        ]

        short_conditions = [
            rsi < 50,
            ema21 > last_close,
            adx > 20,
            cci < 0,
            stoch < 50,
            momentum < 0,
            last_close < bb.bollinger_mavg().iloc[-1],
            wr < -50,
            macd < 0,
            kdj < 50,
            stochrsi < 0.5,
            last_close < sar
        ]

        if sum(long_conditions) > 7:
            forecast = "🔺 Прогноз: LONG (вверх)"
        elif sum(short_conditions) > 7:
            forecast = "🔻 Прогноз: SHORT (вниз)"
        else:
            forecast = "⚪️ Прогноз: NEUTRAL (боковой рынок)"

        # Формируем текст
        text = f"""
📈 Закрытие: {last_close}
📉 Предыдущее: {prev_close}
📊 RSI: {round(rsi, 2)}
📈 EMA21: {round(ema21, 2)}
📊 ADX: {round(adx, 2)}
📊 CCI: {round(cci, 2)}
📊 Stochastic: {round(stoch, 2)}
📊 Momentum: {round(momentum, 2)}
📊 Bollinger Bands: 🔺 {round(bb_upper, 2)} 🔻 {round(bb_lower, 2)}
📊 Williams %R: {round(wr, 2)}
📊 MA(20): {round(ma, 2)}
📊 OBV: {round(obv, 2)}
📊 MACD: {round(macd, 2)}
📊 MAVOL: {round(mavol, 2)}
📊 KDJ: {round(kdj, 2)}
📊 StochRSI: {round(stochrsi, 2)}
📊 SAR: {round(sar, 2)}
📌 {forecast}
        """

        bot.send_message(message.chat.id, text)

        # Построение графика
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(df["close"], label="Цена", linewidth=1.5)
        ax.plot(ta.trend.EMAIndicator(close, 21).ema_indicator(), label="EMA21", linestyle='--')
        ax.plot(bb.bollinger_hband(), label="BB Верхняя", linestyle=':')
        ax.plot(bb.bollinger_lband(), label="BB Нижняя", linestyle=':')
        ax.set_title("График BTC/USDT")
        ax.legend()
        ax.grid()

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close(fig)

        bot.send_photo(message.chat.id, photo=buf)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling()
