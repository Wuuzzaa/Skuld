DROP VIEW IF EXISTS OptionPricingMetrics;

CREATE VIEW
    OptionPricingMetrics AS
Select
    symbol,
    contractSymbol,
    days_to_expiration,
    ROUND(premium_option_price, 2) as premium_option_price,
    spread,
    spread_ptc,
    ROUND(intrinsic_value, 2) as intrinsic_value,
    ROUND(premium_option_price - intrinsic_value, 2) as extrinsic_value,
    strike_stock_price_difference,
    strike_stock_price_difference_ptc
    -- strike - live_stock_price as moneyness
FROM
    (
        select
            a.symbol,
            a.contractSymbol,
            CAST(
                julianday (expiration_date) - julianday ('now') AS INTEGER
            ) AS days_to_expiration,
            a.strike,
            b.live_stock_price,
            ROUND(a.strike - b.live_stock_price, 2) as strike_stock_price_difference,
            ROUND(
                (a.strike - b.live_stock_price) / b.live_stock_price * 100,
                2
            ) as strike_stock_price_difference_ptc,
            case
                when "option-type" = 'calls' then max(live_stock_price - strike, 0)
                when "option-type" = 'puts' then max(strike - live_stock_price, 0)
                else null
            end as intrinsic_value,
            (ask + bid) / 2 as premium_option_price,
            ask - bid as spread,
            ROUND((ask - bid) / bid * 100, 2) as spread_ptc
        from
            OptionDataYahoo as a
            JOIN StockPrice as b ON a.symbol = b.symbol
    );