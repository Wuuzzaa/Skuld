SELECT
    *
FROM
    (
        SELECT
            ROW_NUMBER() OVER (
                PARTITION BY
                    symbol
                ORDER BY
                    roi_annualized_pct DESC
            ) as symbol_option_rank,
            *
        FROM
            (
                SELECT
                    *,
                    minimum_potential_profit_total_annualized / total_investment * 100 as roi_annualized_pct
                FROM
                    (
                        SELECT
                            *,
                            (total_investment + minimum_potential_profit) as total_return,
                            minimum_potential_profit / total_investment * 100 as roi_pct,
                            round(
                                CAST((minimum_potential_profit / days_to_expiration) * 365 AS NUMERIC ),
                                2
                            ) as minimum_potential_profit_total_annualized
                        FROM
                            (
                                SELECT
                                    *,
                                    (
                                        (
                                            number_of_stocks * (live_stock_price + premium_option_price)
                                        ) + 3.5
                                    ) as total_investment,
                                    round(
                                        CAST(dividend_sum_to_expiration - (extrinsic_value * number_of_stocks) -3.5 AS NUMERIC),
                                        2
                                    ) as minimum_potential_profit
                                FROM
                                    (
                                        SELECT
                                            *,
                                            ROUND(extrinsic_value * number_of_stocks + 3.5, 2) as max_loss_total,
                                            CAST(ceil(extrinsic_value / "Current-Div") as Integer) as dividends_to_break_even,
                                            ROUND(CAST(dividends_to_expiration * "Current-Div" AS NUMERIC), 2) * number_of_stocks AS dividend_sum_to_expiration
                                        FROM
                                            (
                                                SELECT
                                                    100 as number_of_stocks,
                                                    symbol,
                                                    "Company",
                                                    "Sector",
                                                    "Industry",
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
                                                    round(CAST(implied_volatility AS NUMERIC),2) as "impliedVolatility",
                                                    greeks_delta AS delta,
                                                    "SMA200",
                                                    live_stock_price,
                                                    strike_stock_price_difference,
                                                    strike_stock_price_difference_ptc,
                                                    analyst_mean_target as analyst_mean_target_price_year,
                                                    "Fair-Value",
                                                    earnings_date,
                                                    days_to_earnings,
                                                    "No-Years",
                                                    "Classification",
                                                    "Payouts/-Year",
                                                    "Current-Div",
                                                    CAST(
                                                        ROUND(("Payouts/-Year" * (days_to_expiration / 365.0))) AS INTEGER
                                                    ) AS dividends_to_expiration
                                                FROM
                                                    "OptionDataMerged"
                                                WHERE
                                                    has_fundamental_data_dividend_radar = true
                                                    and contract_type = 'put'
                                                    and strike > live_stock_price * 1.2
                                            ) AS sub_1
                                    ) AS sub_2
                            ) AS SUB_3
                    ) AS sub_4
                WHERE
                    extrinsic_value > 0
                    and open_interest > 0
                    and days_to_expiration > 90
            ) AS sub_5
    ) AS sub_6
WHERE
    symbol_option_rank <= 3
ORDER BY
    roi_annualized_pct DESC;