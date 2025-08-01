import os
import logging
import pandas as pd
from telebot import TeleBot, types
from pybit.unified_trading import HTTP
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import EMAIndicator, ADXIndicator
from ta.volatility import BollingerBands
from ta.volume import OnBalanceVolumeIndicator, MoneyFlowIndexIndicator
from ta.others import CCIIndicator, WilliamsRIndicator

logging.basicConfig(level=logging.INFO)

BYBIT_API_KEY    = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")

bybit = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)
bot   = TeleBot(TELEGRAM_TOKEN)

def fetch_ohlcv(symbol: str, interval: str, limit: int = 100) -> pd.DataFrame:
    resp = bybit.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
    data = resp["result"]["list"]
    df = pd.DataFrame(data)
    df['timestamp'] = pd.to_datetime(df['start'], unit='ms')
    df[['open','high','low','close','volume']] = df[['open','high','low','volume','volume']].astype(float)
    return df[['timestamp','open','high','low','close','volume']]

def generate_raw(df: pd.DataFrame) -> pd.DataFrame:
    df['rsi']   = RSIIndicator(df['close'], window=14).rsi()
    df['ema21'] = EMAIndicator(df['close'], window=21).ema_indicator()
    df['adx']   = ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
    df['cci']   = CCIIndicator(df['high'], df['low'], df['close'], window=20).cci()
    df['stoch'] = StochasticOscillator(df['high'], df['low'], df['close'], window=14).stoch()
    df['obv']   = OnBalanceVolumeIndicator(df['close'], df['volume']).on_balance_volume()
    df['mfi']   = MoneyFlowIndexIndicator(df['high'], df['low'], df['close'], df['volume'], window=14).money_flow_index()
    df['wr']    = WilliamsRIndicator(df['high'], df['low'], df['close'], lbp=14).wr()

    raw = pd.DataFrame({'timestamp': df['timestamp']})
    raw['RSI']   = df['rsi'].apply(lambda x: 1 if x<30 else (-1 if x>70 else 0))
    raw['EMA']   = df.apply(lambda r: 1 if r['close']>r['ema21'] else -1, axis=1)
    raw['ADX']   = df['adx'].apply(lambda x: 1 if x>25 else 0)
    raw['CCI']   = df['cci'].apply(lambda x: 1 if x<-100 else (-1 if x>100 else 0))
    raw['STOCH'] = df['stoch'].apply(lambda x: 1 if x<20 else (-1 if x>80 else 0))
    raw['OBV']   = df['obv'].diff().apply(lambda x: 1 if x>0 else (-1 if x<0 else 0))
    raw['MFI']   = df['mfi'].apply(lambda x: 1 if x<30 else (-1 if x>70 else 0))
    raw['WR']    = df['wr'].apply(lambda x: 1 if x<-80 else (-1 if x>-20 else 0))

    return raw.set_index('timestamp')

def weighted_signal(raw: pd.DataFrame, weights: dict) -> pd.Series:
    def vote(row):
        score = total = 0
        for ind, w in weights.items():
            score += row[ind] * w
            total += w
        if total == 0: return 0
        return 1 if score/total>0 else (-1 if score/total<0 else 0)
    return raw.apply(vote, axis=1)

@bot.message_handler(commands=['start'])
def cmd_start(msg: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📈 Signal", "📊 Accuracy")
    bot.send_message(msg.chat.id, "Привет! Выберите действие:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "📈 Signal")
def btn_signal(msg: types.Message):
    sym = "BTCUSDT"
    raw = generate_raw(fetch_ohlcv(sym, '240'))
    weights = {'RSI':1,'EMA':1,'ADX':0.5,'CCI':0.5,'STOCH':0.5,'OBV':0.3,'MFI':0.3,'WR':0.2}
    s = weighted_signal(raw, weights).iloc[-1]
    mapping = {1:"LONG",0:"NEUTRAL",-1:"SHORT"}
    bot.reply_to(msg, f"Сигнал 4h: {mapping[s]}")

@bot.message_handler(func=lambda m: m.text == "📊 Accuracy")
def btn_accuracy(msg: types.Message):
    if not os.path.exists('Signals.csv'):
        return bot.reply_to(msg, "Нет Signals.csv.")
    df = pd.read_csv('Signals.csv', parse_dates=['timestamp'])
    total = len(df); wins = df['final'].isin(['LONG','SHORT']).sum()
    pct = wins/total*100 if total else 0
    bot.reply_to(msg, f"Всего: {total}\nАктивных: {wins}\nТочность: {pct:.2f}%")

if __name__ == '__main__':
    bot.infinity_polling()
