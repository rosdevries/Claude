# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This workspace contains three independent Python projects focused on penny stock trading: a backtesting system, a live stock screener, and an intraday chart viewer. All projects connect to the Alpaca API (IEX free-tier data feed) and share the same `.env` credential format.

## Shared Setup

Every project reads credentials from a `.env` file in its own directory:
```
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
```

Install dependencies per project with `pip install -r requirements.txt`.

---

## Project: Backtest Strategy Machine

**Location:** `Projects/Backtest Strategy Machine/`

### Running the pipeline

Step 1 — fetch and validate data (run once, or when refreshing the universe):
```bash
python main.py
```

Step 2 — run the walk-forward backtest:
```bash
python run_backtest.py
```

### Architecture

The pipeline is split into two scripts with distinct responsibilities:

**`main.py`** — Data pipeline:
1. Universe screening via `fetch_universe.py` (filters: $0.50–$10, ≥500k avg daily volume)
2. OHLCV fetching via `fetch_ohlcv.py` (1 year daily bars + 90 days of 15-min bars, saved as CSVs under `data/daily/` and `data/intraday/`)
3. Data validation via `data_validator.py` (results written to `data/validation_report.csv`)

**`run_backtest.py`** — Walk-forward backtest (8 steps):
1. Loads validated symbols from `data/penny_stock_universe.csv` + `data/validation_report.csv`
2. Enriches DataFrames with technical indicators (`indicators.py`)
3. Splits each symbol 70% in-sample / 30% out-of-sample by date
4. Generates entry signals in-sample (`signals.py`)
5. Sweeps trailing-stop parameters in-sample (`optimizer.py`)
6. Selects best (signal_type, trailing_stop_pct) combo by profit factor
7. Runs final out-of-sample backtest with the winning combo (`backtester.py`)
8. Generates an HTML report (`report.py`) saved in `results/`

**Signal types** (`signals.py`): `gap_volume_surge`, `vwap_reclaim`, `opening_range_breakout`. Each returns a DataFrame with columns: `date, entry_timestamp, signal_type, entry_price, signal_strength, notes`.

**Indicator contract** (`indicators.py`): `add_daily_indicators()` and `add_intraday_indicators()` must be called before signals or the backtester. Intraday DataFrames must have columns including `bar_of_day`, `rvol_15`, `above_vwap`, `or_high`, `or_low`.

**`config.py`** is the single source of truth for all filter thresholds and API settings. Change penny-stock price/volume filters here, not in individual modules.

Set `VERBOSE = True` at the top of `run_backtest.py` to print every trade during the backtest.

---

## Project: Stock Screener

**Location:** `Projects/Stock Screener/`

### Running

```bash
streamlit run screener.py
```

### Architecture

**`screener.py`** is the main Streamlit app. It implements a full screening pipeline in-process:
- Fetches all tradable US equities from Alpaca (`fetch_universe`, cached 1 hr)
- Applies snapshot-based pre-filter: price $0.50–$10, daily gain ≥15% (`filter_by_snapshot`)
- Computes relative volume z-score vs. 50-bar baseline; requires ≥4σ (`compute_relative_volume`)
- Requires price **below** session VWAP (`compute_vwap`)
- Fetches market cap via yfinance (parallel, 20 workers); requires ≥$7M
- Auto-refreshes every 60 seconds via `streamlit-autorefresh`
- Clicking a symbol in the table opens a split-panel intraday chart (5-min bars + VWAP overlay)

The `scanner/` package (`clients.py`, `scanner.py`, `index.py`, `strategies/`) is a secondary/refactored module that was being developed alongside the monolithic `screener.py`.

All screening constants (price bounds, z-score threshold, market cap minimum) are defined at the top of `screener.py`.

---

## Project: Intraday Stock Chart

**Location:** `Projects/Intraday Stock Chart/`

### Running

```bash
streamlit run stock_chart.py
```

Single-file Streamlit app. Accepts a ticker symbol, fetches 5-min bars from Alpaca (falling back up to 5 days to handle weekends/holidays), and renders a candlestick chart with a VWAP overlay. API keys can be entered in the sidebar or pre-populated from `.env`.
