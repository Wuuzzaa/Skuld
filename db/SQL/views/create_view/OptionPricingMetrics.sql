DROP VIEW IF EXISTS OptionPricingMetrics;

CREATE VIEW
    OptionPricingMetrics AS
Select
    symbol,
    contractSymbol,
    days_to_expiration,
    premium_option_price,
    intrinsic_value,
    premium_option_price - intrinsic_value as extrinsic_value,
    strike - live_stock_price as moneyness
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
            case
                when "option-type" = 'calls' then max(live_stock_price - strike, 0)
                when "option-type" = 'puts' then max(strike - live_stock_price, 0)
                else null
            end as intrinsic_value,
            (ask + bid) / 2 as premium_option_price
        from
            OptionDataYahoo as a
            JOIN StockPrice as b ON a.symbol = b.symbol
    );