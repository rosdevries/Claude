# Translated from ThinkScript:
#   input minGapPercent   = 3.0
#   input minDailyVolume  = 1000000
#   input rvolLength      = 50
#   input rvolMultiplier  = 1.5
#   gapCondition  = (todayOpen - prevClose) / prevClose * 100 >= minGapPercent
#   volumeCondition = todayVolume >= minDailyVolume
#   rvolCondition   = todayVolume > rvolMultiplier * Average(volume, rvolLength)

STRATEGY = {
    "name":           "Gap + RVOL",
    "description":    "Gap ≥3% at open · vol ≥1M · RVOL ≥1.5× 50-bar avg · $2–$10 · mkt cap ≥$100M",
    "price_min":      2.00,
    "price_max":      10.00,
    "pct_change_min": None,          # no intraday % filter; gap_min is used instead
    "gap_min":        0.03,          # (todayOpen - prevClose) / prevClose >= 3%
    "min_volume":     1_000_000,     # minDailyVolume
    "mktcap_min":     100_000_000,
    "rvol_lookback":  50,            # rvolLength
    "rvol_method":    "ratio",       # todayVolume / Average(volume, rvolLength)
    "rvol_min":       1.5,           # rvolMultiplier
    "rvol_project":   False,         # ThinkScript uses raw todayVolume; no projection
    "vwap_filter":    False,         # not in ThinkScript; VWAP still computed for display
    "rvol_label":     "Rel Vol (×)",
}
