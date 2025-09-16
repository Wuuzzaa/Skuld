DROP VIEW IF EXISTS OptionPricingMetrics;

CREATE VIEW
    OptionPricingMetrics AS
Select
    symbol,
    option_osi,
    premium_option_price,
    intrinsic_value,
    premium_option_price - intrinsic_value as extrinsic_value,
    strike - live_stock_price as moneyness
FROM
    (
        select
            a.symbol,
            a.option_osi,
            a.strike,
            b.live_stock_price,
            case
                when "option-type" = 'call' then max(live_stock_price - strike, 0)
                when "option-type" = 'put' then max(strike - live_stock_price, 0)
                else null
            end as intrinsic_value,
            ifnull ("theoPrice", (ask + bid) / 2) as premium_option_price
        from
            OptionDataTradingView as a
            JOIN StockData as b ON a.symbol = b.symbol
    );