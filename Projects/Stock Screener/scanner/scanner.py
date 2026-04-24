import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

from alpaca.data.enums import DataFeed
from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.enums import AssetClass, AssetStatus
from alpaca.trading.requests import GetAssetsRequest

from scanner.clients import data_client, trading_client

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Market structure constants (not strategy-specific)
# ---------------------------------------------------------------------------
ET           = ZoneInfo("America/New_York")
MARKET_OPEN  = time(9, 30)
MARKET_CLOSE = time(16, 0)
TRADING_HOURS   = 6.5

SNAPSHOT_BATCH   = 500
BARS_BATCH       = 50
YFINANCE_WORKERS = 20

# ---------------------------------------------------------------------------
# Data fetching (all cached independently of strategy)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def fetch_universe() -> list:
    assets = trading_client.get_all_assets(
        GetAssetsRequest(asset_class=AssetClass.US_EQUITY, status=AssetStatus.ACTIVE)
    )
    return [
        a.symbol for a in assets
        if a.tradable and "/" not in a.symbol and len(a.symbol) <= 5
    ]


@st.cache_data(ttl=60)
def fetch_snapshots(symbols: tuple) -> dict:
    results = {}
    for i in range(0, len(symbols), SNAPSHOT_BATCH):
        batch = list(symbols[i : i + SNAPSHOT_BATCH])
        try:
            results.update(
                data_client.get_stock_snapshot(
                    StockSnapshotRequest(symbol_or_symbols=batch, feed=DataFeed.IEX)
                )
            )
        except Exception:
            pass
    return results


@st.cache_data(ttl=60)
def fetch_daily_bars(symbols: tuple) -> dict:
    now   = datetime.now(tz=ET)
    start = now - timedelta(days=80)
    results  = {}
    sym_list = list(symbols)
    for i in range(0, len(sym_list), BARS_BATCH):
        batch = sym_list[i : i + BARS_BATCH]
        try:
            resp   = data_client.get_stock_bars(
                StockBarsRequest(
                    symbol_or_symbols=batch,
                    timeframe=TimeFrame(1, TimeFrameUnit.Day),
                    start=start, end=now,
                    feed=DataFeed.IEX,
                )
            )
            df_all = resp.df
            for sym in batch:
                try:
                    results[sym] = df_all.xs(sym, level="symbol").copy()
                except KeyError:
                    pass
        except Exception:
            pass
    return results


@st.cache_data(ttl=60)
def fetch_intraday_bars(symbols: tuple) -> dict:
    now   = datetime.now(tz=ET)
    today = now.date()
    start = datetime(today.year, today.month, today.day, 9, 30, tzinfo=ET)
    results  = {}
    sym_list = list(symbols)
    for i in range(0, len(sym_list), BARS_BATCH):
        batch = sym_list[i : i + BARS_BATCH]
        try:
            resp   = data_client.get_stock_bars(
                StockBarsRequest(
                    symbol_or_symbols=batch,
                    timeframe=TimeFrame(5, TimeFrameUnit.Minute),
                    start=start, end=now,
                    feed=DataFeed.IEX,
                )
            )
            df_all = resp.df
            for sym in batch:
                try:
                    results[sym] = df_all.xs(sym, level="symbol").copy()
                except KeyError:
                    pass
        except Exception:
            pass
    return results


@st.cache_data(ttl=300)
def fetch_market_caps(symbols: tuple) -> dict:
    def _cap(sym):
        try:
            info = yf.Ticker(sym).fast_info
            return sym, float(info.get("market_cap") or info.get("marketCap") or 0.0)
        except Exception:
            return sym, 0.0

    caps = {}
    with ThreadPoolExecutor(max_workers=YFINANCE_WORKERS) as executor:
        for future in as_completed({executor.submit(_cap, s): s for s in symbols}):
            sym, cap = future.result()
            caps[sym] = cap
    return caps


@st.cache_data(ttl=60)
def get_chart_bars(symbol: str) -> pd.DataFrame:
    now   = datetime.now(tz=ET)
    today = now.date()
    start = datetime(today.year, today.month, today.day, 9, 30, tzinfo=ET)
    try:
        resp = data_client.get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame(5, TimeFrameUnit.Minute),
                start=start, end=now,
                feed=DataFeed.IEX,
            )
        )
        df = resp.df
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level="symbol")
        df = df.sort_index()
        if df.index.tz is not None:
            df.index = df.index.tz_convert(ET)
        df["typical"]   = (df["high"] + df["low"] + df["close"]) / 3
        cum_tv          = (df["typical"] * df["volume"]).cumsum()
        cum_v           = df["volume"].cumsum()
        df["vwap_line"] = cum_tv / cum_v.replace(0, np.nan)
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def get_company_name(symbol: str) -> str:
    try:
        return trading_client.get_asset(symbol).name or symbol
    except Exception:
        return symbol

# ---------------------------------------------------------------------------
# Strategy-agnostic filter functions
# ---------------------------------------------------------------------------

