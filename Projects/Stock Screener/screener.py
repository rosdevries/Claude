import os
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import yfinance as yf
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.enums import AssetClass, AssetStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ET = ZoneInfo("America/New_York")
MARKET_OPEN  = time(9, 30)
MARKET_CLOSE = time(16, 0)

PRICE_MIN, PRICE_MAX = 0.50, 10.00
PCT_CHANGE_MIN  = 0.15
MKTCAP_MIN      = 7_000_000
RELVOL_Z_MIN    = 4.0
TRADING_HOURS   = 6.5
SNAPSHOT_BATCH  = 500
BARS_BATCH      = 50
YFINANCE_WORKERS = 20

DARK_BG  = "#0e1117"
GRID_CLR = "#1e2130"

CSS = """
<style>
@keyframes slideIn {
  from { transform: translateX(100%); opacity: 0; }
  to   { transform: translateX(0);    opacity: 1; }
}
[data-testid="stColumn"]:last-child {
  animation: slideIn 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}
.screener-table {
  width: 100%;
  border-collapse: collapse;
  font-family: 'Courier New', monospace;
  font-size: 0.88em;
}
.screener-table th {
  background: #0d1117;
  color: #5c7cad;
  padding: 8px 10px;
  text-align: left;
  border-bottom: 2px solid #1e2130;
  font-size: 0.75em;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.screener-table td {
  padding: 7px 10px;
  border-bottom: 1px solid #161b27;
  color: #dde6f0;
  white-space: nowrap;
}
.screener-table tr:hover td { background: #151a2e; }
.screener-table tr.selected td {
  background: #1a2d50 !important;
  border-left: 3px solid #4da6ff;
}
.sym-link {
  color: #4da6ff;
  text-decoration: none;
  font-weight: 700;
  letter-spacing: 0.02em;
}
.sym-link:hover { text-decoration: underline; }
.pos { color: #26a69a; font-weight: 600; }
.neg { color: #ef5350; font-weight: 600; }
.dim { color: #7a8ba0; }
</style>
"""

# ---------------------------------------------------------------------------
# Client initialization
# ---------------------------------------------------------------------------
load_dotenv()

try:
    _api_key    = os.environ["ALPACA_API_KEY"]
    _secret_key = os.environ["ALPACA_SECRET_KEY"]
    trading_client = TradingClient(_api_key, _secret_key, paper=True)
    data_client    = StockHistoricalDataClient(_api_key, _secret_key)
except KeyError as exc:
    st.error(f"Missing environment variable: {exc}. Check your .env file.")
    st.stop()

# ---------------------------------------------------------------------------
# Data fetching (cached)
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
        # Cumulative VWAP
        df["typical"]    = (df["high"] + df["low"] + df["close"]) / 3
        cum_tv           = (df["typical"] * df["volume"]).cumsum()
        cum_v            = df["volume"].cumsum()
        df["vwap_line"]  = cum_tv / cum_v.replace(0, np.nan)
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
# Calculation functions
# ---------------------------------------------------------------------------

def filter_by_snapshot(snapshots: dict) -> list:
    passing = []
    for sym, snap in snapshots.items():
        try:
            price      = snap.latest_trade.price
            prev_close = snap.previous_daily_bar.close
            volume     = snap.daily_bar.volume
            if not prev_close or prev_close == 0:
                continue
            pct = (price - prev_close) / prev_close
            if not (PRICE_MIN <= price <= PRICE_MAX) or pct < PCT_CHANGE_MIN:
                continue
            passing.append({"symbol": sym, "price": price, "pct_change": pct, "volume": volume})
        except (AttributeError, TypeError, ZeroDivisionError):
            continue
    return passing


