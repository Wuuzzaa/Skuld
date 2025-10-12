SELECT DISTINCT
    symbol,
    close,
    analyst_mean_target,
    recommendation,
    "Recommend.All",
    "target-close$",
    "target-close%"
FROM
    OptionDataMerged;