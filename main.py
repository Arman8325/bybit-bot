import telebot
import pandas as pd
import sqlite3
import time
import threading
from pybit.unified_trading import HTTP
from ta import trend, momentum, volatility, volume
from datetime import datetime

# === НАСТРОЙКИ ===
BOT_TOKEN = 'ВАШ_ТЕЛЕГРАМ_БОТ_ТОКЕН'
API_KEY = 'ВАШ_BYBIT_API_KEY'
API_SECRET = 'ВАШ_BYBIT_API_SECRET'
import telebot
import pandas as pd
import sqlite3
import time
import threading
from pybit.unified_trading import HTTP
from ta import trend, momentum, volatility, volume
from datetime import datetime

# === НАСТРОЙКИ ===
BOT_TOKEN = 'ВАШ_ТЕЛЕГРАМ_БОТ_ТОКЕН'
API_KEY = 'ВАШ_BYBIT_API_KEY'
API_SECRET = 'ВАШ_BYBIT_API_SECRET'
AUTHORIZED_USER_ID = 1311705654

bot = telebot.TeleBot(BOT_TOKEN)
session = HTTP(api_key=API_KEY, api_secret=API_SECRET)

# === СОЗДАНИЕ БД ===
conn = sqlite3.connect('accuracy.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS predictions
              (timestamp TEXT, prediction TEXT, result TEXT)''')
conn.commit()

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

    if last["rsi"] < 30: votes.append("long")
    elif last["rsi"] > 70: votes.append("short")

    if last["close"] > last["ema21"]: votes.append("long")
    else: votes.append("short")

    if last["adx"] > 25: votes.append("trend")
    if last["cci"] > 100: votes.append("long")
    elif last["cci"] < -100: votes.append("short")

    if last["stoch_k"] < 20: votes.append("long")
    elif last["stoch_k"] > 80: votes.append("short")

    if last["roc"] > 0: votes.append("long")
    else: votes.append("short")

    if last["close"] > last["sma20"]: votes.append("long")
    else: votes.append("short")

    if last["close"] > last["bb_bbm"]: votes.append("long")
    else: votes.append("short")

    if last["wr"] < -80: votes.append("long")
    elif last["wr"] > -20: votes.append("short")

    long_votes = votes.count("long")
    short_votes = votes.count("short")

    if long_votes > short_votes:
        return "LONG"
    elif short_votes > long_votes:
        return "SHORT"
    else:
        return "NEUTRAL"

# === ОБРАБОТКА КОМАНД ===
@bot.message_handler(commands=["start", "signal"])
def handle_command(message):
    if message.from_user.id != AUTHORIZED_USER_ID:
        return

    if message.text == "/start":
        bot.send_message(message.chat.id, "✅ Бот активен. Используйте /signal для прогноза.")
    elif message.text == "/signal":
        df = calculate_indicators(get_klines())
        prediction = make_prediction(df)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO predictions (timestamp, prediction, result) VALUES (?, ?, ?)", (timestamp, prediction, "pending"))
        conn.commit()
        bot.send_message(message.chat.id, f"📊 Прогноз на следующие 15 минут: *{prediction}*", parse_mode="Markdown")

# === АВТОПРОГНОЗ ===
def auto_update():
    while True:
        try:
            df = calculate_indicators(get_klines())
            prediction = make_prediction(df)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("INSERT INTO predictions (timestamp, prediction, result) VALUES (?, ?, ?)", (timestamp, prediction, "pending"))
            conn.commit()
            bot.send_message(AUTHORIZED_USER_ID, f"🔄 Авто-прогноз: *{prediction}*", parse_mode="Markdown")
        except Exception as e:
            print(f"[Ошибка автообновления]: {e}")
        time.sleep(15 * 60)

threading.Thread(target=auto_update, daemon=True).start()

# === СТАРТ БОТА ===
bot.polling(none_stop=True)


bot = telebot.TeleBot(BOT_TOKEN)
session = HTTP(api_key=API_KEY, api_secret=API_SECRET)

# === СОЗДАНИЕ БД ===
conn = sqlite3.connect('accuracy.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS predictions
              (timestamp TEXT, prediction TEXT, result TEXT)''')
conn.commit()

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

    if last["rsi"] < 30: votes.append("long")
    elif last["rsi"] > 70: votes.append("short")

    if last["close"] > last["ema21"]: votes.append("long")
    else: votes.append("short")

    if last["adx"] > 25: votes.append("trend")
    if last["cci"] > 100: votes.append("long")
    elif last["cci"] < -100: votes.append("short")

    if last["stoch_k"] < 20: votes.append("long")
    elif last["stoch_k"] > 80: votes.append("short")

    if last["roc"] > 0: votes.append("long")
    else: votes.append("short")

    if last["close"] > last["sma20"]: votes.append("long")
    else: votes.append("short")

    if last["close"] > last["bb_bbm"]: votes.append("long")
    else: votes.append("short")

    if last["wr"] < -80: votes.append("long")
    elif last["wr"] > -20: votes.append("short")

    long_votes = votes.count("long")
    short_votes = votes.count("short")

    if long_votes > short_votes:
        return "LONG"
    elif short_votes > long_votes:
        return "SHORT"
    else:
        return "NEUTRAL"

# === ОБРАБОТКА КОМАНД ===
@bot.message_handler(commands=["start", "signal"])
def handle_command(message):
    if message.from_user.id != AUTHORIZED_USER_ID:
        return

    if message.text == "/start":
        bot.send_message(message.chat.id, "✅ Бот активен. Используйте /signal для прогноза.")
    elif message.text == "/signal":
        df = calculate_indicators(get_klines())
        prediction = make_prediction(df)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO predictions (timestamp, prediction, result) VALUES (?, ?, ?)", (timestamp, prediction, "pending"))
        conn.commit()
        bot.send_message(message.chat.id, f"📊 Прогноз на следующие 15 минут: *{prediction}*", parse_mode="Markdown")

# === АВТОПРОГНОЗ ===
def auto_update():
    while True:
        try:
            df = calculate_indicators(get_klines())
            prediction = make_prediction(df)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("INSERT INTO predictions (timestamp, prediction, result) VALUES (?, ?, ?)", (timestamp, prediction, "pending"))
            conn.commit()
            bot.send_message(AUTHORIZED_USER_ID, f"🔄 Авто-прогноз: *{prediction}*", parse_mode="Markdown")
        except Exception as e:
            print(f"[Ошибка автообновления]: {e}")
        time.sleep(15 * 60)

threading.Thread(target=auto_update, daemon=True).start()

# === СТАРТ БОТА ===
bot.polling(none_stop=True)
