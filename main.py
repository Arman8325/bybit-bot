import telebot
from telebot import types
import os
import pandas as pd
from io import BytesIO
from pybit.unified_trading import HTTP
from datetime import datetime, timedelta
import ta
import sqlite3
import threading
import time
from dotenv import load_dotenv

# === Загрузка окружения ===
load_dotenv()
AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID"))
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))
session = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

# === Инициализация БД ===
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
    timeframe TEXT,
    sl REAL,
    tp REAL
)
""")
conn.commit()

# === Состояния и дедупликация ===
last_period = {}
user_states = {}

# === Утилиты ===
def get_candles(interval="15", limit=100):
    return session.get_kline(category="linear", symbol="BTCUSDT", interval=interval, limit=limit)["result"]["list"]

# === Индикаторы ===
def analyze_indicators(df):
    df = df.astype({"close":"float", "high":"float", "low":"float", "volume":"float"})
    return {
        "RSI": ta.momentum.RSIIndicator(df["close"]).rsi().iloc[-1],
        "EMA21": ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1],
        "ADX": ta.trend.ADXIndicator(df["high"], df["low"], df["close"]).adx().iloc[-1],
        "CCI": ta.trend.CCIIndicator(df["high"], df["low"], df["close"]).cci().iloc[-1],
        "ATR14": ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=14).average_true_range().iloc[-1]
    }

# === Голосование ===
def make_prediction(ind, last):
    votes = []
    if ind["RSI"] > 60:
        votes.append("LONG")
    elif ind["RSI"] < 40:
        votes.append("SHORT")
    votes.append("LONG" if last > ind["EMA21"] else "SHORT")
    if ind["ADX"] > 25:
        votes.append("LONG")
    if ind["CCI"] > 100:
        votes.append("LONG")
    elif ind["CCI"] < -100:
        votes.append("SHORT")
    lc, sc = votes.count("LONG"), votes.count("SHORT")
    if lc > sc:
        return "LONG", votes
    if sc > lc:
        return "SHORT", votes
    return "NEUTRAL", votes

# === Условие входа ===
def is_entry_opportunity(ind, last, votes):
    return votes.count("LONG") == len(votes)

# === Обработка сигнала ===
def process_signal(chat_id, interval, manual=False):
    data = get_candles(interval=interval)
    df = pd.DataFrame(data, columns=["timestamp","open","high","low","close","volume","turnover"])

    # Дедупликация автосигнала
    period = int(interval) * 60
    idx = int(df["timestamp"].iloc[-1]) // period
    if not manual and last_period.get(interval) == idx:
        return
    if not manual:
        last_period[interval] = idx

    ind_cur = analyze_indicators(df)
    last = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2])
    signal, votes = make_prediction(ind_cur, last)

    # Мульти-ТФ проверка EMA21
    higher_map = {"15": "60", "30": "240", "60": "240"}
    higher_tf = higher_map.get(interval)
    if higher_tf and not manual:
        hdata = get_candles(interval=higher_tf)
        hdf = pd.DataFrame(hdata, columns=["timestamp","open","high","low","close","volume","turnover"])
        ind_high = analyze_indicators(hdf)
        if signal == "LONG" and last < ind_high["EMA21"]:
            return
        if signal == "SHORT" and last > ind_high["EMA21"]:
            return

    # ATR-фильтр
    if not manual:
        candle_range = df["high"].iloc[-1] - df["low"].iloc[-1]
        if candle_range < ind_cur["ATR14"]:
            return

    # Рассчет SL/TP
    atr = ind_cur["ATR14"]
    if signal == "LONG":
        sl = last - atr
        tp = last + 2 * atr
    elif signal == "SHORT":
        sl = last + atr
        tp = last - 2 * atr
    else:
        sl = tp = None

    # Сохранение
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO predictions (timestamp, price, signal, actual, votes, timeframe, sl, tp) VALUES (?,?,?,?,?,?,?,?)",
        (ts, last, signal, None, ",".join(votes), interval, sl, tp)
    )
    conn.commit()

    # Формирование и отправка сообщения
    text = f"⏱ Таймфрейм: {interval}м\n"
    text += f"📈 Закрытие: {last}  (SL={round(sl,2) if sl else '-'}, TP={round(tp,2) if tp else '-'})\n"
    text += f"📉 Предыдущее: {prev}\n"
    text += f"🔹 RSI: {round(ind_cur['RSI'],2)}, EMA21: {round(ind_cur['EMA21'],2)}\n"
    if higher_tf:
        text += f"🔹 Старший ТФ {higher_tf}м EMA21: {round(ind_high['EMA21'],2)}\n"
    text += f"🔹 ATR14: {round(atr,2)}\n"
    text += f"\n📌 Прогноз: {('🔺 LONG' if signal=='LONG' else '🔻 SHORT' if signal=='SHORT' else '⚪️ NEUTRAL')}\n"
    text += f"🧠 Голоса: {votes}\n"
    bot.send_message(chat_id, text)

    # Точка входа за минуту до новой свечи
    now = datetime.utcnow()
    if now.minute % int(interval) == int(interval)-1 and is_entry_opportunity(ind_cur, last, votes):
        entry = f"🔔 *Точка входа {signal}! SL={round(sl,2) if sl else '-'} TP={round(tp,2) if tp else '-'}*"
        bot.send_message(chat_id, entry, parse_mode="Markdown")

# === Калькулятор прибыли с плечом ===
@bot.message_handler(regexp=r"^Калькулятор$")
def start_calculator(m):
    if m.from_user.id != AUTHORIZED_USER_ID:
        return
    user_states[m.chat.id] = 'await_calc'
    bot.send_message(
        m.chat.id,
        "Введите баланс, цену входа, цену цели и плечо через пробел, например:\n`100 20000 20100 10`",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: user_states.get(m.chat.id)=='await_calc')
def calculator(m):
    try:
        parts = m.text.split()
        if len(parts) != 4:
            raise ValueError
        bal, price_in, price_tp, lev = parts
        bal = float(bal)
        price_in = float(price_in)
        price_tp = float(price_tp)
        lev = float(lev)
        profit_pct = (price_tp - price_in) / price_in * 100
        profit_usd = bal * lev * profit_pct / 100
        bot.send_message(
            m.chat.id,
            f"При плече {int(lev)}×: Прибыль составит {round(profit_usd,2)} USD (~{round(profit_pct,2)}%)"
        )
    except:
        bot.send_message(m.chat.id, "Неверный формат. Введите четыре числа через пробел: баланс, цена входа, цена цели, плечо.")
        return
    user_states.pop(m.chat.id, None)

# === Хендлеры основных команд ===
def make_reply_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("15м", "30м", "1ч")
    kb.row("Проверка", "Точность")
    kb.row("Export CSV", "Export Excel")
    kb.row("Калькулятор")
    return kb

@bot.message_handler(commands=['start'])
def start(m):
    if m.from_user.id != AUTHORIZED_USER_ID:
        return bot.send_message(m.chat.id, "⛔ У вас нет доступа.")
    bot.send_message(m.chat.id, "✅ Бот запущен!", reply_markup=make_reply_keyboard())

@bot.message_handler(func=lambda m: m.chat.id==AUTHORIZED_USER_ID)
def handler(m):
    # Сбросим состояние калькулятора, если оно было
    user_states.pop(m.chat.id, None)
    cmd = m.text.strip()
    # сброс состояния калькулятора при нажатии любых кнопок
    user_states.pop(m.chat.id, None)
    cmd = m.text.strip()
    if cmd == "15м":
        process_signal(m.chat.id, "15", manual=True)
    elif cmd == "30м":
        process_signal(m.chat.id, "30", manual=True)
    elif cmd == "1ч":
        process_signal(m.chat.id, "60", manual=True)
    elif cmd == "Проверка":
        verify(m.chat.id)
    elif cmd == "Точность":
        accuracy(m.chat.id)
    elif cmd == "Export CSV":
        export_csv(m)
    elif cmd == "Export Excel":
        export_excel(m)
    elif cmd == "Калькулятор":
        start_calculator(m)
    else:
        bot.send_message(m.chat.id, "ℹ️ Используйте клавиатуру.", reply_markup=make_reply_keyboard())

# === Проверка и точность ===
def verify(chat_id):
    now = datetime.utcnow()
    cursor.execute("SELECT id, timestamp, price FROM predictions WHERE actual IS NULL")
    updated = 0
    for _id, ts, price in cursor.fetchall():
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        if now - dt >= timedelta(minutes=15):
            nc = float(get_candles(interval="15")[-1][4])
            actual = "LONG" if nc>price else "SHORT" if nc<price else "NEUTRAL"
            cursor.execute("UPDATE predictions SET actual=? WHERE id=?", (actual, _id))
            updated += 1
    conn.commit()
    bot.send_message(chat_id, f"🔍 Обновлено: {updated}")

def accuracy(chat_id):
    cursor.execute("SELECT signal, actual FROM predictions WHERE actual IS NOT NULL")
    rows = cursor.fetchall()
    if not rows:
        return bot.send_message(chat_id, "📊 Нет проверенных.")
    total = len(rows)
    correct = sum(1 for s,a in rows if s==a)
    bot.send_message(chat_id, f"✅ Точность: {round(correct/total*100,2)}% ({correct}/{total})")

# === Экспорт ===
def export_csv(m):
    df = pd.read_sql_query("SELECT * FROM predictions", conn)
    if df.empty:
        return bot.send_message(m.chat.id, "📁 Нет данных.")
    buf = BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    bot.send_document(m.chat.id, ("signals.csv", buf))

def export_excel(m):
    df = pd.read_sql_query("SELECT * FROM predictions", conn)
    if df.empty:
        return bot.send_message(m.chat.id, "📁 Нет данных.")
    buf = BytesIO()
    df.to_excel(buf, index=False, sheet_name="Signals")
    buf.seek(0)
    bot.send_document(m.chat.id, ("signals.xlsx", buf))

# === Авто-прогноз 15м ===
def auto_pred():
    while True:
        try:
            process_signal(AUTHORIZED_USER_ID, "15")
            time.sleep(900)
        except:
            time.sleep(900)
threading.Thread(target=auto_pred, daemon=True).start()

# === Ежедневный отчёт ===
last_summary_date = None

def daily_summary():
    global last_summary_date
    while True:
        now = datetime.utcnow()
        nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        time.sleep((nxt-now).total_seconds())
        ds = (nxt - timedelta(days=1)).strftime("%Y-%m-%d")
        if ds != last_summary_date:
            last_summary_date = ds
            rows = cursor.execute(
                "SELECT signal,actual FROM predictions WHERE timestamp LIKE ? AND actual IS NOT NULL",
                (ds+"%",)
            ).fetchall()
            tot = len(rows)
            corr = sum(1 for s,a in rows if s==a)
            txt = (f"📅 Отчёт за {ds}: Всего {tot}, Попаданий {corr}, Точность {round(corr/tot*100,2)}%" if tot else f"📅 Отчёт за {ds}: нет данных")
            bot.send_message(AUTHORIZED_USER_ID, txt)
threading.Thread(target=daily_summary, daemon=True).start()

# === Запуск бота ===
bot.polling(none_stop=True)
