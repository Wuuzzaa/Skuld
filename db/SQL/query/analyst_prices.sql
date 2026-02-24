SELECT DISTINCT
    symbol,
    live_stock_price as close,
    analyst_mean_target,
    NULL recommendation,
    NULL "Recommend.All",
    "target-close$",
    "target-close%"
FROM
    "OptionDataMerged";