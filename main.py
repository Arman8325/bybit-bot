import telebot
from telebot import types
import os
import pandas as pd
from pybit.unified_trading import HTTP
from datetime import datetime, timedelta
import ta
import sqlite3
import threading
import time
from dotenv import load_dotenv
import matplotlib.pyplot as plt
import io

# === Загрузка переменных окружения ===
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
AUTHORIZED_USER_ID = 1311705654

bot = telebot.TeleBot(BOT_TOKEN)
session = HTTP(api_key=API_KEY, api_secret=API_SECRET)

# === БД SQLite ===
conn = sqlite3.connect("predictions.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    price REAL,
    signal TEXT,
    actual TEXT,
    votes TEXT,
    timeframe TEXT
)
""")
conn.commit()

# === Получение свечей ===
def get_candles(symbol="BTCUSDT", interval="15", limit=100):
    candles = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
    return candles["result"]["list"]

# === Расчёт индикаторов ===
def analyze_indicators(df):
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)

    indicators = {
        "RSI": ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1],
        "EMA21": ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1],
        "ADX": ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1],
        "CCI": ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1],
        "Stochastic": ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"]).stoch().iloc[-1],
        "Momentum": ta.momentum.ROCIndicator(df["close"]).roc().iloc[-1],
        "BOLL_UP": ta.volatility.BollingerBands(df["close"]).bollinger_hband().iloc[-1],
        "BOLL_LOW": ta.volatility.BollingerBands(df["close"]).bollinger_lband().iloc[-1],
        "SAR": ta.trend.PSARIndicator(df["high"], df["low"], df["close"]).psar().iloc[-1],
        "MACD": ta.trend.MACD(df["close"]).macd().iloc[-1],
        "WR": ta.momentum.WilliamsRIndicator(df["high"], df["low"], df["close"]).williams_r().iloc[-1]
    }
    return indicators

# === Прогноз ===
def make_prediction(ind, last_close):
    votes = []
    if ind["RSI"] > 60: votes.append("LONG")
    elif ind["RSI"] < 40: votes.append("SHORT")
    votes.append("LONG" if last_close > ind["EMA21"] else "SHORT")
    if ind["ADX"] > 25: votes.append("LONG")
    if ind["CCI"] > 100: votes.append("LONG")
    elif ind["CCI"] < -100: votes.append("SHORT")
    if ind["Stochastic"] > 80: votes.append("SHORT")
    elif ind["Stochastic"] < 20: votes.append("LONG")
    votes.append("LONG" if ind["Momentum"] > 0 else "SHORT")
    if last_close > ind["BOLL_UP"]: votes.append("SHORT")
    elif last_close < ind["BOLL_LOW"]: votes.append("LONG")
    votes.append("LONG" if last_close > ind["SAR"] else "SHORT")
    votes.append("LONG" if ind["MACD"] > 0 else "SHORT")
    if ind["WR"] < -80: votes.append("LONG")
    elif ind["WR"] > -20: votes.append("SHORT")

    long_count = votes.count("LONG")
    short_count = votes.count("SHORT")
    signal = "LONG" if long_count > short_count else "SHORT" if short_count > long_count else "NEUTRAL"
    return signal, votes

# === Отправка сигнала ===
def process_signal(chat_id, interval):
    raw = get_candles(interval=interval)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
    indicators = analyze_indicators(df)
    last = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2])
    signal, votes = make_prediction(indicators, last)

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO predictions (timestamp, price, signal, actual, votes, timeframe) VALUES (?, ?, ?, ?, ?, ?)",
                   (timestamp, last, signal, None, ",".join(votes), interval))
    conn.commit()

    text = f"\ud83d\udcc8 Закрытие: {last}\n\ud83d\udcc9 Предыдущее: {prev}\n"
    for key, val in indicators.items():
        text += f"\ud83d\udd39 {key}: {round(val, 2)}\n"
    text += f"\n\ud83d\udccc Прогноз на следующие {interval} минут: {'\ud83d\udd3a LONG' if signal == 'LONG' else '\ud83d\udd3b SHORT' if signal == 'SHORT' else '\u26aa\ufe0f NEUTRAL'}\n\ud83e\udde0 Голоса: {votes}"
    bot.send_message(chat_id, text)

# === Кнопки ===
def main_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("\ud83d\udd52 15м", callback_data="tf_15"),
        types.InlineKeyboardButton("\ud83d\udd5e 30м", callback_data="tf_30"),
        types.InlineKeyboardButton("\ud83d\udd50 1ч", callback_data="tf_60")
    )
    markup.row(
        types.InlineKeyboardButton("\ud83d\udccd Проверка", callback_data="verify"),
        types.InlineKeyboardButton("\ud83d\udcca Точность", callback_data="accuracy"),
        types.InlineKeyboardButton("\ud83d\udcc8 Рейтинг", callback_data="ranking")
    )
    return markup

# === Команды ===
@bot.message_handler(commands=['start'])
def start(message):
    if message.from_user.id != AUTHORIZED_USER_ID:
        return
    bot.send_message(message.chat.id, "Привет! Выбери действие:", reply_markup=main_keyboard())

@bot.message_handler(commands=['export'])
def export_data(message):
    if message.from_user.id != AUTHORIZED_USER_ID:
        return
    df = pd.read_sql_query("SELECT * FROM predictions", conn)
    df.to_csv("predictions.csv", index=False)
    df.to_excel("predictions.xlsx", index=False)
    with open("predictions.csv", "rb") as f1, open("predictions.xlsx", "rb") as f2:
        bot.send_document(message.chat.id, f1, caption="\ud83d\udcc4 CSV-файл")
        bot.send_document(message.chat.id, f2, caption="\ud83d\udcc4 Excel-файл")

@bot.message_handler(commands=['ranking'])
def indicator_ranking(message):
    if message.from_user.id != AUTHORIZED_USER_ID:
        return
    cursor.execute("SELECT votes, signal, actual FROM predictions WHERE actual IS NOT NULL")
    rows = cursor.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "Нет данных для рейтинга.")
        return
    scores, counts = {}, {}
    for vote_str, signal, actual in rows:
        for ind in vote_str.split(","):
            counts[ind] = counts.get(ind, 0) + 1
            if signal == actual:
                scores[ind] = scores.get(ind, 0) + 1
    result = "\ud83c\udfc6 *Рейтинг индикаторов по точности:*\n"
    sorted_ind = sorted(scores.items(), key=lambda x: scores.get(x[0], 0)/counts.get(x[0], 1), reverse=True)
    for ind, correct in sorted_ind:
        total = counts.get(ind, 1)
        acc = round(correct / total * 100, 2)
        result += f"\ud83d\udd39 {ind}: {acc}% ({correct}/{total})\n"
    bot.send_message(message.chat.id, result, parse_mode="Markdown")

# === Обработка кнопок ===
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.from_user.id != AUTHORIZED_USER_ID:
        return
    if call.data == "tf_15":
        process_signal(call.message.chat.id, "15")
    elif call.data == "tf_30":
        process_signal(call.message.chat.id, "30")
    elif call.data == "tf_60":
        process_signal(call.message.chat.id, "60")
    elif call.data == "verify":
        verify_predictions(call.message.chat.id)
    elif call.data == "accuracy":
        show_accuracy(call.message.chat.id)
    elif call.data == "ranking":
        indicator_ranking(call.message)

# === Верификация прогноза ===
def verify_predictions(chat_id):
    now = datetime.utcnow()
    cursor.execute("SELECT id, timestamp, price FROM predictions WHERE actual IS NULL")
    rows = cursor.fetchall()
    updated = 0
    for id_, ts, old_price in rows:
        ts_time = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        if now - ts_time >= timedelta(minutes=15):
            new_close = float(get_candles()[-1][4])
            actual = "LONG" if new_close > old_price else "SHORT" if new_close < old_price else "NEUTRAL"
            cursor.execute("UPDATE predictions SET actual = ? WHERE id = ?", (actual, id_))
            updated += 1
    conn.commit()
    bot.send_message(chat_id, f"\ud83d\udd0d Обновлено прогнозов: {updated}")

# === Показать точность ===
def show_accuracy(chat_id):
    cursor.execute("SELECT signal, actual FROM predictions WHERE actual IS NOT NULL")
    rows = cursor.fetchall()
    if not rows:
        bot.send_message(chat_id, "\ud83d\udcca Ещё нет проверенных прогнозов.")
        return
    total = len(rows)
    correct = sum(1 for r in rows if r[0] == r[1])
    acc = round(correct / total * 100, 2)
    bot.send_message(chat_id, f"\u2705 Точность: {acc}% ({correct}/{total})")

# === Автообновление прогноза ===
def auto_predict():
    while True:
        try:
            process_signal(chat_id=AUTHORIZED_USER_ID, interval="15")
            time.sleep(900)
        except Exception as e:
            print(f"[AutoPredict Error] {e}")

threading.Thread(target=auto_predict).start()

# === Запуск бота ===
bot.polling(none_stop=True)
