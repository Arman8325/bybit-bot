import os
import logging
import pandas as pd
from telebot import TeleBot, types
from pybit.unified_trading import HTTP

# Индикаторы, которые точно есть в вашей версии ta
from ta.momentum import RSIIndicator, StochasticOscillator, StochRSIIndicator
from ta.trend import EMAIndicator, ADXIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator, MoneyFlowIndexIndicator
from ta.others import CCIIndicator, WilliamsRIndicator

# ---------- Настройка ----------

logging.basicConfig(level=logging.INFO)
BYBIT_API_KEY    = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")

bybit = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)
bot   = TeleBot(TELEGRAM_TOKEN)

# ---------- Утилиты ----------

def fetch_ohlcv(symbol: str, interval: str, limit: int = 100) -> pd.DataFrame:
    resp = bybit.get_kline(
        category="linear",
        symbol=symbol,
        interval=interval,
        limit=limit
    )
    data = resp["result"]["list"]
    df = pd.DataFrame(data)
    df['timestamp'] = pd.to_datetime(df['start'], unit='ms')
    df[['open','high','low','close','volume']] = \
        df[['open','high','low','volume','volume']].astype(float)
    return df[['timestamp','open','high','low','close','volume']]

def generate_raw(df: pd.DataFrame) -> pd.DataFrame:
    # Рассчитываем индикаторы
    df['rsi']    = RSIIndicator(df['close'], window=14).rsi()
    df['ema21']  = EMAIndicator(df['close'], window=21).ema_indicator()
    df['adx']    = ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
    df['cci']    = CCIIndicator(df['high'], df['low'], df['close'], window=20).cci()
    df['stoch']  = StochasticOscillator(df['high'], df['low'], df['close'], window=14).stoch()
    df['stochrsi']= StochRSIIndicator(df['close'], window=14).stochrsi()
    df['bb_up']  = BollingerBands(df['close'], window=20).bollinger_hband()
    df['bb_low'] = BollingerBands(df['close'], window=20).bollinger_lband()
    df['atr']    = AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range()
    df['obv']    = OnBalanceVolumeIndicator(df['close'], df['volume']).on_balance_volume()
    df['mfi']    = MoneyFlowIndexIndicator(df['high'], df['low'], df['close'], df['volume'], window=14).money_flow_index()
    df['wr']     = WilliamsRIndicator(df['high'], df['low'], df['close'], lbp=14).wr()

    # Формируем DataFrame raw-сигналов: 1, 0, -1
    raw = pd.DataFrame({'timestamp': df['timestamp']})
    raw['RSI']    = df['rsi'].apply(lambda x: 1 if x<30 else (-1 if x>70 else 0))
    raw['EMA']    = df.apply(lambda r: 1 if r['close']>r['ema21'] else -1, axis=1)
    raw['ADX']    = df['adx'].apply(lambda x: 1 if x>25 else 0)
    raw['CCI']    = df['cci'].apply(lambda x: 1 if x<-100 else (-1 if x>100 else 0))
    raw['STOCH']  = df['stoch'].apply(lambda x: 1 if x<20 else (-1 if x>80 else 0))
    raw['StochRSI']= df['stochrsi'].apply(lambda x: 1 if x<20 else (-1 if x>80 else 0))
    raw['BB']     = df.apply(lambda r: 1 if r['close']<r['bb_low'] else (-1 if r['close']>r['bb_up'] else 0), axis=1)
    raw['ATR']    = df['atr'].apply(lambda x: 1 if x>df['atr'].mean() else 0)
    raw['OBV']    = df['obv'].diff().apply(lambda x: 1 if x>0 else (-1 if x<0 else 0))
    raw['MFI']    = df['mfi'].apply(lambda x: 1 if x<30 else (-1 if x>70 else 0))
    raw['WR']     = df['wr'].apply(lambda x: 1 if x<-80 else (-1 if x>-20 else 0))

    return raw.set_index('timestamp')

def weighted_signal(raw: pd.DataFrame, weights: dict) -> pd.Series:
    def vote(row):
        score = total = 0.0
        for ind, w in weights.items():
            score += row[ind] * w
            total += w
        if total == 0:
            return 0
        return 1 if score/total>0 else (-1 if score/total<0 else 0)
    return raw.apply(vote, axis=1)

# ---------- Меню и хендлеры ----------

@bot.message_handler(commands=['start'])
def cmd_start(msg: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📈 Signal 4h/1d", "📊 Accuracy", "📤 Export", "🧮 Calc")
    bot.send_message(msg.chat.id, "Выберите:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "📈 Signal 4h/1d")
def btn_signal(msg: types.Message):
    sym = "BTCUSDT"
    raw4 = generate_raw(fetch_ohlcv(sym, '240'))
    rawD = generate_raw(fetch_ohlcv(sym, 'D'))
    weights = {
        'RSI':1, 'EMA':1, 'ADX':0.5, 'CCI':0.5, 'STOCH':0.5,
        'StochRSI':0.5, 'BB':0.4, 'ATR':0.2, 'OBV':0.3,
        'MFI':0.3, 'WR':0.2
    }
    s4 = weighted_signal(raw4, weights).iloc[-1]
    sD = weighted_signal(rawD, weights).iloc[-1]
    map_ = {1:"LONG", 0:"NEUTRAL", -1:"SHORT"}
    final = map_[s4] if (s4==sD and s4!=0) else "NEUTRAL"

    bot.reply_to(msg,
        f"4h: {map_[s4]}\n1d: {map_[sD]}\nFinal: {final}"
    )

    # Сохраняем в CSV
    df_out = pd.DataFrame([{
        'timestamp': raw4.index[-1],
        'sig_4h': map_[s4],
        'sig_1d': map_[sD],
        'final': final
    }])
    df_out.to_csv('Signals.csv', mode='a',
                  header=not os.path.exists('Signals.csv'),
                  index=False)

@bot.message_handler(func=lambda m: m.text == "📊 Accuracy")
def btn_accuracy(msg: types.Message):
    if not os.path.exists('Signals.csv'):
        return bot.reply_to(msg, "Нет Signals.csv.")
    df = pd.read_csv('Signals.csv', parse_dates=['timestamp'])
    total = len(df); wins = df['final'].isin(['LONG','SHORT']).sum()
    pct = wins/total*100 if total else 0
    bot.reply_to(msg, f"Всего: {total}\nАктивных: {wins}\nТочность: {pct:.2f}%")

@bot.message_handler(func=lambda m: m.text == "📤 Export")
def btn_export(msg: types.Message):
    if not os.path.exists('Signals.csv'):
        return bot.reply_to(msg, "Нет Signals.csv.")
    df = pd.read_csv('Signals.csv', parse_dates=['timestamp'])
    df.to_excel('Signals.xlsx', index=False)
    bot.reply_to(msg, "Signals.xlsx готов.")

@bot.message_handler(func=lambda m: m.text.startswith("🧮") or m.text.startswith("/calc"))
def btn_calc(msg: types.Message):
    expr = msg.text.replace("🧮","").replace("/calc","").strip()
    if not expr:
        return bot.reply_to(msg, "Введите выражение.")
    try:
        res = eval(expr, {"__builtins__":None}, {})
        bot.reply_to(msg, f"Результат: {res}")
    except Exception as e:
        bot.reply_to(msg, f"Ошибка: {e}")

if __name__ == '__main__':
    bot.infinity_polling()
