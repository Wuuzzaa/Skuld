SELECT DISTINCT
    symbol,
    live_stock_price as close,
    analyst_mean_target,
    -- NULL recommendation, -- replace later with own recommendation based on technical indicators
    -- NULL "Recommend.All", -- replace later with own recommendation based on technical indicators
    "target-close$",
    "target-close%"
FROM
    "OptionDataMerged";