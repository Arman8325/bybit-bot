import os
import logging
from datetime import datetime
import pandas as pd
from telebot import TeleBot, types
from pybit import HTTP
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import EMAIndicator, ADXIndicator, KDJIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator, MFIIndicator
# … (импортируйте все остальные индикаторы, которые вы используете)

# ---------- СТАРЫЙ КОД БЕЗ ИЗМЕНЕНИЙ ----------
logging.basicConfig(level=logging.INFO)

BYBIT_API_KEY    = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")

bybit_client = HTTP("https://api.bybit.com",
                    api_key=BYBIT_API_KEY,
                    api_secret=BYBIT_API_SECRET)
bot = TeleBot(TELEGRAM_TOKEN)


def fetch_ohlcv(symbol: str, interval: str, limit: int = 100) -> pd.DataFrame:
    data = bybit_client.kline(symbol=symbol,
                              interval=interval,
                              limit=limit)["result"]
    df = pd.DataFrame(data)
    df['timestamp'] = pd.to_datetime(df['open_time'], unit='s')
    df[['open','high','low','close','volume']] = \
        df[['open','high','low','volume','volume']].astype(float)
    return df[['timestamp','open','high','low','close','volume']]


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    # Вычисляем все 13+ индикаторов
    df['rsi']    = RSIIndicator(df['close'], window=14).rsi()
    df['ema21']  = EMAIndicator(df['close'], window=21).ema_indicator()
    df['adx']    = ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
    df['cci']    = pd.Series(dtype=float)  # ваш CCI
    df['stoch']  = StochasticOscillator(df['high'], df['low'], df['close'], window=14).stoch()
    df['mom']    = pd.Series(dtype=float)  # ваш Momentum
    df['sma20']  = df['close'].rolling(20).mean()
    df['bb_up']  = BollingerBands(df['close'], window=20).bollinger_hband()
    df['bb_low'] = BollingerBands(df['close'], window=20).bollinger_lband()
    df['wr']     = pd.Series(dtype=float)  # Williams %R
    df['sar']    = pd.Series(dtype=float)  # ваш SAR
    df['macd']   = pd.Series(dtype=float)  # ваш MACD
    df['kdj']    = KDJIndicator(df['high'], df['low'], df['close']).kdj_k()
    df['stochrsi']= pd.Series(dtype=float) # ваш StochRSI
    df['obv']    = OnBalanceVolumeIndicator(df['close'], df['volume']).on_balance_volume()
    # … и т.д.

    # Генерируем «сырые» сигналы для каждого индикатора
    raw = pd.DataFrame({'timestamp': df['timestamp']})
    raw['signal_RSI']   = df['rsi'].apply(lambda x: 'LONG' if x < 30 else ('SHORT' if x > 70 else 'NEUTRAL'))
    raw['signal_EMA21'] = df.apply(lambda r: 'LONG' if r['close'] > r['ema21'] else 'SHORT', axis=1)
    raw['signal_ADX']   = df['adx'].apply(lambda x: 'LONG' if x > 25 else 'NEUTRAL')
    # … добавьте генерацию signal_CCI, signal_STOCH и т.д. по вашей логике

    return raw  # DataFrame с колонками timestamp + signal_<IND>


# ---------- НОВЫЙ КОД ОБРАБОТКИ СИГНАЛОВ ----------
def process_signals(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    # 1) Дедупликация внутри 30-минутной свечи
    df['candle_30m'] = df['timestamp'].dt.floor('30T')
    df = df.sort_values('timestamp') \
           .drop_duplicates(subset=['candle_30m'], keep='first')

    # 2) Веса индикаторов (подберите после бэктеста)
    weights = {
        'RSI':   0.4,
        'EMA21': 0.6,
        'ADX':   0.3,
        # … веса для всех signal_<IND>
    }

    def weighted_vote(row):
        score = total = 0.0
        for ind, w in weights.items():
            sig = row.get(f'signal_{ind}', 'NEUTRAL')
            if sig == 'LONG':  score += w
            if sig == 'SHORT': score -= w
            total += w
        if total == 0: return 'NEUTRAL'
        ratio = score / total
        if ratio >  0.2: return 'LONG'
        if ratio < -0.2: return 'SHORT'
        return 'NEUTRAL'

    df['filtered_signal'] = df.apply(weighted_vote, axis=1)

    # 3) Мульти-ТФ: проверяем 60-минутную свечу
    df60 = raw.copy()
    df60['candle_60m'] = df60['timestamp'].dt.floor('60T')
    df60 = df60.sort_values('timestamp') \
               .drop_duplicates(subset=['candle_60m'], keep='first')
    df60 = df60[['candle_60m','signal_RSI']].rename(columns={
        'candle_60m':'candle_30m',
        'signal_RSI':'signal_60m'  # здесь можно взять любой «эталонный» индикатор или повторить взвешенное голосование
    })

    merged = df.merge(df60, on='candle_30m', how='left')
    merged['final_signal'] = merged.apply(
        lambda r: r['filtered_signal'] if r['filtered_signal'] == r['signal_60m'] else 'NEUTRAL',
        axis=1
    )

    return merged[['candle_30m','final_signal']]


@bot.message_handler(commands=['signal'])
def handle_signal(message: types.Message):
    """/signal: старый код остается, потом процессим."""
    symbol = "BTCUSDT"

    # — НИЧЕГО НЕ МЕНЯЛИ В ЭТОМ БЛОКЕ —
    df_30 = fetch_ohlcv(symbol, '30')
    raw    = generate_signals(df_30)

    # — ВСТАВИЛИ НОВУЮ ОБРАБОТКУ —
    processed = process_signals(raw)
    last = processed.iloc[-1]
    sig  = last['final_signal']

    bot.reply_to(message, f"Сигнал: {sig} (30m+60m фильтр)")
    

if __name__ == '__main__':
    bot.infinity_polling()
