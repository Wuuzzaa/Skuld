DROP VIEW IF EXISTS "OptionPricingMetrics";
CREATE VIEW
    "OptionPricingMetrics" AS
Select
    symbol,
    option_osi,
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
            a.option_osi,
            CAST(
                julianday (a.expiration_date) - julianday ('now') AS INTEGER
            ) AS days_to_expiration,
            c.live_stock_price,
            ROUND(a."strike_price" - c.live_stock_price, 2) as strike_stock_price_difference,
            ROUND(
                (a."strike_price" - c.live_stock_price) / c.live_stock_price * 100,
                2
            ) as strike_stock_price_difference_ptc,
            case
                when a."contract_type" = 'call' then max(c.live_stock_price - a."strike_price", 0)
                when a."contract_type" = 'put' then max(a."strike_price" - c.live_stock_price, 0)
                else null
            end as intrinsic_value,
            (b.ask + b.bid) / 2 as premium_option_price,
            b.ask - b.bid as spread,
            ROUND((b.ask - b.bid) / b.bid * 100, 2) as spread_ptc
        from
            "OptionDataMassive" as a
            LEFT OUTER JOIN "OptionDataYahoo" as b ON a.option_osi = b."contractSymbol"
            LEFT OUTER JOIN "StockPrice" as c ON a.symbol = c.symbol
    );