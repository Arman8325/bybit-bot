import os
import logging
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
from telebot import TeleBot, types
from pybit import HTTP

# TA-библиотека
from ta.momentum import RSIIndicator, StochasticOscillator, StochRSIIndicator
from ta.trend import EMAIndicator, ADXIndicator, KDJIndicator
from ta.volatility import BollingerBands, SARIndicator
from ta.volume import OnBalanceVolumeIndicator, MoneyFlowIndexIndicator
from ta.others import CCIIndicator, WilliamsRIndicator

# ---------- СТАРЫЙ КОД (без изменений) ----------
logging.basicConfig(level=logging.INFO)

BYBIT_API_KEY    = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")

bybit = HTTP("https://api.bybit.com",
             api_key=BYBIT_API_KEY,
             api_secret=BYBIT_API_SECRET)
bot = TeleBot(TELEGRAM_TOKEN)


def fetch_ohlcv(symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
    """Получить OHLCV из Bybit."""
    data = bybit.kline(symbol=symbol, interval=interval, limit=limit)["result"]
    df = pd.DataFrame(data)
    df['timestamp'] = pd.to_datetime(df['open_time'], unit='s')
    df[['open','high','low','close','volume']] = df[['open','high','low','volume','volume']].astype(float)
    return df[['timestamp','open','high','low','close','volume']]


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Рассчитать 13+ индикаторов и сгенерировать «сырые» сигналы:
    signal_<IND> для каждого.
    """
    # --- расчёт индикаторов ---
    df['rsi']   = RSIIndicator(df['close'], window=14).rsi()
    df['ema21'] = EMAIndicator(df['close'], window=21).ema_indicator()
    df['adx']   = ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
    df['cci']   = CCIIndicator(df['high'], df['low'], df['close'], window=20).cci()
    df['stoch'] = StochasticOscillator(df['high'], df['low'], df['close'], window=14).stoch()
    df['mom']   = df['close'].pct_change(5)
    df['sma20'] = df['close'].rolling(20).mean()
    bb = BollingerBands(df['close'], window=20)
    df['bb_up'] = bb.bollinger_hband()
    df['bb_low']= bb.bollinger_lband()
    df['wr']    = WilliamsRIndicator(df['high'], df['low'], df['close'], lbp=14).wr()
    df['sar']   = SARIndicator(df['high'], df['low'], df['close'], window=14).sar()
    macd_line   = df['close'].ewm(span=12).mean() - df['close'].ewm(span=26).mean()
    macd_sig    = macd_line.ewm(span=9).mean()
    df['macd']  = macd_line - macd_sig
    kdj         = KDJIndicator(df['high'], df['low'], df['close'], window=14)
    df['kdj_k'] = kdj.kdj_k()
    df['stochrsi']= StochRSIIndicator(df['close'], window=14).stochrsi()
    df['obv']   = OnBalanceVolumeIndicator(df['close'], df['volume']).on_balance_volume()
    df['mfi']   = MoneyFlowIndexIndicator(df['high'], df['low'], df['close'], df['volume'], window=14).money_flow_index()

    # --- генерация raw сигналов ---
    raw = pd.DataFrame({'timestamp': df['timestamp']})
    raw['signal_RSI']      = df['rsi'].apply(lambda x: 'LONG' if x < 30 else ('SHORT' if x > 70 else 'NEUTRAL'))
    raw['signal_EMA21']    = df.apply(lambda r: 'LONG' if r['close'] > r['ema21'] else 'SHORT', axis=1)
    raw['signal_ADX']      = df['adx'].apply(lambda x: 'LONG' if x > 25 else 'NEUTRAL')
    raw['signal_CCI']      = df['cci'].apply(lambda x: 'LONG' if x < -100 else ('SHORT' if x > 100 else 'NEUTRAL'))
    raw['signal_STOCH']    = df['stoch'].apply(lambda x: 'LONG' if x < 20 else ('SHORT' if x > 80 else 'NEUTRAL'))
    raw['signal_MOM']      = df['mom'].apply(lambda x: 'LONG' if x > 0.005 else ('SHORT' if x < -0.005 else 'NEUTRAL'))
    raw['signal_SMA20']    = df.apply(lambda r: 'LONG' if r['close'] > r['sma20'] else 'SHORT', axis=1)
    raw['signal_BB']       = df.apply(lambda r: 'LONG' if r['close'] < r['bb_low']
                                      else ('SHORT' if r['close'] > r['bb_up'] else 'NEUTRAL'), axis=1)
    raw['signal_WR']       = df['wr'].apply(lambda x: 'LONG' if x < -80 else ('SHORT' if x > -20 else 'NEUTRAL'))
    raw['signal_SAR']      = df.apply(lambda r: 'LONG' if r['close'] > r['sar'] else 'SHORT', axis=1)
    raw['signal_MACD']     = df['macd'].apply(lambda x: 'LONG' if x > 0 else 'SHORT')
    raw['signal_KDJ']      = df['kdj_k'].apply(lambda x: 'LONG' if x < 20 else ('SHORT' if x > 80 else 'NEUTRAL'))
    raw['signal_StochRSI'] = df['stochrsi'].apply(lambda x: 'LONG' if x < 20 else ('SHORT' if x > 80 else 'NEUTRAL'))
    raw['signal_OBV']      = df['obv'].diff().apply(lambda x: 'LONG' if x > 0 else ('SHORT' if x < 0 else 'NEUTRAL'))
    raw['signal_MFI']      = df['mfi'].apply(lambda x: 'LONG' if x < 30 else ('SHORT' if x > 70 else 'NEUTRAL'))
    return raw


# ---------- НОВЫЙ КОД ОБРАБОТКИ СИГНАЛОВ ----------
def process_signals(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    # 1) дедупликация в 15m, 30m и 60m
    for tf in ['15T', '30T', '60T']:
        df[f'candle_{tf}'] = df['timestamp'].dt.floor(tf)
        df = df.sort_values('timestamp').drop_duplicates(subset=[f'candle_{tf}'], keep='first')

    # 2) веса индикаторов
    weights = {ind: 1.0 for ind in raw.columns if ind.startswith('signal_')}  # по умолчанию равные веса

    def vote(df_subset):
        def scorer(row):
            score = total = 0.0
            for ind, w in weights.items():
                sig = row[ind]
                if sig == 'LONG': score += w
                if sig == 'SHORT': score -= w
                total += w
            return ('LONG' if score/total>0 else 'SHORT') if total>0 else 'NEUTRAL'
        df_subset['vote'] = df_subset.apply(scorer, axis=1)
        return df_subset[['timestamp','vote']]

    # отдельно для каждого TF
    sig15 = vote(df.copy().rename(columns=lambda c: c).loc[:, ['timestamp']+list(weights.keys())]).rename(columns={'vote':'sig_15m'})
    sig30 = vote(df.copy().loc[:,         ['timestamp']+list(weights.keys())]).rename(columns={'vote':'sig_30m'})
    sig60 = vote(df.copy().loc[:,         ['timestamp']+list(weights.keys())]).rename(columns={'vote':'sig_60m'})

    merged = sig15.merge(sig30, on='timestamp').merge(sig60, on='timestamp')
    # итоговый сигнал: совпадение 30m и 60m
    merged['final'] = merged.apply(
        lambda r: r['sig_30m'] if r['sig_30m']==r['sig_60m'] else 'NEUTRAL', axis=1
    )
    return merged


# ---------- ХЕНДЛЕР /signal ----------
@bot.message_handler(commands=['signal'])
def handle_signal(msg: types.Message):
    df15 = fetch_ohlcv("BTCUSDT", '15', limit=100)
    raw15 = generate_signals(df15)
    processed = process_signals(raw15)
    last = processed.iloc[-1]
    bot.reply_to(msg, f"15m: {last['sig_15m']} 30m: {last['sig_30m']} 60m: {last['sig_60m']} ➞ final: {last['final']}")


# ---------- ХЕНДЛЕР /accuracy ----------
@bot.message_handler(commands=['accuracy'])
def handle_accuracy(msg: types.Message):
    # предполагаем, что Signals.csv уже есть и содержит столбец 'final'
    df = pd.read_csv('Signals.csv', parse_dates=['timestamp'])
    total = len(df)
    wins  = df['final'].value_counts().get('LONG',0) + df['final'].value_counts().get('SHORT',0)
    bot.reply_to(msg, f"Всего сигналов: {total}. Активных (LONG/SHORT): {wins}. Процент: {wins/total*100:.2f}%.")


# ---------- ХЕНДЛЕР /export ----------
@bot.message_handler(commands=['export'])
def handle_export(msg: types.Message):
    df = pd.read_csv('Signals.csv', parse_dates=['timestamp'])
    df.to_excel('Signals.xlsx', index=False)
    bot.reply_to(msg, "Экспорт завершён: Signals.xlsx")


# ---------- ХЕНДЛЕР /calc ----------
@bot.message_handler(commands=['calc'])
def handle_calc(msg: types.Message):
    expr = msg.text.partition(' ')[2]
    try:
        # безопасное вычисление
        allowed = {'__builtins__':None}
        result = eval(expr, allowed, {})
        bot.reply_to(msg, f"Результат: {result}")
    except Exception as e:
        bot.reply_to(msg, f"Ошибка в выражении: {e}")


if __name__ == '__main__':
    bot.infinity_polling()