def compute_relative_volume(daily_df: pd.DataFrame, snapshot_volume: int):
    try:
        df       = daily_df.sort_index()
        idx      = df.index
        dates    = idx.tz_convert(ET).date if idx.tz else pd.to_datetime(idx).dt.date.values
        today_et = datetime.now(tz=ET).date()
        hist     = df[dates != today_et]
        if len(hist) < 50:
            return None
        baseline = hist["volume"].iloc[-50:]
        mean_v, std_v = baseline.mean(), baseline.std(ddof=1)
        if std_v == 0:
            return None
        now_et  = datetime.now(tz=ET)
        open_dt = datetime(now_et.date().year, now_et.date().month, now_et.date().day, 9, 30, tzinfo=ET)
        elapsed = max((now_et - open_dt).total_seconds() / 3600, 0.0833)
        return (snapshot_volume * (TRADING_HOURS / elapsed) - mean_v) / std_v
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
# Pipeline
# ---------------------------------------------------------------------------

def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "Symbol", "Last Price", "% Change", "Volume",
        "Rel Vol (σ)", "VWAP", "vs VWAP", "Market Cap",
    ])


def run_pipeline() -> tuple:
    universe     = fetch_universe()
    snapshots    = fetch_snapshots(tuple(universe))
    pre_filtered = filter_by_snapshot(snapshots)
    if not pre_filtered:
        return _empty_df(), 0

    fsyms    = [r["symbol"] for r in pre_filtered]
    snap_map = {r["symbol"]: r for r in pre_filtered}

    daily_bars    = fetch_daily_bars(tuple(fsyms))
    intraday_bars = fetch_intraday_bars(tuple(fsyms))
    market_caps   = fetch_market_caps(tuple(fsyms))

    rows = []
    for sym in fsyms:
        s      = snap_map[sym]
        price  = s["price"]
        pct    = s["pct_change"]
        volume = s["volume"]

        d_df = daily_bars.get(sym)
        if d_df is None or d_df.empty:
            continue
        z = compute_relative_volume(d_df, volume)
        if z is None or z < RELVOL_Z_MIN:
            continue

        vwap = compute_vwap(intraday_bars.get(sym))
        if vwap is None or price >= vwap:
            continue

        mktcap = market_caps.get(sym, 0.0)
        if mktcap < MKTCAP_MIN:
            continue

        rows.append({
            "Symbol":      sym,
            "Last Price":  round(price, 2),
            "% Change":    round(pct * 100, 2),
            "Volume":      int(volume),
            "Rel Vol (σ)": round(z, 1),
            "VWAP":        round(vwap, 2),
            "vs VWAP":     round(price - vwap, 2),
            "Market Cap":  int(mktcap),
        })

    if not rows:
        return _empty_df(), 0
    df = pd.DataFrame(rows).sort_values("Rel Vol (σ)", ascending=False).reset_index(drop=True)
    return df, 0

# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def format_market_cap(cap: int) -> str:
    if cap >= 1_000_000_000:
        return f"${cap / 1_000_000_000:.1f}B"
    return f"${cap / 1_000_000:.1f}M"


def is_market_open() -> bool:
    now = datetime.now(tz=ET)
    return now.weekday() < 5 and MARKET_OPEN <= now.time() <= MARKET_CLOSE


def build_table_html(df: pd.DataFrame, selected: str) -> str:
    if df.empty:
        return (
            "<p style='color:#7a8ba0; padding:24px 0;'>"
            "No stocks currently meet all five screening criteria.</p>"
        )

    rows_html = []
    for _, r in df.iterrows():
        sym    = r["Symbol"]
        price  = r["Last Price"]
        pct    = r["% Change"]
        vol    = r["Volume"]
        rvol   = r["Rel Vol (σ)"]
        mktcap = format_market_cap(r["Market Cap"])
        vs     = r["vs VWAP"]

        sel    = "selected" if sym == selected else ""
        pcls   = "pos" if pct >= 0 else "neg"
        psign  = "+" if pct >= 0 else ""
        vs_str = f"${abs(vs):.2f} below"

        rows_html.append(
            f'<tr class="{sel}">'
            f'<td><a class="sym-link" href="?symbol={sym}">{sym}</a></td>'
            f"<td>${price:.2f}</td>"
            f'<td class="{pcls}">{psign}{pct:.1f}%</td>'
            f"<td>{vol:,}</td>"
            f"<td>{rvol:.1f}σ</td>"
            f'<td class="dim">{mktcap}</td>'
            f'<td class="pos">{vs_str}</td>'
            f"</tr>"
        )

    return (
        '<table class="screener-table">'
        "<thead><tr>"
        "<th>Symbol</th><th>Last Price</th><th>% Change</th>"
        "<th>Volume</th><th>Rel Vol (σ)</th><th>Mkt Cap</th><th>vs VWAP</th>"
        "</tr></thead>"
        "<tbody>" + "\n".join(rows_html) + "</tbody>"
        "</table>"
    )


