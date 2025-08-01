import os
import pandas as pd
from dotenv import load_dotenv
from telebot import TeleBot, types
from pybit.unified_trading import HTTP

# Загружаем .env
load_dotenv(dotenv_path="/mnt/data/NNV/.env")

# Переменные окружения
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN") or "7725284250:AAG7a-apzzqkoQCa1RGO0g10Y2lZB36LXYc"
BYBIT_API_KEY    = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")

print("DEBUG: TELEGRAM_TOKEN =", TELEGRAM_TOKEN)
print("DEBUG: BYBIT_API_KEY =", BYBIT_API_KEY)

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

# Инициализация
bybit = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)
bot   = TeleBot(TELEGRAM_TOKEN)

# ---------- Функция для OHLCV ----------
def fetch_ohlcv(symbol: str, interval: str, limit: int = 10) -> pd.DataFrame:
    resp = bybit.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
    data = resp["result"]["list"]
    df = pd.DataFrame(data)
    df['timestamp'] = pd.to_datetime(df['start'], unit='ms')
    df[['open','high','low','close','volume']] = df[['open','high','low','volume','volume']].astype(float)
    return df[['timestamp','open','high','low','close','volume']]

# ---------- Команды ----------
@bot.message_handler(commands=['start'])
def cmd_start(msg: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("✅ Test Button")
    kb.add("📊 Check Bybit", "📈 Last Candle")
    bot.send_message(msg.chat.id, "Привет! Выберите действие:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "✅ Test Button")
def test_button(msg: types.Message):
    bot.reply_to(msg, "Кнопка работает! 🎉")

@bot.message_handler(func=lambda m: m.text == "📊 Check Bybit")
def check_bybit(msg: types.Message):
    try:
        server_time = bybit.get_server_time()
        bot.reply_to(msg, f"✅ Bybit доступен.\nServer Time: {server_time['result']['time']}")
    except Exception as e:
        bot.reply_to(msg, f"❌ Ошибка подключения к Bybit: {e}")

@bot.message_handler(func=lambda m: m.text == "📈 Last Candle")
def check_ohlcv(msg: types.Message):
    try:
        df = fetch_ohlcv("BTCUSDT", "60")
        last = df.iloc[-1]
        bot.reply_to(
            msg,
            f"📈 Последняя свеча BTCUSDT (1ч):\n"
            f"Время: {last['timestamp']}\n"
            f"Цена закрытия: {last['close']}"
        )
    except Exception as e:
        bot.reply_to(msg, f"❌ Ошибка получения свечей: {e}")

# ---------- Запуск ----------
if __name__ == '__main__':
    print("✅ Бот запущен и ждёт сообщений...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
