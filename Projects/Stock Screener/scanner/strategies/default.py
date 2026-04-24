STRATEGY = {
    "name":           "Default Momentum",
    "description":    "Price up ≥15% today · $0.50–$10 · mkt cap ≥$7M · RVOL ≥4σ · price < VWAP",
    "price_min":      0.50,
    "price_max":      10.00,
    "pct_change_min": 0.15,    # current price ≥15% above prev close
    "gap_min":        None,    # no gap-at-open filter
    "min_volume":     None,    # no raw volume floor
    "mktcap_min":     7_000_000,
    "rvol_lookback":  50,
    "rvol_method":    "zscore",
    "rvol_min":       4.0,
    "rvol_project":   True,    # project partial-day volume to full-day equivalent
    "vwap_filter":    True,    # only pass stocks trading below VWAP
    "rvol_label":     "Rel Vol (σ)",
    "data_source":    "yfinance_screener",
}
