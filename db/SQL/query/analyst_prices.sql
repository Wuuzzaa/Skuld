SELECT DISTINCT
    symbol,
    live_stock_price as close,
    analyst_mean_target,
    recommendation,
    "Recommend.All",
    "target-close$",
    "target-close%"
FROM
    "OptionDataMerged";