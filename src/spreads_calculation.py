import pandas as pd
import logging
import os
from typing import Dict, Any
from src.decorator_log_function import log_function
from src.options_utils import (
    MULTIPLIER,
    calculate_apdi,
    create_earnings_warning,
    format_strike,
    format_expiration_date,
    calculate_expected_value
)

# Setup logging
logger = logging.getLogger(os.path.basename(__file__))

def _calculate_expected_value_for_symbol(row: pd.Series, strategy_type: str = 'credit', iv_correction: str = 'auto') -> Dict[str, Any]:
    """Calculates the Expected Value and IV details for a single spread using Monte Carlo simulation."""
    is_credit = strategy_type == 'credit'
    
    options = [
        {
            'strike': row['sell_strike'],
            'premium': row['sell_last_option_price'],
            'is_call': row['option_type'] == 'call',
            'is_long': not is_credit  # In Debit Spread, the "sell" side from SQL is actually the bought one if we follow the naming
        },
        {
            'strike': row['buy_strike'],
            'premium': row['buy_last_option_price'],
            'is_call': row['option_type'] == 'call',
            'is_long': is_credit
        }
    ]

    return calculate_expected_value(
        current_price=row['close'],
        dte=row['days_to_expiration'],
        volatility=row['sell_iv'],
        options=options,
        iv_correction=iv_correction,
        return_details=True
    )

def _calculate_spread_metrics(df: pd.DataFrame, strategy_type: str = 'credit', iv_correction: str = 'auto') -> pd.DataFrame:
    """Calculates all relevant metrics for the spreads."""
    if df.empty:
        return df

    # Spread Width
    df["spread_width"] = (df['sell_strike'] - df['buy_strike']).abs()

    # Max Profit & Max Loss (BPR usually represents max loss for credit, but we clarify)
    if strategy_type == 'credit':
        # Credit Spread: Premium received
        df["max_profit"] = MULTIPLIER * (df["sell_last_option_price"] - df["buy_last_option_price"])
        # Buying Power Reduction (BPR) / Max Risk
        df["bpr"] = df["spread_width"] * MULTIPLIER - df["max_profit"]
    else:
        # Debit Spread: Premium paid
        # In Debit spreads, sell_strike is long and buy_strike is short
        # Net Debit = Long Price - Short Price
        df["max_loss"] = MULTIPLIER * (df["sell_last_option_price"] - df["buy_last_option_price"])
        df["max_profit"] = (df["spread_width"] * MULTIPLIER) - df["max_loss"]
        df["bpr"] = df["max_loss"]
    
    # Filter out negative profit spreads
    df = df[df['max_profit'] > 0].copy()
    if df.empty:
        return df

    # Filter out negative BPR spreads
    df = df[df['bpr'] > 0].copy()
    if df.empty:
        return df

    # Profit to BPR ratio
    df["profit_to_bpr"] = df["max_profit"] / df["bpr"]

    # Spread Theta
    if strategy_type == 'credit':
        df["spread_theta"] = df["sell_theta"].fillna(0) - df["buy_theta"].fillna(0)
    else:
        # In Debit spreads, sell_strike is the LONG leg (closer to money), buy_strike is SHORT leg (further)
        # Total Theta = Theta(Long) + Theta(Short)
        # Long Theta is negative (time decay hurts), Short Theta is positive (time decay helps)
        # In our SQL: sell_theta is from the long leg, buy_theta is from the short leg.
        # So it should be: sell_theta (negative) + (-buy_theta) ? 
        # Actually, option greeks in data are usually signed (negative for puts/calls theta).
        # Short position flips the sign of the greek.
        # Long Theta = sell_theta
        # Short Theta = -buy_theta
        df["spread_theta"] = df["sell_theta"].fillna(0) - df["buy_theta"].fillna(0)

    # % Out-of-the-Money (OTM)
    df["%_otm"] = (df["sell_strike"] - df["close"]).abs() / df["close"] * 100

    # Expected Value and IV Details
    ev_results = df.apply(lambda r: _calculate_expected_value_for_symbol(r, strategy_type, iv_correction=iv_correction), axis=1)
    df["expected_value"] = ev_results.apply(lambda x: x["expected_value"])
    df["iv_correction_factor"] = ev_results.apply(lambda x: x["iv_correction_factor"])

    # APDI
    df["APDI"] = df.apply(lambda r: calculate_apdi(r["max_profit"], r["days_to_expiration"], r["bpr"]), axis=1)
    df["APDI_EV"] = df.apply(lambda r: calculate_apdi(r["expected_value"], r["days_to_expiration"], r["bpr"]), axis=1)

    # Ensure Company name is handled correctly
    if 'Company' in df.columns:
        df["Company"] = df["Company"].replace("", None).fillna(df["symbol"])
    else:
        df["Company"] = df["symbol"]

    return df

