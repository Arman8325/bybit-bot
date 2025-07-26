import telebot
from telebot import types
import pandas as pd
import sqlite3
import time
import threading
import matplotlib.pyplot as plt
import io
from pybit.unified_trading import HTTP
from ta import trend, momentum, volatility, volume
from datetime import datetime

# === НАСТРОЙКИ ===
BOT_TOKEN = '7725284250:AAFQi1jp4yWefZJExHlXOoLQWEPLdrnuk4w'
API_KEY = 'IyFHgr8YtnCz60D27D'
API_SECRET = 'kxj3fry4US9lZq2nyDZIVKMgSaTd7U7vPp53'
AUTHORIZED_USER_ID = 1311705654

bot = telebot.TeleBot(BOT_TOKEN)
session = HTTP(api_key=API_KEY, api_secret=API_SECRET)

# === ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ===
conn = sqlite3.connect('accuracy.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS predictions
              (timestamp TEXT, prediction TEXT, result TEXT)''')
conn.commit()
def get_klines(symbol="BTCUSDT", interval="15", limit=100):
    data = session.get_kline(
        category="linear",
        symbol=symbol,
        interval=interval,
        limit=limit
    )["result"]["list"]
    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close", "volume", "turnover"
    ])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
    return df

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
# === СООБЩЕНИЕ С КНОПКАМИ ===
def send_main_menu(chat_id, text):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('/signal', '/verify', '/accuracy')
    bot.send_message(chat_id, text, reply_markup=markup)

# === ОБРАБОТЧИКИ КОМАНД ===
@bot.message_handler(commands=["start"])
def handle_start(message):
    if message.from_user.id != AUTHORIZED_USER_ID:
        bot.reply_to(message, "❌ У вас нет доступа.")
        return
    send_main_menu(message.chat.id, "✅ Бот активен. Выберите действие:")

@bot.message_handler(commands=["signal"])
def handle_signal(message):
    if message.from_user.id != AUTHORIZED_USER_ID:
        bot.reply_to(message, "❌ Нет доступа.")
        return
    df = calculate_indicators(get_klines())
    prediction = make_prediction(df)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO predictions (timestamp, prediction, result) VALUES (?, ?, ?)", (timestamp, prediction, "pending"))
    conn.commit()
    bot.send_message(message.chat.id, f"📊 Прогноз на 15 минут: *{prediction}*", parse_mode="Markdown")

@bot.message_handler(commands=["verify"])
def handle_verify(message):
    if message.from_user.id != AUTHORIZED_USER_ID:
        bot.reply_to(message, "❌ Нет доступа.")
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("✅ Правильно", "❌ Ошибка", "🔙 Назад")
    bot.send_message(message.chat.id, "📌 Последний прогноз был правильный?", reply_markup=markup)

@bot.message_handler(commands=["accuracy"])
def handle_accuracy(message):
    if message.from_user.id != AUTHORIZED_USER_ID:
        bot.reply_to(message, "❌ Нет доступа.")
        return
    cursor.execute("SELECT * FROM predictions WHERE result != 'pending'")
    rows = cursor.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "Нет данных для анализа.")
        return

    timestamps = [row[0] for row in rows]
    results = [1 if row[1] == row[2] else 0 for row in rows]
    accuracy = pd.Series(results).rolling(5).mean() * 100

    plt.figure(figsize=(8, 4))
    plt.plot(timestamps, accuracy, label="Точность (%)", color='blue')
    plt.xticks(rotation=45)
    plt.title("📈 Точность прогнозов")
    plt.xlabel("Время")
    plt.ylabel("% попаданий")
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    bot.send_photo(message.chat.id, photo=buf, caption="📊 Динамика точности")
    buf.close()

# === ОБРАБОТКА ОТВЕТА НА /verify ===
@bot.message_handler(func=lambda m: m.text in ["✅ Правильно", "❌ Ошибка"])
def handle_verification(m):
    if m.from_user.id != AUTHORIZED_USER_ID:
        return
    cursor.execute("SELECT rowid FROM predictions WHERE result = 'pending' ORDER BY rowid DESC LIMIT 1")
    last = cursor.fetchone()
    if last:
        result = "LONG" if m.text == "✅ Правильно" else "SHORT" if m.text == "❌ Ошибка" else "neutral"
        cursor.execute("UPDATE predictions SET result = ? WHERE rowid = ?", (result, last[0]))
        conn.commit()
        bot.send_message(m.chat.id, "✅ Результат записан.")
    else:
        bot.send_message(m.chat.id, "⛔ Нет неподтверждённых прогнозов.")

# === АВТООБНОВЛЕНИЕ ПРОГНОЗОВ ===
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
            print(f"[ОШИБКА автообновления]: {e}")
        time.sleep(15 * 60)  # каждые 15 минут

threading.Thread(target=auto_update, daemon=True).start()

# === СТАРТ БОТА ===
bot.polling(none_stop=True)
