import telebot
import pandas as pd
import sqlite3
import time
import threading
import openai
import os
from pybit.unified_trading import HTTP
from ta import trend, momentum, volatility, volume
from datetime import datetime
from dotenv import load_dotenv

# === Загрузка переменных окружения ===
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AUTHORIZED_USER_ID = 1311705654

# === ИНИЦИАЛИЗАЦИЯ ===
bot = telebot.TeleBot(BOT_TOKEN)
session = HTTP(api_key=API_KEY, api_secret=API_SECRET)
openai.api_key = OPENAI_API_KEY

# === СОЗДАНИЕ БД ===
conn = sqlite3.connect('accuracy.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS predictions
              (timestamp TEXT, prediction TEXT, result TEXT)''')
conn.commit()

# === ЗАПРОС К CHATGPT ===
def ask_chatgpt(prompt):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Ты аналитик крипторынка. Объясни кратко трейдеру смысл прогноза на основе голосов индикаторов."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ Ошибка при обращении к ChatGPT: {e}"

# === ПОЛУЧЕНИЕ ДАННЫХ ===
def get_klines(symbol="BTCUSDT", interval="15", limit=100):
    data = session.get_kline(
        category="linear",
        symbol=symbol,
        interval=interval,
        limit=limit
    )["result"]["list"]
    df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
    return df

# === ИНДИКАТОРЫ ===
def calculate_indicators(df):
    df["rsi"] = momentum.RSIIndicator(df["close"]).rsi()
    df["ema21"] = trend.EMAIndicator(df["close"], window=21).ema_indicator()
    df["adx"] = trend.ADXIndicator(df["high"], df["low"], df["close"]).adx()
    df["cci"] = trend.CCIIndicator(df["high"], df["low"], df["close"]).cci()
    df["stoch_k"] = momentum.StochasticOscillator(df["high"], df["low"], df["close"]).stoch()
    df["roc"] = momentum.ROCIndicator(df["close"]).roc()
    df["sma20"] = trend.SMAIndicator(df["close"], window=20).sma_indicator()
    bb = volatility.BollingerBands(df["close"])
    df["bb_bbm"] = bb.bollinger_mavg()
    df["wr"] = momentum.WilliamsRIndicator(df["high"], df["low"], df["close"]).williams_r()
    df["obv"] = volume.OnBalanceVolumeIndicator(df["close"], df["volume"]).on_balance_volume()
    df.dropna(inplace=True)
    return df

# === ПРЕДСКАЗАНИЕ ===
def make_prediction(df):
    last = df.iloc[-1]
    votes = []

    if last["rsi"] < 30: votes.append("RSI=LONG")
    elif last["rsi"] > 70: votes.append("RSI=SHORT")

    if last["close"] > last["ema21"]: votes.append("EMA21=LONG")
    else: votes.append("EMA21=SHORT")

    if last["adx"] > 25: votes.append("ADX=TREND")
    if last["cci"] > 100: votes.append("CCI=LONG")
    elif last["cci"] < -100: votes.append("CCI=SHORT")

    if last["stoch_k"] < 20: votes.append("Stoch=LONG")
    elif last["stoch_k"] > 80: votes.append("Stoch=SHORT")

    if last["roc"] > 0: votes.append("ROC=LONG")
    else: votes.append("ROC=SHORT")

    if last["close"] > last["sma20"]: votes.append("SMA20=LONG")
    else: votes.append("SMA20=SHORT")

    if last["close"] > last["bb_bbm"]: votes.append("BOLL=LONG")
    else: votes.append("BOLL=SHORT")

    if last["wr"] < -80: votes.append("WR=LONG")
    elif last["wr"] > -20: votes.append("WR=SHORT")

    long_votes = [v for v in votes if "=LONG" in v]
    short_votes = [v for v in votes if "=SHORT" in v]

    if len(long_votes) > len(short_votes):
        signal = "LONG"
    elif len(short_votes) > len(long_votes):
        signal = "SHORT"
    else:
        signal = "NEUTRAL"

    return signal, votes

# === ОБРАБОТКА КОМАНД ===
@bot.message_handler(commands=["start", "signal"])
def handle_command(message):
    if message.from_user.id != AUTHORIZED_USER_ID:
        return

    if message.text == "/start":
        bot.send_message(message.chat.id, "✅ Бот активен. Используйте /signal для прогноза.")
    elif message.text == "/signal":
        df = calculate_indicators(get_klines())
        prediction, votes = make_prediction(df)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO predictions (timestamp, prediction, result) VALUES (?, ?, ?)", (timestamp, prediction, "pending"))
        conn.commit()

        vote_text = "\n".join(votes)
        prompt = f"Прогноз: {prediction}\nГолоса:\n{vote_text}"
        explanation = ask_chatgpt(prompt)

        bot.send_message(message.chat.id, f"\ud83d\udcca Прогноз: *{prediction}*\n\n\ud83e\udde0 Объяснение от GPT:\n{explanation}", parse_mode="Markdown")

# === АВТОПРОГНОЗ ===
def auto_update():
    while True:
        try:
            df = calculate_indicators(get_klines())
            prediction, votes = make_prediction(df)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("INSERT INTO predictions (timestamp, prediction, result) VALUES (?, ?, ?)", (timestamp, prediction, "pending"))
            conn.commit()
            prompt = f"Прогноз: {prediction}\nГолоса:\n{chr(10).join(votes)}"
            explanation = ask_chatgpt(prompt)
            bot.send_message(AUTHORIZED_USER_ID, f"\u23f0 Авто-прогноз: *{prediction}*\n\ud83e\udde0 GPT:\n{explanation}", parse_mode="Markdown")
        except Exception as e:
            print(f"[Ошибка автообновления]: {e}")
        time.sleep(900)  # каждые 15 минут

threading.Thread(target=auto_update, daemon=True).start()

# === ЗАПУСК БОТА ===
bot.polling(none_stop=True)
