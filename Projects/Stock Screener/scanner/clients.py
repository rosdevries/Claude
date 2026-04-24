import os

from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.trading.client import TradingClient

load_dotenv()

_key    = os.getenv("ALPACA_API_KEY")
_secret = os.getenv("ALPACA_SECRET_KEY")

trading_client = (
    TradingClient(_key, _secret, paper=True)
    if _key and _secret else None
)
data_client = (
    StockHistoricalDataClient(_key, _secret)
    if _key and _secret else None
)
