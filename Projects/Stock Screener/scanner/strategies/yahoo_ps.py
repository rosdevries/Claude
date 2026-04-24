STRATEGY = {
    "name":           "Yahoo PS Screener",
    "description":    "Price $0.50–$10 · gain >15% · vol >2M · mkt cap $7M–$1.5B · no RVOL/VWAP filter",
    "price_min":      0.50,
    "price_max":      10.00,
    "pct_change_min": 0.15,
    "gap_min":        None,
    "min_volume":     2_000_000,
    "mktcap_min":     7_000_000,
    "mktcap_max":     1_500_000_000,
    "rvol_lookback":  50,
    "rvol_method":    "zscore",
    "rvol_min":       None,           # display only — not used to filter
    "rvol_project":   True,
    "vwap_filter":    False,
    "rvol_label":     "Rel Vol (σ)",
    "data_source":    "yfinance_screener",
}