def build_candle_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        fig = go.Figure()
        fig.update_layout(
            paper_bgcolor=DARK_BG,
            plot_bgcolor=DARK_BG,
            annotations=[dict(
                text="No intraday data available",
                x=0.5, y=0.5, xref="paper", yref="paper",
                showarrow=False, font=dict(color="#7a8ba0", size=14),
            )],
        )
        return fig

    x = df.index.strftime("%H:%M")

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.70, 0.30],
        vertical_spacing=0.02,
    )

    fig.add_trace(go.Candlestick(
        x=x,
        open=df["open"], high=df["high"],
        low=df["low"],   close=df["close"],
        increasing_line_color="#26a69a", increasing_fillcolor="#26a69a",
        decreasing_line_color="#ef5350", decreasing_fillcolor="#ef5350",
        showlegend=False,
        whiskerwidth=0.5,
    ), row=1, col=1)

    if "vwap_line" in df.columns and not df["vwap_line"].isna().all():
        fig.add_trace(go.Scatter(
            x=x, y=df["vwap_line"],
            line=dict(color="#FF9800", width=1.5, dash="dash"),
            name="VWAP",
        ), row=1, col=1)

    bar_colors = [
        "#26a69a" if c >= o else "#ef5350"
        for c, o in zip(df["close"], df["open"])
    ]
    fig.add_trace(go.Bar(
        x=x, y=df["volume"],
        marker_color=bar_colors,
        showlegend=False,
    ), row=2, col=1)

    fig.update_layout(
        paper_bgcolor=DARK_BG,
        plot_bgcolor=DARK_BG,
        font=dict(color="#c9d1d9", size=10),
        margin=dict(l=5, r=5, t=20, b=5),
        legend=dict(
            orientation="h", y=1.05, x=0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=10),
        ),
        height=390,
        xaxis_rangeslider_visible=False,
    )
    for i in [1, 2]:
        fig.update_xaxes(
            showgrid=True, gridcolor=GRID_CLR,
            zeroline=False, tickfont=dict(size=9),
            row=i, col=1,
        )
        fig.update_yaxes(
            showgrid=True, gridcolor=GRID_CLR,
            zeroline=False, tickfont=dict(size=9),
            row=i, col=1,
        )

    return fig

# ---------------------------------------------------------------------------
# Panel renderers
# ---------------------------------------------------------------------------

