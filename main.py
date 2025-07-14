# Railway альтернатива Render для запуска Telegram-трейдинг-бота
# Этот код будет частью backend-приложения, которое мы разместим в Railway (работает из Армении без VPN)

from flask import Flask, request
import telebot
from pybit.unified_trading import HTTP
import threading
import os
import ta
import pandas as pd
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

API_KEY = os.environ.get("BYBIT_API_KEY")
API_SECRET = os.environ.get("BYBIT_API_SECRET")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not all([API_KEY, API_SECRET, BOT_TOKEN]):
    raise EnvironmentError("Не установлены переменные окружения: BYBIT_API_KEY, BYBIT_API_SECRET или TELEGRAM_BOT_TOKEN")

bot = telebot.TeleBot(BOT_TOKEN)
session = HTTP(api_key=API_KEY, api_secret=API_SECRET, testnet=False)

app = Flask(__name__)

# Стартовое сообщение с клавиатурой
@bot.message_handler(commands=['start'])
def start_message(message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("📈 Получить сигнал"))
    bot.send_message(message.chat.id, "✅ Бот запущен! Нажмите кнопку ниже, чтобы получить сигнал:", reply_markup=markup)

# Анализ сигнала по свечам и индикаторам
@bot.message_handler(func=lambda message: message.text == "📈 Получить сигнал" or message.text == "/signal")
def get_signal(message):
    try:
        bot.send_message(message.chat.id, "⏳ Получаю данные от Bybit...")
        candles = session.get_kline(category="linear", symbol="BTCUSDT", interval="15", limit=100)

        if not candles.get('result') or not candles['result'].get('list'):
            bot.send_message(message.chat.id, "❌ Не удалось получить данные о свечах.")
            return

        df = pd.DataFrame(candles['result']['list'], columns=[
            "timestamp", "open", "high", "low", "close", "volume", "turnover"
        ])
        df = df.astype(float)

        # Расчёт индикаторов
        df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()
        df['ema20'] = ta.trend.EMAIndicator(close=df['close'], window=20).ema_indicator()
        df['sma50'] = ta.trend.SMAIndicator(close=df['close'], window=50).sma_indicator()
        macd = ta.trend.MACD(close=df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        boll = ta.volatility.BollingerBands(close=df['close'], window=20)
        df['bb_upper'] = boll.bollinger_hband()
        df['bb_lower'] = boll.bollinger_lband()

        last = df.iloc[-1]
        prev = df.iloc[-2]

        # Простейшая логика для сигнала
        direction = "🔺 LONG (вверх)" if last['close'] > prev['close'] else "🔻 SHORT (вниз)"

        # Объединённый ответ
        response = (
            f"📊 Закрытие: {last['close']:.2f}\n"
            f"📉 Предыдущее: {prev['close']:.2f}\n"
            f"ℹ️ RSI: {last['rsi']:.2f} ({'Перекупленность 🔴' if last['rsi'] > 70 else 'Перепроданность 🟢' if last['rsi'] < 30 else 'Нейтрально ➖'})\n"
            f"📏 EMA(20): {last['ema20']:.2f}\n"
            f"📐 SMA(50): {last['sma50']:.2f}\n"
            f"💹 MACD: {last['macd']:.2f} / Сигнал: {last['macd_signal']:.2f}\n"
            f"📎 Bollinger: Верх {last['bb_upper']:.2f} / Низ {last['bb_lower']:.2f}\n"
            f"📌 Сигнал: {direction}"
        )

        bot.send_message(message.chat.id, response)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка при получении сигнала:\n{str(e)}")

threading.Thread(target=bot.polling, kwargs={"none_stop": True, "timeout": 60}, daemon=True).start()

@app.route('/')
def home():
    return 'Бот работает на Railway!'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))



