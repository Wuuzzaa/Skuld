DROP VIEW IF EXISTS OptionDataHistory;
CREATE VIEW
	OptionDataHistory AS

WITH OptionDataYahooHistoryCTE AS (
 <OptionDataYahooHistorySelect>
),
OptionDataTradingViewHistoryCTE AS (
 <OptionDataTradingViewHistorySelect>
),
StockPriceHistoryCTE AS (
 <StockPriceHistorySelect>
),
OptionPricingMetricsHistoryCTE AS (
    Select
    date,
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
            a.date,
            a.symbol,
            a.contractSymbol,
            CAST(
                julianday (expiration_date) - julianday (a.date) AS INTEGER
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
            OptionDataYahooHistoryCTE as a
            JOIN StockPriceHistoryCTE as b ON a.symbol = b.symbol
            AND a.date = b.date
    )
)
SELECT
	a.date, 
	-- OptionDataYahooHistory
	a.symbol,
	a."option-type",
	DATE (a.expiration_date) as expiration_date,
	a.strike,
	a.bid,
	a.ask,
	a."contractSymbol",
	a.currency,
	a."lastPrice",
	a.change,
	a."percentChange",
	a.option_open_interest,
	a."contractSize",
	a."lastTradeDate",
	a."impliedVolatility",
	a."inTheMoney",
	a.option_volume,
	-- OptionDataTradingViewHistory
	CASE
		WHEN b.option_osi IS NOT NULL THEN TRUE
		ELSE FALSE
	END as has_option_data_tradingview,
	b.delta,
	b.gamma,
	b.iv,
	b.rho,
	b."theoPrice",
	b.theta,
	b.vega,
	b.option,
	b.time,
	b.exchange,
	b.option_osi,
	-- OptionPricingMetricsHistory
	CASE
		WHEN c.contractSymbol IS NOT NULL THEN TRUE
		ELSE FALSE
	END as has_option_pricing_metrics,
	c.days_to_expiration,
	c.premium_option_price,
	c.spread,
	c.spread_ptc,
	c.intrinsic_value,
	c.extrinsic_value,
	c.strike_stock_price_difference,
	c.strike_stock_price_difference_ptc
FROM
	OptionDataYahooHistoryCTE as a
	LEFT OUTER JOIN OptionDataTradingViewHistoryCTE AS b 
    ON a.contractSymbol = b.option_osi
	AND a.date = b.date
	LEFT OUTER JOIN OptionPricingMetricsHistoryCTE as c 
    ON a.contractSymbol = c.contractSymbol
	AND a.date = c.date;