def filter_by_snapshot(snapshots: dict, strategy: dict) -> list:
    passing = []
    for sym, snap in snapshots.items():
        try:
            price      = snap.latest_trade.price
            prev_close = snap.previous_daily_bar.close
            open_price = snap.daily_bar.open
            volume     = snap.daily_bar.volume

            if not prev_close or prev_close == 0:
                continue

            # Price range
            if not (strategy["price_min"] <= price <= strategy["price_max"]):
                continue

            # Gap at open: (todayOpen - prevClose) / prevClose (ThinkScript-style)
            if strategy["gap_min"] is not None:
                if (open_price - prev_close) / prev_close < strategy["gap_min"]:
                    continue

            # Intraday % change: current price vs prev close (default strategy)
            if strategy["pct_change_min"] is not None:
                if (price - prev_close) / prev_close < strategy["pct_change_min"]:
                    continue

            # Raw daily volume floor
            if strategy["min_volume"] and volume < strategy["min_volume"]:
                continue

            pct = (price - prev_close) / prev_close
            passing.append({
                "symbol":     sym,
                "price":      price,
                "pct_change": pct,
                "volume":     volume,
                "prev_close": prev_close,
            })
        except (AttributeError, TypeError, ZeroDivisionError):
            continue
    return passing


def compute_relative_volume(daily_df: pd.DataFrame, snapshot_volume: int, strategy: dict):
    try:
        lookback = strategy["rvol_lookback"]
        df       = daily_df.sort_index()
        idx      = df.index
        dates    = idx.tz_convert(ET).date if idx.tz else pd.to_datetime(idx).dt.date.values
        today_et = datetime.now(tz=ET).date()
        hist     = df[dates != today_et]

        if len(hist) < lookback:
            return None

        baseline = hist["volume"].iloc[-lookback:]
        mean_v   = baseline.mean()

        # Use raw or projected volume depending on strategy
        if strategy["rvol_project"]:
            now_et  = datetime.now(tz=ET)
            open_dt = datetime(now_et.date().year, now_et.date().month, now_et.date().day, 9, 30, tzinfo=ET)
            elapsed = max((now_et - open_dt).total_seconds() / 3600, 0.0833)
            current_v = snapshot_volume * (TRADING_HOURS / elapsed)
        else:
            current_v = snapshot_volume

        if strategy["rvol_method"] == "zscore":
            std_v = baseline.std(ddof=1)
            if std_v == 0:
                return None
            return (current_v - mean_v) / std_v
        else:  # ratio
            if mean_v == 0:
                return None
            return current_v / mean_v

    except Exception:
        return None


def compute_vwap(intraday_df):
    try:
        if intraday_df is None or intraday_df.empty:
            return None
        df       = intraday_df.copy()
        df["tp"] = (df["high"] + df["low"] + df["close"]) / 3
        total_v  = df["volume"].sum()
        return float((df["tp"] * df["volume"]).sum() / total_v) if total_v > 0 else None
    except Exception:
        return None

# ---------------------------------------------------------------------------
# yfinance screener pipeline (used when strategy data_source == "yfinance_screener")
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)
def _fetch_yf_screener(
    price_min: float, price_max: float,
    pct_min: float,
    min_volume,           # may be None
    mktcap_min: int, mktcap_max: int,
) -> list:
    from yfinance import EquityQuery
    import yfinance as yf
    operands = [
        EquityQuery('eq',   ['region', 'us']),
        EquityQuery('btwn', ['intradaymarketcap', mktcap_min, mktcap_max]),
        EquityQuery('btwn', ['intradayprice', price_min, price_max]),
        EquityQuery('gt',   ['percentchange', pct_min * 100]),
    ]
    if min_volume:
        operands.append(EquityQuery('gt', ['dayvolume', min_volume]))
    result = yf.screen(EquityQuery('and', operands), sortField='dayvolume', sortAsc=False)
    return result.get('quotes', [])


@st.cache_data(ttl=60)
def fetch_daily_bars_yf(symbols: tuple) -> dict:
    import yfinance as yf
    if not symbols:
        return {}
    result = {}
    raw = yf.download(list(symbols), period="3mo", interval="1d",
                      auto_adjust=True, progress=False)
    for sym in symbols:
        try:
            df = raw.xs(sym, level=1, axis=1) if isinstance(raw.columns, pd.MultiIndex) else raw.copy()
            df = df.dropna(subset=["Volume"]).rename(columns={"Volume": "volume"})
            result[sym] = df
        except Exception:
            pass
    return result


