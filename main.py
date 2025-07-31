import os
import logging
from datetime import datetime
import pandas as pd
from telebot import TeleBot, types
from pybit.unified_trading import HTTP

# индикаторы
from ta.momentum import RSIIndicator, StochasticOscillator, StochRSIIndicator
from ta.trend import EMAIndicator, ADXIndicator, KDJIndicator
from ta.volatility import BollingerBands, SARIndicator
from ta.volume import OnBalanceVolumeIndicator, MoneyFlowIndexIndicator
from ta.others import CCIIndicator, WilliamsRIndicator

# ---------- Настройка ----------
logging.basicConfig(level=logging.INFO)
BYBIT_API_KEY    = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")

# инициализируем V5-клиент
bybit = HTTP(
    testnet=False,
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET
)
bot = TeleBot(TELEGRAM_TOKEN)

# ---------- Утилиты ----------
def fetch_ohlcv(symbol: str, interval: str, limit: int = 100) -> pd.DataFrame:
    """
    В V5 метод называется get_kline.
    category по умолчанию 'linear' (USDT-контракты).
    """
    resp = bybit.get_kline(
        category="linear",
        symbol=symbol,
        interval=interval,
        limit=limit
    )
    data = resp["result"]["list"]  # список свечей
    df = pd.DataFrame(data)
    # в V5 ключ называется 'start' в миллисекундах
    df['timestamp'] = pd.to_datetime(df['start'], unit='ms')
    df[['open','high','low','close','volume']] = \
        df[['open','high','low','volume','volume']].astype(float)
    return df[['timestamp','open','high','low','close','volume']]

def generate_raw(df: pd.DataFrame) -> pd.DataFrame:
    df['rsi']   = RSIIndicator(df['close'], window=14).rsi()
    df['ema21'] = EMAIndicator(df['close'], window=21).ema_indicator()
    df['adx']   = ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
    df['cci']   = CCIIndicator(df['high'], df['low'], df['close'], window=20).cci()
    df['stoch'] = StochasticOscillator(df['high'], df['low'], df['close'], window=14).stoch()
    df['obv']   = OnBalanceVolumeIndicator(df['close'], df['volume']).on_balance_volume()
    df['mfi']   = MoneyFlowIndexIndicator(df['high'], df['low'], df['close'], df['volume'], window=14).money_flow_index()

    raw = pd.DataFrame({'timestamp': df['timestamp']})
    raw['RSI']   = df['rsi'].apply(lambda x: 1 if x < 30 else (-1 if x > 70 else 0))
    raw['EMA']   = df.apply(lambda r: 1 if r['close'] > r['ema21'] else -1, axis=1)
    raw['ADX']   = df['adx'].apply(lambda x: 1 if x > 25 else 0)
    raw['CCI']   = df['cci'].apply(lambda x: 1 if x < -100 else (-1 if x > 100 else 0))
    raw['STOCH'] = df['stoch'].apply(lambda x: 1 if x < 20 else (-1 if x > 80 else 0))
    raw['OBV']   = df['obv'].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    raw['MFI']   = df['mfi'].apply(lambda x: 1 if x < 30 else (-1 if x > 70 else 0))
    return raw.set_index('timestamp')

def weighted_signal(raw: pd.DataFrame, weights: dict) -> pd.Series:
    def vote(row):
        s = total = 0.0
        for ind, w in weights.items():
            s += row[ind] * w
            total += w
        if total == 0: return 0
        return 1 if s/total > 0 else (-1 if s/total < 0 else 0)
    return raw.apply(vote, axis=1)

# ---------- Меню и хендлеры ----------
@bot.message_handler(commands=['start'])
def cmd_start(msg: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📈 Signal 4h/1d", "📊 Accuracy", "📤 Export", "🧮 Calc")
    bot.send_message(msg.chat.id, "Выберите действие:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "📈 Signal 4h/1d")
def btn_signal(msg: types.Message):
    symbol = "BTCUSDT"
    raw4 = generate_raw(fetch_ohlcv(symbol, '240'))
    rawD = generate_raw(fetch_ohlcv(symbol, 'D'))
    weights = {'RSI':1,'EMA':1,'ADX':0.5,'CCI':0.5,'STOCH':0.5,'OBV':0.3,'MFI':0.3}
    s4 = weighted_signal(raw4, weights).iloc[-1]
    sD = weighted_signal(rawD, weights).iloc[-1]
    mapping = {1:"LONG",0:"NEUTRAL",-1:"SHORT"}
    final = mapping[s4] if (s4 == sD and s4 != 0) else "NEUTRAL"

    bot.reply_to(
        msg,
        f"4h: {mapping[s4]}\n"
        f"1d: {mapping[sD]}\n"
        f"Final: {final}"
    )

    # Сохраняем в CSV историю сигналов
    df_out = pd.DataFrame([{
        'timestamp': raw4.index[-1],
        'sig_4h': mapping[s4],
        'sig_1d': mapping[sD],
        'final': final
    }])
    df_out.to_csv('Signals.csv', mode='a',
                  header=not os.path.exists('Signals.csv'),
                  index=False)

@bot.message_handler(func=lambda m: m.text == "📊 Accuracy")
def btn_accuracy(msg: types.Message):
    if not os.path.exists('Signals.csv'):
        return bot.reply_to(msg, "Нет файла Signals.csv.")
    df = pd.read_csv('Signals.csv', parse_dates=['timestamp'])
    total = len(df)
    wins  = df['final'].isin(['LONG','SHORT']).sum()
    pct   = wins/total*100 if total else 0
    bot.reply_to(
        msg,
        f"Всего сигналов: {total}\n"
        f"Активных: {wins}\n"
        f"Точность: {pct:.2f}%"
    )

@bot.message_handler(func=lambda m: m.text == "📤 Export")
def btn_export(msg: types.Message):
    if not os.path.exists('Signals.csv'):
        return bot.reply_to(msg, "Signals.csv не найден.")
    df = pd.read_csv('Signals.csv', parse_dates=['timestamp'])
    df.to_excel('Signals.xlsx', index=False)
    bot.reply_to(msg, "Экспорт готов: Signals.xlsx")

@bot.message_handler(func=lambda m: m.text.startswith("🧮") or m.text.startswith("/calc"))
def btn_calc(msg: types.Message):
    expr = msg.text.replace("🧮","").replace("/calc","").strip()
    if not expr:
        return bot.reply_to(msg, "Введите выражение после 🧮 или /calc")
    try:
        res = eval(expr, {"__builtins__":None}, {})
        bot.reply_to(msg, f"Результат: {res}")
    except Exception as e:
        bot.reply_to(msg, f"Ошибка: {e}")

# ---------- Запуск ----------
if __name__ == '__main__':
    bot.infinity_polling()
