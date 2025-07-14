# Обновлённый Telegram-бот: получает данные с Bybit, отправляет в ChatGPT и возвращает ответ в Telegram

from flask import Flask, request
import telebot
import threading
import os
import openai
from pybit.unified_trading import HTTP

# Получение ключей из переменных окружения
API_KEY = os.environ.get("BYBIT_API_KEY")
API_SECRET = os.environ.get("BYBIT_API_SECRET")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not all([API_KEY, API_SECRET, BOT_TOKEN, OPENAI_API_KEY]):
    raise EnvironmentError("Одна или несколько переменных окружения не установлены")

# Инициализация
bot = telebot.TeleBot(BOT_TOKEN)
session = HTTP(api_key=API_KEY, api_secret=API_SECRET, testnet=False)
openai.api_key = OPENAI_API_KEY

app = Flask(__name__)

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "✅ Бот запущен! Используй /signal, чтобы получить рекомендацию.")

@bot.message_handler(commands=['signal'])
def get_signal(message):
    try:
        bot.send_message(message.chat.id, "⏳ Получаю данные от Bybit...")

        candles = session.get_kline(category="linear", symbol="BTCUSDT", interval="15", limit=100)

        if not candles.get('result') or not candles['result'].get('list'):
            bot.send_message(message.chat.id, "❌ Не удалось получить данные о свечах.")
            return

        # Анализ по 13 индикаторам (эмуляция примера)
        market_data = {
            "RSI": 54.2,
            "MACD": 1.7,
            "EMA20": 116800,
            "EMA50": 117200,
            "EMA200": 118000,
            "SMA20": 116950,
            "SMA50": 117300,
            "SMA200": 118100,
            "Bollinger_Upper": 117800,
            "Bollinger_Lower": 116400,
            "Stochastic_K": 65,
            "Stochastic_D": 60,
            "ADX": 24
        }

        prompt = f"""
Вот рыночные данные по BTC/USDT:
{market_data}

На основе этих технических индикаторов, выдай профессиональную краткую рекомендацию:
— направление (LONG или SHORT),
— сила сигнала (слабый, средний, сильный),
— краткое объяснение.
"""

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Ты профессиональный криптоаналитик, кратко и точно даёшь советы трейдерам."},
                {"role": "user", "content": prompt}
            ]
        )

        answer = response.choices[0].message.content.strip()
        bot.send_message(message.chat.id, f"📈 Сигнал от ChatGPT:
{answer}")

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка при получении сигнала: {str(e)}")

threading.Thread(target=bot.polling, kwargs={"none_stop": True, "timeout": 60}, daemon=True).start()

@app.route('/')
def home():
    return '🤖 Бот работает на Railway!'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))


