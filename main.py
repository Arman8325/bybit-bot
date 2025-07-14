import os
import telebot
from telebot import types
from pybit.unified_trading import HTTP
import ta
import pandas as pd
import requests

# Инициализация переменных среды
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

bot = telebot.TeleBot(BOT_TOKEN)
session = HTTP(api_key=API_KEY, api_secret=API_SECRET)

# Получение и расчет индикаторов
def fetch_technical_data(symbol="BTCUSDT", interval="15", limit=100):
    candles = session.get_kline(
        category="linear",
        symbol=symbol,
        interval=interval,
        limit=limit
    )
    df = pd.DataFrame(candles["result"]["list"], columns=[
        "timestamp", "open", "high", "low", "close", "volume", "turnover"])

    df["close"] = df["close"].astype(float)
    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["volume"] = df["volume"].astype(float)

    df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
    df["ema"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()
    macd = ta.trend.MACD(df["close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()

    return df.iloc[-1]

# Генерация сигнала на основе индикаторов
def analyze_signals(row):
    decisions = []

    if row["rsi"] < 30:
        decisions.append("RSI перепродан → LONG")
    elif row["rsi"] > 70:
        decisions.append("RSI перекуплен → SHORT")
    else:
        decisions.append("RSI нейтральный")

    if row["close"] > row["ema"]:
        decisions.append("Цена выше EMA → LONG")
    else:
        decisions.append("Цена ниже EMA → SHORT")

    if row["macd"] > row["macd_signal"]:
        decisions.append("MACD бычий → LONG")
    else:
        decisions.append("MACD медвежий → SHORT")

    score = sum(["LONG" in d for d in decisions]) - sum(["SHORT" in d for d in decisions])
    if score > 0:
        final = "📈 Рекомендация: LONG (вверх)"
    elif score < 0:
        final = "📉 Рекомендация: SHORT (вниз)"
    else:
        final = "⚖️ Рекомендация: Нейтрально"

    return "\n".join(decisions + [final])

# Команды
@bot.message_handler(commands=["start"])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("📈 Получить сигнал")
    markup.add(btn1)
    bot.send_message(message.chat.id, "Привет! Я трейдинг-бот. Нажми кнопку, чтобы получить сигнал.", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "📈 Получить сигнал")
@bot.message_handler(commands=["signal"])
def signal(message):
    try:
        bot.send_message(message.chat.id, "⏳ Получаю данные от Bybit...")
        row = fetch_technical_data()
        result = analyze_signals(row)

        bot.send_message(message.chat.id, f"📊 Закрытие: {row['close']:.2f}\n📈 RSI: {row['rsi']:.2f}\n📉 EMA: {row['ema']:.2f}\nMACD: {row['macd']:.2f}, сигнальная: {row['macd_signal']:.2f}\n\n{result}")
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

bot.polling(none_stop=True)