def _add_earnings_and_urls(df: pd.DataFrame, strategy_type: str = 'credit') -> pd.DataFrame:
    """Adds earnings warnings and OptionStrat URLs."""
    if df.empty:
        return df

    df['earnings_date'] = pd.to_datetime(df['earnings_date'], errors='coerce')
    df['expiration_date'] = pd.to_datetime(df['expiration_date'], errors='coerce')

    df['earnings_warning'] = df.apply(
        lambda r: create_earnings_warning(r['earnings_date'], r['expiration_date']), 
        axis=1
    )
    df['optionstrat_url'] = df.apply(lambda r: _build_optionstrat_url(r, strategy_type), axis=1)

    return df

def _build_optionstrat_url(row: pd.Series, strategy_type: str = 'credit') -> str:
    """Builds an OptionStrat URL for the spread."""
    base_url = "https://optionstrat.com/build"
    symbol = row['symbol'].upper()
    date_str = format_expiration_date(row['expiration_date'])
    opt_type = row['option_type'].lower()
    
    if strategy_type == 'credit':
        if opt_type == 'put':
            strategy = 'bull-put-spread'
            lower_strike = min(row['sell_strike'], row['buy_strike'])
            higher_strike = max(row['sell_strike'], row['buy_strike'])
            options = f".{symbol}{date_str}P{format_strike(lower_strike)},-.{symbol}{date_str}P{format_strike(higher_strike)}"
        else:
            strategy = 'bear-call-spread'
            lower_strike = min(row['sell_strike'], row['buy_strike'])
            higher_strike = max(row['sell_strike'], row['buy_strike'])
            options = f"-.{symbol}{date_str}C{format_strike(lower_strike)},.{symbol}{date_str}C{format_strike(higher_strike)}"
    else:
        # Debit Spreads
        if opt_type == 'call':
            strategy = 'bull-call-spread'
            # SQL: sell_strike is the closer ITM (buy), buy_strike is further OTM (sell)
            options = f".{symbol}{date_str}C{format_strike(row['sell_strike'])},-.{symbol}{date_str}C{format_strike(row['buy_strike'])}"
        else:
            strategy = 'bear-put-spread'
            options = f".{symbol}{date_str}P{format_strike(row['sell_strike'])},-.{symbol}{date_str}P{format_strike(row['buy_strike'])}"
        
    return f"{base_url}/{strategy}/{symbol}/{options}"

@log_function
def calc_spreads(df: pd.DataFrame, strategy_type: str = 'credit', iv_correction: str = 'auto') -> pd.DataFrame:
    """Main calculation entry point for spreads."""
    if df.empty:
        return df
    
    df = _calculate_spread_metrics(df, strategy_type, iv_correction=iv_correction)
    df = _add_earnings_and_urls(df, strategy_type)
    
    return df

def get_page_spreads(df: pd.DataFrame, strategy_type: str = 'credit', iv_correction: str = 'auto') -> pd.DataFrame:
    """Prepares the DataFrame for display in the frontend."""
    if df.empty:
        return df
        
    df = calc_spreads(df, strategy_type, iv_correction=iv_correction)
    
    if df.empty:
        return df

    columns = [
        'symbol', 'Company', 'earnings_date', 'earnings_warning', 'close', 
        'analyst_mean_target', 'company_industry', 'company_sector', 
        'historical_volatility_30d', 'iv_rank', 'iv_percentile',
        'spread_width', 'max_profit', 'bpr', 'profit_to_bpr', 'spread_theta', 
        'expected_value', 'iv_correction_factor', 'APDI', 'APDI_EV', 'optionstrat_url',
        'sell_strike', 'sell_last_option_price', 'sell_delta', 'sell_iv', '%_otm', 
        'sell_theta', 'sell_open_interest', 'sell_expected_move', 'sell_day_volume',
        'buy_strike', 'buy_last_option_price', 'buy_delta', 'buy_iv', 'buy_theta', 
        'buy_open_interest', 'buy_expected_move', 'buy_day_volume',
        'option_type', 'expiration_date', 'days_to_expiration', 'days_to_earnings'
    ]
    
    existing_columns = [col for col in columns if col in df.columns]
    return df[existing_columns]

