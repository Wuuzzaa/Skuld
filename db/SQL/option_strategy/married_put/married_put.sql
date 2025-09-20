SELECT
    *,
    (total_investment + minimum_potential_profit) as total_return,
    minimum_potential_profit / total_investment * 100 as roi_pct,
    minimum_potential_profit_total_annualized / total_investment * 100 as roi_annualized_pct
FROM
    (
        SELECT
            *,
            (
                (
                    minimum_potential_profit_per_option / days_to_expiration
                ) * 365
            ) as minimum_potential_profit_per_option_annualized,
            (
                (minimum_potential_profit / days_to_expiration) * 365
            ) as minimum_potential_profit_total_annualized,
            (
                (
                    number_of_options * (live_stock_price + premium_option_price)
                ) + 3.5
            ) as total_investment
        FROM
            (
                SELECT
                    *,
                    extrinsic_value + (3.5 / number_of_options) as max_loss_per_option,
                    extrinsic_value * number_of_options + 3.5 as max_loss_total,
                    (extrinsic_value / "Current-Div") as break_even_dividens,
                    (dividend_sum_per_option - extrinsic_value) as minimum_potential_profit_per_option,
                    (dividend_sum_per_option - extrinsic_value) * number_of_options as minimum_potential_profit
                FROM
                    (
                        SELECT
                            100 as number_of_options,
                            symbol,
                            expiration_date,
                            days_to_expiration,
                            premium_option_price,
                            intrinsic_value,
                            extrinsic_value,
                            moneyness,
                            live_stock_price,
                            strike,
                            classification,
                            "Payouts/-Year",
                            "Current-Div",
                            option_open_interest,
                            CAST(
                                ROUND(("Payouts/-Year" * (days_to_expiration / 365.0))) AS INTEGER
                            ) AS dividend_count,
                            ROUND(
                                ("Payouts/-Year" * (days_to_expiration / 365.0)) * "Current-Div",
                                2
                            ) AS dividend_sum_per_option,
                            ROUND(
                                ("Payouts/-Year" * (days_to_expiration / 365.0)) * "Current-Div",
                                2
                            ) * 100 AS dividend_sum
                        FROM
                            OptionDataMerged
                        where
                            "option-type" = 'put'
                            --and classification = 'Champions'
                            and strike > live_stock_price * 1.2
                    )
            )
    )
where
    extrinsic_value > 0
    and option_open_interest > 0
Order by
    roi_annualized_pct DESC;