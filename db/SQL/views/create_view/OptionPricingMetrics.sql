DROP VIEW IF EXISTS OptionPricingMetrics;

CREATE VIEW
    OptionPricingMetrics AS
Select
    symbol,
    option_osi,
    expiration_date_formatted,
    CAST(
        julianday (expiration_date_formatted) - julianday ('now') AS INTEGER
    ) AS days_to_expiration,
    premium_option_price,
    intrinsic_value,
    premium_option_price - intrinsic_value as extrinsic_value,
    strike - live_stock_price as moneyness
FROM
    (
        select
            a.symbol,
            a.option_osi,
            date (
                substr (a.expiration_date, 1, 4) || '-' || substr (a.expiration_date, 5, 2) || '-' || substr (a.expiration_date, 7, 2)
            ) as expiration_date_formatted,
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