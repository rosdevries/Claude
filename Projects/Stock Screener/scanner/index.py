import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import warnings
from datetime import datetime
from urllib.parse import quote_plus

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from scanner.clients import trading_client, data_client  # noqa: F401 — validates credentials
from scanner.scanner import (
    ET,
    _empty_df,
    format_market_cap,
    get_chart_bars,
    get_company_name,
    is_market_open,
    run_pipeline,
)
from scanner.strategies.default  import STRATEGY as DEFAULT
from scanner.strategies.gap_rvol import STRATEGY as GAP_RVOL
from scanner.strategies.yahoo_ps import STRATEGY as YAHOO_PS

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Strategy registry — add new strategies here
# ---------------------------------------------------------------------------
STRATEGIES: dict = {s["name"]: s for s in [DEFAULT, GAP_RVOL, YAHOO_PS]}

# ---------------------------------------------------------------------------
# CSS + theme
# ---------------------------------------------------------------------------
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
# Table builder
# ---------------------------------------------------------------------------

def build_table_html(df, selected: str, strategy: dict) -> str:
    if df.empty:
        return (
            "<p style='color:#7a8ba0; padding:24px 0;'>"
            "No stocks currently meet all screening criteria.</p>"
        )

    df = df.sort_values("% Change", ascending=False)

    rvol_col = strategy["rvol_label"]
    rows_html = []
    for _, r in df.iterrows():
        sym    = r["Symbol"]
        price  = r["Last Price"]
        pct    = r["% Change"]
        vol    = r["Volume"]
        rvol   = r[rvol_col]
        mktcap = format_market_cap(r["Market Cap"])
        vs_raw = r.get("vs VWAP")

        sel    = "selected" if sym == selected else ""
        pcls   = "pos" if pct >= 0 else "neg"
        psign  = "+" if pct >= 0 else ""
        vs_str = f"${abs(vs_raw):.2f} below" if vs_raw is not None else "—"

        prev_close = r.get("Prev Close")
        pc_str     = f"${prev_close:.2f}" if prev_close is not None else "—"

        rows_html.append(
            f'<tr class="{sel}">'
            f'<td><a class="sym-link" href="?symbol={sym}&strategy={quote_plus(strategy["name"])}">{sym}</a></td>'
            f"<td>{pc_str}</td>"
            f"<td>${price:.2f}</td>"
            f'<td class="{pcls}">{psign}{pct:.1f}%</td>'
            f"<td>{int(vol):,}</td>"
            f"<td>{'—' if rvol is None else f'{rvol:.1f}'}</td>"
            f'<td class="pos">{vs_str}</td>'
            f'<td class="dim">{mktcap}</td>'
            f"</tr>"
        )

    return (
        '<table class="screener-table">'
        "<thead><tr>"
        f"<th>Symbol</th><th>Prev Close</th><th>Last Price</th><th>% Change</th>"
        f"<th>Volume</th><th>{rvol_col}</th><th>vs VWAP</th><th>Mkt Cap</th>"
        "</tr></thead>"
        "<tbody>" + "\n".join(rows_html) + "</tbody>"
        "</table>"
    )

# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def build_candle_chart(df) -> go.Figure:
    if df.empty:
        fig = go.Figure()
        fig.update_layout(
            paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG,
            annotations=[dict(
                text="No intraday data available",
                x=0.5, y=0.5, xref="paper", yref="paper",
                showarrow=False, font=dict(color="#7a8ba0", size=14),
            )],
        )
        return fig

    x = df.index.strftime("%H:%M")
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.70, 0.30], vertical_spacing=0.02,
    )

    fig.add_trace(go.Candlestick(
        x=x, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color="#26a69a", increasing_fillcolor="#26a69a",
        decreasing_line_color="#ef5350", decreasing_fillcolor="#ef5350",
        showlegend=False, whiskerwidth=0.5,
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
        x=x, y=df["volume"], marker_color=bar_colors, showlegend=False,
    ), row=2, col=1)

    fig.update_layout(
        paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG,
        font=dict(color="#c9d1d9", size=10),
        margin=dict(l=5, r=5, t=20, b=5),
        legend=dict(orientation="h", y=1.05, x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
        height=390, xaxis_rangeslider_visible=False,
    )
    for i in [1, 2]:
        fig.update_xaxes(showgrid=True, gridcolor=GRID_CLR, zeroline=False, tickfont=dict(size=9), row=i, col=1)
        fig.update_yaxes(showgrid=True, gridcolor=GRID_CLR, zeroline=False, tickfont=dict(size=9), row=i, col=1)

    return fig

# ---------------------------------------------------------------------------
# Panel renderers
# ---------------------------------------------------------------------------

def render_chart_panel(symbol: str, scan_df, strategy: dict) -> None:
    hdr_col, close_col = st.columns([4, 1])

    with close_col:
        if st.button("✕ Close", key="close_panel", width="stretch"):
            if "symbol" in st.query_params:
                del st.query_params["symbol"]
            st.rerun()

    rvol_col = strategy["rvol_label"]
    row      = scan_df[scan_df["Symbol"] == symbol]
    company  = get_company_name(symbol)

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
        c1.metric("Open",   f"${chart_df['open'].iloc[0]:.2f}")
        c2.metric("High",   f"${chart_df['high'].max():.2f}")
        c3.metric("Low",    f"${chart_df['low'].min():.2f}")
        c4.metric("Volume", f"{int(r['Volume']):,}")
        rvol_val = r.get(rvol_col)
        c5.metric(rvol_col, f"{rvol_val:.1f}" if rvol_val is not None else "—")


def render_sidebar(df, error_count: int, last_run: datetime) -> dict:
    with st.sidebar:
        st.header("Strategy")
        strategy_name = st.selectbox(
            "Active Strategy",
            list(STRATEGIES.keys()),
            key="active_strategy",
        )
        strategy = STRATEGIES[strategy_name]
        st.caption(strategy["description"])

        st.divider()
        st.header("Screener Status")
        st.metric("Last Scan", last_run.strftime("%H:%M:%S ET"))
        st.metric("Results",   f"{len(df)} stock(s)")

        if error_count > 0:
            st.warning(f"{error_count} fetch error(s) — some symbols skipped")
        else:
            st.success("No fetch errors")

        st.divider()
        st.subheader("Active Filters")
        lines = [
            f"- Price: **${strategy['price_min']:.2f} – ${strategy['price_max']:.2f}**",
        ]
        if strategy["pct_change_min"] is not None:
            lines.append(f"- Gain: **≥{strategy['pct_change_min']*100:.0f}%**")
        if strategy["gap_min"] is not None:
            lines.append(f"- Gap at open: **≥{strategy['gap_min']*100:.0f}%**")
        if strategy["min_volume"]:
            lines.append(f"- Min volume: **{strategy['min_volume']:,}**")
        mktcap_max = strategy.get("mktcap_max")
        if mktcap_max is not None:
            lines.append(
                f"- Mkt cap: **${strategy['mktcap_min']/1_000_000:.0f}M – ${mktcap_max/1_000_000_000:.1f}B**"
            )
        else:
            lines.append(f"- Mkt cap: **≥${strategy['mktcap_min']/1_000_000:.0f}M**")
        if strategy["rvol_min"] is not None:
            lines.append(
                f"- {strategy['rvol_label']}: **≥{strategy['rvol_min']}** ({strategy['rvol_method']})"
            )
        if strategy["vwap_filter"]:
            lines.append("- Price **< VWAP**")
        st.markdown("\n".join(lines))

        st.divider()
        if st.button("Refresh Now", width="stretch"):
            st.cache_data.clear()
            st.rerun()

    return strategy

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(layout="wide", page_title="Stock Screener", page_icon="📈")
    st.markdown(CSS, unsafe_allow_html=True)

    # Credential guard
    if trading_client is None:
        st.error("Missing ALPACA_API_KEY or ALPACA_SECRET_KEY in .env")
        st.stop()

    # Restore strategy from URL on fresh sessions (symbol link navigated / new tab)
    if "active_strategy" not in st.session_state:
        _raw = st.query_params.get("strategy")
        if _raw and _raw in STRATEGIES:
            st.session_state["active_strategy"] = _raw

    # State init
    for key, default in [
        ("scan_results",       None),
        ("scan_error_count",   0),
        ("last_refresh_count", -1),
        ("last_scan_time",     None),
        ("prev_strategy",      None),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # Autorefresh every 60 s
    refresh_count  = st_autorefresh(interval=60_000, key="screener_refresh")
    auto_refreshed = refresh_count != st.session_state.last_refresh_count
    st.session_state.last_refresh_count = refresh_count

    # Resolve active strategy from session_state (set by sidebar selectbox)
    strategy_name = st.session_state.get("active_strategy", list(STRATEGIES.keys())[0])
    strategy      = STRATEGIES.get(strategy_name, list(STRATEGIES.values())[0])

    # Force rescan when strategy changes
    if st.session_state.prev_strategy != strategy["name"]:
        st.session_state.scan_results = None
        st.session_state.prev_strategy = strategy["name"]

    # Selected symbol from URL query param (set by clicking a symbol link)
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

    # Run scan when needed
    need_scan = refresh_clicked or auto_refreshed or st.session_state.scan_results is None
    if refresh_clicked:
        st.cache_data.clear()

    if need_scan:
        with st.spinner("Scanning markets…"):
            df, ec = run_pipeline(strategy)
        st.session_state.scan_results     = df
        st.session_state.scan_error_count = ec
        st.session_state.last_scan_time   = datetime.now(tz=ET)

    df       = st.session_state.scan_results if st.session_state.scan_results is not None else _empty_df(strategy)
    ec       = st.session_state.scan_error_count
    last_run = st.session_state.last_scan_time or datetime.now(tz=ET)

    # Sidebar (also returns the currently selected strategy)
    strategy = render_sidebar(df, ec, last_run)

    # Main layout: split when a symbol is selected, full-width otherwise
    if selected and not df.empty:
        left, right = st.columns([55, 45])
        with left:
            st.markdown(f"**{len(df)} result(s)** — click a symbol to view its chart")
            st.markdown(build_table_html(df, selected, strategy), unsafe_allow_html=True)
        with right:
            render_chart_panel(selected, df, strategy)
    else:
        st.markdown(build_table_html(df, None, strategy), unsafe_allow_html=True)
        if not df.empty:
            st.caption("↑ Click a symbol to open the intraday chart panel")


if __name__ == "__main__":
    main()