def run_pipeline_yf(strategy: dict) -> tuple:
    pct_min = strategy["pct_change_min"] or strategy.get("gap_min", 0)
    try:
        quotes = _fetch_yf_screener(
            price_min  = strategy["price_min"],
            price_max  = strategy["price_max"],
            pct_min    = pct_min,
            min_volume = strategy["min_volume"],
            mktcap_min = strategy["mktcap_min"],
            mktcap_max = strategy.get("mktcap_max", 10_000_000_000),
        )
    except Exception:
        return _empty_df(strategy), 0

    fsyms = [q.get("symbol") for q in quotes if q.get("symbol")]
    if not fsyms:
        return _empty_df(strategy), 0

    rvol_min      = strategy["rvol_min"]
    daily_bars_yf = fetch_daily_bars_yf(tuple(fsyms)) if rvol_min is not None else {}
    intraday_bars = fetch_intraday_bars(tuple(fsyms))

    rvol_col = strategy["rvol_label"]
    rows = []
    for q in quotes:
        try:
            sym        = q.get("symbol", "")
            price      = q.get("regularMarketPrice")
            prev_close = q.get("regularMarketPreviousClose")
            volume     = q.get("regularMarketVolume", 0)
            mktcap     = q.get("marketCap", 0)
            pct        = q.get("regularMarketChangePercent", 0)
            if not sym or not price or not prev_close:
                continue

            if rvol_min is not None:
                d_df = daily_bars_yf.get(sym)
                if d_df is None or d_df.empty:
                    continue
                rvol = compute_relative_volume(d_df, volume, strategy)
                if rvol is None or rvol < rvol_min:
                    continue
            else:
                rvol = None

            vwap = compute_vwap(intraday_bars.get(sym))
            if strategy["vwap_filter"] and (vwap is None or price >= vwap):
                continue

            rows.append({
                "Symbol":     sym,
                "Prev Close": round(prev_close, 2),
                "Last Price": round(price, 2),
                "% Change":   round(pct, 2),
                "Volume":     int(volume),
                rvol_col:     round(rvol, 1) if rvol is not None else None,
                "VWAP":       round(vwap, 2) if vwap is not None else None,
                "vs VWAP":    round(price - vwap, 2) if vwap is not None else None,
                "Market Cap": int(mktcap),
            })
        except Exception:
            continue

    if not rows:
        return _empty_df(strategy), 0
    df = pd.DataFrame(rows).sort_values("% Change", ascending=False).reset_index(drop=True)
    return df, 0


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _empty_df(strategy: dict) -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "Symbol", "Prev Close", "Last Price", "% Change", "Volume",
        strategy["rvol_label"], "VWAP", "vs VWAP", "Market Cap",
    ])


def run_pipeline(strategy: dict) -> tuple:
    if strategy.get("data_source") == "yfinance_screener":
        return run_pipeline_yf(strategy)

    universe     = fetch_universe()
    snapshots    = fetch_snapshots(tuple(universe))
    pre_filtered = filter_by_snapshot(snapshots, strategy)

    if not pre_filtered:
        return _empty_df(strategy), 0

    fsyms    = [r["symbol"] for r in pre_filtered]
    snap_map = {r["symbol"]: r for r in pre_filtered}

    daily_bars    = fetch_daily_bars(tuple(fsyms))
    intraday_bars = fetch_intraday_bars(tuple(fsyms))
    market_caps   = fetch_market_caps(tuple(fsyms))

    rvol_col = strategy["rvol_label"]
    rows = []
    for sym in fsyms:
        s          = snap_map[sym]
        price      = s["price"]
        pct        = s["pct_change"]
        volume     = s["volume"]
        prev_close = s["prev_close"]

        d_df = daily_bars.get(sym)
        if d_df is None or d_df.empty:
            continue
        rvol = compute_relative_volume(d_df, volume, strategy)
        rvol_min = strategy["rvol_min"]
        if rvol_min is not None and (rvol is None or rvol < rvol_min):
            continue

        vwap = compute_vwap(intraday_bars.get(sym))
        if strategy["vwap_filter"] and (vwap is None or price >= vwap):
            continue

        mktcap = market_caps.get(sym, 0.0)
        if mktcap < strategy["mktcap_min"]:
            continue
        mktcap_max = strategy.get("mktcap_max")
        if mktcap_max is not None and mktcap > mktcap_max:
            continue

        rows.append({
            "Symbol":     sym,
            "Prev Close": round(prev_close, 2),
            "Last Price": round(price, 2),
            "% Change":   round(pct * 100, 2),
            "Volume":     int(volume),
            rvol_col:     round(rvol, 1),
            "VWAP":       round(vwap, 2) if vwap is not None else None,
            "vs VWAP":    round(price - vwap, 2) if vwap is not None else None,
            "Market Cap": int(mktcap),
        })

    if not rows:
        return _empty_df(strategy), 0

    df = pd.DataFrame(rows).sort_values(rvol_col, ascending=False).reset_index(drop=True)
    return df, 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_market_open() -> bool:
    now = datetime.now(tz=ET)
    return now.weekday() < 5 and MARKET_OPEN <= now.time() <= MARKET_CLOSE


def format_market_cap(cap) -> str:
    if cap is None:
        return "—"
    cap = int(cap)
    if cap >= 1_000_000_000:
        return f"${cap / 1_000_000_000:.1f}B"
    return f"${cap / 1_000_000:.1f}M"
