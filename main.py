import os
import logging
from datetime import datetime
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

bybit_client = HTTP(
    "https://api.bybit.com",
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET
)
bot = TeleBot(TELEGRAM_TOKEN)


def fetch_ohlcv(symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
    """Получить OHLCV из Bybit."""
    data = bybit_client.kline(
        symbol=symbol,
        interval=interval,
        limit=limit
    )["result"]
    df = pd.DataFrame(data)
    df['timestamp'] = pd.to_datetime(df['open_time'], unit='s')
    df[['open','high','low','close','volume']] = \
        df[['open','high','low','volume','volume']].astype(float)
    return df[['timestamp','open','high','low','close','volume']]


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Рассчитать 13+ индикаторов и сгенерировать "сырые" сигналы для каждого:
      RSI, EMA21, ADX, CCI, Stochastic, Momentum (ROC), SMA20,
      Bollinger Bands, Williams %R, SAR, MACD (hist), KDJ, StochRSI, OBV, MFI
    """
    # Расчёт индикаторов
    df['rsi']      = RSIIndicator(df['close'], window=14).rsi()
    df['ema21']    = EMAIndicator(df['close'], window=21).ema_indicator()
    df['adx']      = ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
    df['cci']      = CCIIndicator(df['high'], df['low'], df['close'], window=20).cci()
    df['stoch']    = StochasticOscillator(df['high'], df['low'], df['close'], window=14).stoch()
    df['mom']      = df['close'].pct_change(periods=5)
    df['sma20']    = df['close'].rolling(window=20).mean()
    bb = BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_up']    = bb.bollinger_hband()
    df['bb_low']   = bb.bollinger_lband()
    df['wr']       = WilliamsRIndicator(df['high'], df['low'], df['close'], lbp=14).wr()
    df['sar']      = SARIndicator(df['high'], df['low'], df['close'], window=14).sar()
    macd = df['close'].ewm(span=12, adjust=False).mean() - df['close'].ewm(span=26, adjust=False).mean()
    signal = macd.ewm(span=9, adjust=False).mean()
    df['macd_hist'] = macd - signal
    kdj = KDJIndicator(df['high'], df['low'], df['close'], window=14)
    df['kdj_k']     = kdj.kdj_k()
    df['stochrsi']  = StochRSIIndicator(df['close'], window=14, smooth1=3, smooth2=3).stochrsi()
    df['obv']       = OnBalanceVolumeIndicator(df['close'], df['volume']).on_balance_volume()
    df['mfi']       = MoneyFlowIndexIndicator(df['high'], df['low'], df['close'], df['volume'], window=14).money_flow_index()

    # Генерация raw сигналов
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
    raw['signal_MACD']     = df['macd_hist'].apply(lambda x: 'LONG' if x > 0 else 'SHORT')
    raw['signal_KDJ']      = df['kdj_k'].apply(lambda x: 'LONG' if x < 20 else ('SHORT' if x > 80 else 'NEUTRAL'))
    raw['signal_StochRSI'] = df['stochrsi'].apply(lambda x: 'LONG' if x < 20 else ('SHORT' if x > 80 else 'NEUTRAL'))
    raw['signal_OBV']      = df['obv'].diff().apply(lambda x: 'LONG' if x > 0 else ('SHORT' if x < 0 else 'NEUTRAL'))
    raw['signal_MFI']      = df['mfi'].apply(lambda x: 'LONG' if x < 30 else ('SHORT' if x > 70 else 'NEUTRAL'))

    return raw


# ---------- НОВЫЙ КОД ОБРАБОТКИ ----------
def process_signals(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    # 1) Дедупликация внутри 30-мин свечи
    df['candle_30m'] = df['timestamp'].dt.floor('30T')
    df = df.sort_values('timestamp').drop_duplicates(subset=['candle_30m'], keep='first')

    # 2) Веса индикаторов
    weights = {
        'RSI':      0.4,
        'EMA21':    0.6,
        'ADX':      0.3,
        'CCI':      0.3,
        'STOCH':    0.5,
        'MOM':      0.2,
        'SMA20':    0.4,
        'BB':       0.4,
        'WR':       0.3,
        'SAR':      0.3,
        'MACD':     0.5,
        'KDJ':      0.3,
        'StochRSI': 0.3,
        'OBV':      0.2,
        'MFI':      0.2
    }

    def weighted_vote(row):
        score = total = 0.0
        for ind, w in weights.items():
            sig = row.get(f'signal_{ind}', 'NEUTRAL')
            if sig == 'LONG':
                score += w
            elif sig == 'SHORT':
                score -= w
            total += w
        if total == 0:
            return 'NEUTRAL'
        r = score / total
        if r >  0.2: return 'LONG'
        if r < -0.2: return 'SHORT'
        return 'NEUTRAL'

    df['filtered_signal'] = df.apply(weighted_vote, axis=1)

    # 3) Мульти-ТФ: сверка с 60-минутой
    df60 = raw.copy()
    df60['candle_60m'] = df60['timestamp'].dt.floor('60T')
    df60 = df60.sort_values('timestamp').drop_duplicates(subset=['candle_60m'], keep='first')
    df60['filtered_60'] = df60.apply(weighted_vote, axis=1)
    df60 = df60[['candle_60m','filtered_60']].rename(
        columns={'candle_60m':'candle_30m','filtered_60':'signal_60m'}
    )

    merged = df.merge(df60, on='candle_30m', how='left')
    merged['final_signal'] = merged.apply(
        lambda r: r['filtered_signal'] if r['filtered_signal'] == r['signal_60m'] else 'NEUTRAL',
        axis=1
    )
    return merged[['candle_30m','filtered_signal','signal_60m','final_signal']]


# ---------- ХЕНДЛЕР /signal ----------
@bot.message_handler(commands=['signal'])
def handle_signal(message: types.Message):
    symbol = "BTCUSDT"

    # Шаг 1: загрузка и генерация raw-сигналов
    df_30 = fetch_ohlcv(symbol, '30')
    raw   = generate_signals(df_30)

    # Шаг 2: фильтрация
    processed = process_signals(raw)

    # Шаг 3: экспорт в CSV и построение графиков
    # Переименуем для CSV
    out = processed.rename(columns={'candle_30m':'timestamp'})
    out.to_csv('Signals.csv', index=False)

    # Визуализация
    mapping = {'LONG':1, 'NEUTRAL':0, 'SHORT':-1}
    out['sig_30m'] = out['filtered_signal'].map(mapping)
    out['sig_60m'] = out['signal_60m'].map(mapping)

    plt.figure()
    plt.plot(out['timestamp'], out['sig_30m'])
    plt.title("30-минутные сигналы")
    plt.xlabel("Время")
    plt.ylabel("Сигнал")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig('signals_30m.png')
    plt.close()

    plt.figure()
    plt.plot(out['timestamp'], out['sig_60m'])
    plt.title("60-минутные сигналы")
    plt.xlabel("Время")
    plt.ylabel("Сигнал")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig('signals_60m.png')
    plt.close()

    # Шаг 4: ответ пользователю
    last = processed.iloc[-1]
    bot.reply_to(
        message,
        f"Сигнал: {last['final_signal']} (30m+60m фильтр)\n"
        f"CSV: Signals.csv, графики: signals_30m.png, signals_60m.png"
    )


if __name__ == '__main__':
    bot.infinity_polling()
