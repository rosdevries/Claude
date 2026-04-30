import json
import logging
from datetime import date, timedelta
from pathlib import Path

import yfinance as yf

log = logging.getLogger(__name__)
_PORTFOLIO_FILE = Path(__file__).parent.parent / "portfolio.json"


def _latest_close(symbol: str) -> float:
    end = date.today()
    start = end - timedelta(days=7)
    hist = yf.Ticker(symbol).history(
        start=start.strftime("%Y-%m-%d"),
        end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
    )
    if hist.empty:
        raise ValueError(f"No price data for {symbol}")
    return float(hist["Close"].iloc[-1])


def fetch_holdings() -> dict:
    trades = json.loads(_PORTFOLIO_FILE.read_text())

    holdings = []
    for t in trades:
        symbol = t["symbol"]
        shares = float(t["shares"])
        buy_price = float(t["buy_price"])
        current_price = _latest_close(symbol)

        invested = shares * buy_price
        current_value = shares * current_price
        pnl = current_value - invested
        pnl_pct = pnl / invested if invested else 0.0

        holdings.append({
            "trade": {"symbol": symbol, "shares": shares, "buy_price": buy_price},
            "current_price": current_price,
            "current_value": current_value,
            "invested": invested,
            "unrealized_pnl": pnl,
            "unrealized_pnl_pct": pnl_pct,
        })

    total_invested = sum(h["invested"] for h in holdings)
    total_value = sum(h["current_value"] for h in holdings)
    total_pnl = total_value - total_invested
    total_pnl_pct = total_pnl / total_invested if total_invested else 0.0

    return {
        "summary": {
            "total_invested": total_invested,
            "total_current_value": total_value,
            "total_unrealized_pnl": total_pnl,
            "total_unrealized_pnl_pct": total_pnl_pct,
            "total_dividends": 0.0,
        },
        "holdings": holdings,
    }
