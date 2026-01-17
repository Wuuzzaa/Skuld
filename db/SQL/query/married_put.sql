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
                                (minimum_potential_profit / days_to_expiration) * 365,
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
                                        dividend_sum_to_expiration - (extrinsic_value * number_of_stocks) -3.5,
                                        2
                                    ) as minimum_potential_profit
                                FROM
                                    (
                                        SELECT
                                            *,
                                            ROUND(extrinsic_value * number_of_stocks + 3.5, 2) as max_loss_total,
                                            CAST(ceil(extrinsic_value / "Current-Div") as Integer) as dividends_to_break_even,
                                            ROUND(dividends_to_expiration * "Current-Div", 2) * number_of_stocks AS dividend_sum_to_expiration
                                        FROM
                                            (
                                                SELECT
                                                    100 as number_of_stocks,
                                                    symbol,
                                                    "Company",
                                                    sector,
                                                    "Industry",
                                                    expiration_date,
                                                    days_to_expiration,
                                                    option_open_interest,
                                                    bid,
                                                    ask,
                                                    spread_ptc,
                                                    premium_option_price,
                                                    intrinsic_value,
                                                    extrinsic_value,
                                                    strike,
                                                    iv,
                                                    round(impliedVolatility, 2) as impliedVolatility,
                                                    delta,
                                                    "SMA200",
                                                    live_stock_price,
                                                    strike_stock_price_difference,
                                                    strike_stock_price_difference_ptc,
                                                    analyst_mean_target as analyst_mean_target_price_year,
                                                    "Fair-Value",
                                                    earnings_date,
                                                    days_to_earnings,
                                                    "No-Years",
                                                    classification,
                                                    "Payouts/-Year",
                                                    "Current-Div",
                                                    CAST(
                                                        ROUND(("Payouts/-Year" * (days_to_expiration / 365.0))) AS INTEGER
                                                    ) AS dividends_to_expiration
                                                FROM
                                                    "OptionDataMerged"
                                                WHERE
                                                    has_fundamental_data_dividend_radar = true
                                                    and "option-type" = 'puts'
                                                    and strike > live_stock_price * 1.2
                                            )
                                    )
                            )
                    )
                WHERE
                    extrinsic_value > 0
                    and option_open_interest > 0
                    and days_to_expiration > 90
            )
    )
WHERE
    symbol_option_rank <= 3
ORDER BY
    roi_annualized_pct DESC;