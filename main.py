import os
import logging
import pandas as pd
from dotenv import load_dotenv  # <--- добавляем

from telebot import TeleBot, types
from pybit.unified_trading import HTTP
from ta.momentum import RSIIndicator, StochasticOscillator, StochRSIIndicator
from ta.trend import EMAIndicator, ADXIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator

# загрузка .env
load_dotenv()

logging.basicConfig(level=logging.INFO)

BYBIT_API_KEY    = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")

print("DEBUG: TELEGRAM_TOKEN =", TELEGRAM_TOKEN)
print("DEBUG: BYBIT_API_KEY =", BYBIT_API_KEY)

bot = TeleBot(TELEGRAM_TOKEN)
