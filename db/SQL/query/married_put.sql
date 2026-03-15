WITH BaseData AS (
    SELECT
        100 as number_of_stocks,
        symbol,
        company_name AS "Company",
        company_sector AS "Sector",
        company_industry AS "Industry",
        expiration_date,
        days_to_expiration,
        open_interest,
        NULL AS bid,
        NULL AS ask,
        spread_ptc,
        premium_option_price,
        intrinsic_value,
        extrinsic_value,
        strike_price,
        NULL iv,
        round(CAST(implied_volatility AS NUMERIC), 2) as "impliedVolatility",
        greeks_delta AS delta,
        NULL "SMA200",
        live_stock_price,
        strike_stock_price_difference,
        strike_stock_price_difference_ptc,
        analyst_mean_target as analyst_mean_target_price_year,
        NULL "Fair-Value",
        earnings_date,
        days_to_earnings,
        dividend_growth_years AS "No-Years",
        dividend_classification AS "Classification",
        NO_DIVIDEND_PAYOUTS_LAST_YEAR AS "Payouts/-Year",
        "Summary_dividendRate" AS "Current-Div",
        CAST(FLOOR(days_to_expiration / NULLIF(365.0 / NULLIF(NO_DIVIDEND_PAYOUTS_LAST_YEAR, 0), 0)) AS INTEGER) AS dividends_to_expiration
    FROM
        "OptionDataMerged"
    WHERE
        "Summary_dividendRate" > 0
        AND contract_type = 'put'
        AND open_interest > 0
        AND extrinsic_value > 0
        AND strike_price > live_stock_price * :strike_multiplier
        AND days_to_expiration > 0
        AND NO_DIVIDEND_PAYOUTS_LAST_YEAR > 0
),
CalculatedData AS (
    SELECT
        *,
        ROUND(extrinsic_value * number_of_stocks + 3.5, 2) as max_loss_total,
        CAST(ceil(extrinsic_value / NULLIF("Current-Div" / NULLIF("Payouts/-Year", 0), 0)) as Integer) as dividends_to_break_even,
        ROUND(CAST("Current-Div" * (days_to_expiration / 365.0) AS NUMERIC), 2) * number_of_stocks AS dividend_sum_to_expiration
    FROM
        BaseData
),
InvestmentData AS (
    SELECT
        *,
        (
            (
                number_of_stocks * (live_stock_price + premium_option_price)
            ) + 3.5
        ) as total_investment,
        round(
            CAST(dividend_sum_to_expiration - (extrinsic_value * number_of_stocks) - 3.5 AS NUMERIC),
            2
        ) as minimum_potential_profit
    FROM
        CalculatedData
),
RoiData AS (
    SELECT
        *,
        (total_investment + minimum_potential_profit) as total_return,
        minimum_potential_profit / NULLIF(total_investment, 0) * 100 as roi_pct,
        round(
            CAST((minimum_potential_profit / NULLIF(total_investment, 0) * 100) / NULLIF(days_to_expiration, 0) * 365 AS NUMERIC),
            2
        ) as roi_annualized_pct
    FROM
        InvestmentData
),
RankedData AS (
    SELECT
        ROW_NUMBER() OVER (
            PARTITION BY symbol
            ORDER BY roi_annualized_pct DESC
        ) as symbol_option_rank,
        *
    FROM
        RoiData
)
SELECT
    *
FROM
    RankedData
WHERE
    symbol_option_rank <= 3
ORDER BY
    roi_annualized_pct DESC;