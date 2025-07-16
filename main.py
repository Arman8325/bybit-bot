import telebot
import numpy as np
import talib
from pybit.unified_trading import HTTP

# Временно вставленные токены (замени своими при необходимости)
TELEGRAM_BOT_TOKEN = 7725284250:AAFQi1jp4yWefZJExHlXOoLQWEPLdrnuk4w
BYBIT_API_KEY = "IyFHgr8YtnCz60D27D"
BYBIT_API_SECRET = "kxj3fry4US9lZq2nyDZIVKMgSaTd7U7vPp53"

# Инициализация
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

# Получение данных свечей
def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    try:
        response = session.get_kline(
            category="linear",
            symbol=symbol,
            interval=interval,
            limit=limit
        )
        return response["result"]["list"]
    except Exception as e:
        print("Ошибка получения свечей:", e)
        return None

# Анализ индикаторов без ChatGPT
def analyze_indicators(candle_data):
    closes = np.array([float(c[4]) for c in candle_data], dtype=float)
    highs = np.array([float(c[2]) for c in candle_data], dtype=float)
    lows = np.array([float(c[3]) for c in candle_data], dtype=float)
    volumes = np.array([float(c[5]) for c in candle_data], dtype=float)

    rsi = talib.RSI(closes, timeperiod=14)[-1]
    macd, macdsignal, _ = talib.MACD(closes)
    ema_fast = talib.EMA(closes, timeperiod=9)[-1]
    ema_slow = talib.EMA(closes, timeperiod=21)[-1]

    # Простой вывод сигнала
    if rsi > 70 and ema_fast < ema_slow and macd[-1] < macdsignal[-1]:
        signal = "🔻 SHORT (вниз)"
    elif rsi < 30 and ema_fast > ema_slow and macd[-1] > macdsignal[-1]:
        signal = "🔺 LONG (вверх)"
    else:
        signal = "➖ NEUTRAL (вне рынка)"

    return {
        "close": closes[-1],
        "previous": closes[-2],
        "rsi": round(rsi, 2),
        "macd": round(macd[-1], 2),
        "macd_signal": round(macdsignal[-1], 2),
        "ema9": round(ema_fast, 2),
        "ema21": round(ema_slow, 2),
        "volume": round(volumes[-1], 2),
        "signal": signal
    }

# Обработка команды /signal
@bot.message_handler(commands=['signal'])
def get_signal(message):
    bot.send_message(message.chat.id, "⏳ Получаю данные от Bybit...")
    candles = get_candles()
    if not candles:
        bot.send_message(message.chat.id, "⚠️ Не удалось получить данные от Bybit")
        return

    indicators = analyze_indicators(candles)

    reply = f"""
📊 Закрытие: {indicators['close']}
📉 Предыдущее: {indicators['previous']}
ℹ️ RSI: {indicators['rsi']}
📉 MACD: {indicators['macd']}, сигнал: {indicators['macd_signal']}
📈 EMA9: {indicators['ema9']}, EMA21: {indicators['ema21']}
📊 Объём: {indicators['volume']}
📌 Сигнал: {indicators['signal']}
    """
    bot.send_message(message.chat.id, reply)

# Запуск бота
print("✅ Бот запущен!")
bot.polling()