if __name__ == "__main__":
    """
     Keep the main for testing purposes
     """

    import time
    import logging
    from src.logger_config import setup_logging
    from src.database import select_into_dataframe

    # enable logging
    setup_logging(component="script_spreads_calculation", log_level=logging.DEBUG, console_output=True)
    logger = logging.getLogger(__name__)
    logger.info(f"Start {__name__} ({__file__})")

    params = {
        "expiration_date": "2026-02-20",
        "option_type": "put",
        "delta_target": 0.2,
        "spread_width": 5,
        "min_open_interest": 100
    }


    # test query. ensure to use the running query in the production code as well :D
    sql_query = """
    WITH FilteredOptions AS (
        SELECT
            symbol,
            expiration_date,
            contract_type AS option_type,
            strike_price AS strike,
            day_close AS last_option_price,
            abs(greeks_delta) AS delta,
            implied_volatility AS iv,
            greeks_theta AS theta,
            close,
            earnings_date,
            days_to_expiration,
            days_to_earnings,
            open_interest AS option_open_interest,
            expected_move,
            ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY abs(greeks_delta) DESC) AS row_num,
            analyst_mean_target,
            recommendation
        FROM
            "OptionDataMerged"
        WHERE
            expiration_date = :expiration_date
            AND contract_type = :option_type
            AND abs(greeks_delta) <= :delta_target
            AND open_interest >= :min_open_interest
    ),
    
    SelectedSellOptions AS (
        SELECT
            symbol,
            strike AS sell_strike,
            expiration_date,
            option_type,
            last_option_price AS sell_last_option_price,
            delta AS sell_delta,
            iv AS sell_iv,
            theta AS sell_theta,
            close AS sell_close,
            earnings_date,
            days_to_expiration,
            days_to_earnings,
            option_open_interest AS sell_open_interest,
            expected_move AS sell_expected_move,
            analyst_mean_target,
            recommendation
        FROM
            FilteredOptions
        WHERE
            row_num = 1
    )
    
    --spread data
    SELECT
        -- sell option
        sell.symbol,
        sell.expiration_date,
        sell.option_type,
        sell.sell_close AS close,
        sell.earnings_date,
        sell.days_to_expiration,
        sell.days_to_earnings,
        sell.sell_strike,
        sell.sell_last_option_price,
        sell.sell_delta,
        sell.sell_iv,
        sell.sell_theta,
        sell.sell_open_interest,
        sell.sell_expected_move,
        sell.analyst_mean_target,
        sell.recommendation,
        -- buy option
        buy.strike               AS buy_strike,
        buy.last_option_price    AS buy_last_option_price,
        buy.delta                AS buy_delta,
        buy.iv                   AS buy_iv,
        buy.theta                AS buy_theta,
        buy.option_open_interest AS buy_open_interest,
        buy.expected_move        AS buy_expected_move
    FROM
        SelectedSellOptions sell
    INNER JOIN
        FilteredOptions buy
        ON sell.symbol = buy.symbol
        AND buy.strike = (
            CASE
                WHEN sell.option_type = 'put' THEN sell.sell_strike - :spread_width
                WHEN sell.option_type = 'call' THEN sell.sell_strike + :spread_width
            END
        );

    """

    start = time.time()
    df = select_into_dataframe(query=sql_query, params=params)

    if df.empty:
        raise ValueError("Input DataFrame ist leer - keine Optionsdaten vorhanden")

    df = get_page_spreads(df)
    ende = time.time()

    print(df.head())
    print(df.shape)
    print(f"Runtime: {ende - start:.6f} seconds")
    pass