def render_chart_panel(symbol: str, scan_df: pd.DataFrame) -> None:
    hdr_col, close_col = st.columns([4, 1])

    with close_col:
        if st.button("✕ Close", key="close_panel", width="stretch"):
            st.query_params.clear()
            st.rerun()

    row = scan_df[scan_df["Symbol"] == symbol]
    company = get_company_name(symbol)

    with hdr_col:
        if not row.empty:
            r     = row.iloc[0]
            price = r["Last Price"]
            pct   = r["% Change"]
            pcol  = "#26a69a" if pct >= 0 else "#ef5350"
            psign = "+" if pct >= 0 else ""
            st.markdown(
                f"<div style='line-height:1.35; margin-bottom:4px'>"
                f"<span style='font-size:1.55em; font-weight:700'>{symbol}</span>&nbsp;"
                f"<span style='font-size:0.82em; color:#7a8ba0'>{company}</span><br>"
                f"<span style='font-size:1.3em; font-weight:600'>${price:.2f}</span>&nbsp;"
                f"<span style='color:{pcol}; font-weight:600; font-size:1.05em'>"
                f"{psign}{pct:.1f}%</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.subheader(symbol)

    st.divider()

    with st.spinner(f"Loading {symbol} bars…"):
        chart_df = get_chart_bars(symbol)

    st.plotly_chart(
        build_candle_chart(chart_df),
        width="stretch",
        config={"displayModeBar": False},
    )

    if not chart_df.empty and not row.empty:
        r = row.iloc[0]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Open",    f"${chart_df['open'].iloc[0]:.2f}")
        c2.metric("High",    f"${chart_df['high'].max():.2f}")
        c3.metric("Low",     f"${chart_df['low'].min():.2f}")
        c4.metric("Volume",  f"{int(r['Volume']):,}")
        c5.metric("Rel Vol", f"{r['Rel Vol (σ)']:.1f}σ")


def render_sidebar(df: pd.DataFrame, error_count: int, last_run: datetime) -> None:
    with st.sidebar:
        st.header("Screener Status")
        st.metric("Last Scan", last_run.strftime("%H:%M:%S ET"))
        st.metric("Results",   f"{len(df)} stock(s)")

        if error_count > 0:
            st.warning(f"{error_count} fetch error(s) — some symbols skipped")
        else:
            st.success("No fetch errors")

        st.divider()
        st.subheader("Active Filters")
        st.markdown(
            f"- Price: **${PRICE_MIN:.2f} – ${PRICE_MAX:.2f}**\n"
            f"- Daily gain: **≥{PCT_CHANGE_MIN * 100:.0f}%**\n"
            f"- Market cap: **≥${MKTCAP_MIN / 1_000_000:.0f}M**\n"
            f"- Rel. volume: **≥{RELVOL_Z_MIN}σ** vs 50-bar avg\n"
            f"- Price **below** session VWAP"
        )

        st.divider()
        if st.button("Refresh Now", width="stretch"):
            st.cache_data.clear()
            st.rerun()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(layout="wide", page_title="Stock Screener", page_icon="📈")
    st.markdown(CSS, unsafe_allow_html=True)

    # State init
    for key, default in [
        ("scan_results",       None),
        ("scan_error_count",   0),
        ("last_refresh_count", -1),
        ("last_scan_time",     None),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # Auto-refresh trigger every 60 s
    refresh_count  = st_autorefresh(interval=60_000, key="screener_refresh")
    auto_refreshed = refresh_count != st.session_state.last_refresh_count
    st.session_state.last_refresh_count = refresh_count

    # Selected symbol from URL query params (set by clicking a symbol link)
    selected = st.query_params.get("symbol") or None

    # Toolbar
    title_col, btn_col = st.columns([5, 1])
    with title_col:
        st.title("📈 Momentum Stock Screener")
        st.caption("US Equities · Alpaca IEX · Auto-refreshes every 60 s")
    with btn_col:
        st.write("")
        refresh_clicked = st.button("🔄 Refresh Scan", width="stretch")

    if not is_market_open():
        st.warning(
            "US markets are currently closed (9:30 AM – 4:00 PM ET, Mon–Fri). "
            "Showing last available data."
        )

    # Decide whether to re-run the scan
    need_scan = refresh_clicked or auto_refreshed or st.session_state.scan_results is None
    if refresh_clicked:
        st.cache_data.clear()

    if need_scan:
        with st.spinner("Scanning markets…"):
            df, ec = run_pipeline()
        st.session_state.scan_results     = df
        st.session_state.scan_error_count = ec
        st.session_state.last_scan_time   = datetime.now(tz=ET)

    df       = st.session_state.scan_results if st.session_state.scan_results is not None else _empty_df()
    ec       = st.session_state.scan_error_count
    last_run = st.session_state.last_scan_time or datetime.now(tz=ET)

    render_sidebar(df, ec, last_run)

    # Layout: split when a symbol is selected, full-width otherwise
    if selected and not df.empty:
        left, right = st.columns([55, 45])
        with left:
            st.markdown(
                f"**{len(df)} result(s)** — click a symbol to view its chart",
                unsafe_allow_html=False,
            )
            st.markdown(build_table_html(df, selected), unsafe_allow_html=True)
        with right:
            render_chart_panel(selected, df)
    else:
        st.markdown(build_table_html(df, None), unsafe_allow_html=True)
        if not df.empty:
            st.caption("↑ Click a symbol to open the intraday chart panel")


if __name__ == "__main__":
    main()
