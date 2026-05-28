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
    calculate_expected_value,
    OptionLeg,
    calculate_strategy_metrics
)
from src.black_scholes import CallValue, PutValue
from config import RISK_FREE_RATE

# Setup logging
logger = logging.getLogger(os.path.basename(__file__))

def _calculate_metrics_for_row(row: pd.Series, strategy_type: str = 'credit', iv_correction: str = 'auto') -> pd.Series:
    """Calculates all metrics for a single spread using the generic calculator."""
    is_credit = strategy_type == 'credit'
    
    legs = [
        OptionLeg(
            strike=row['sell_strike'],
            premium=row['sell_last_option_price'],
            is_call=row['option_type'] == 'call',
            is_long=not is_credit,
            theta=row.get('sell_theta'),
            oi=row.get('sell_open_interest'),
            volume=row.get('sell_day_volume'),
            expected_move=row.get('sell_expected_move'),
            last_updated_massive=row.get('sell_last_updated'),
            last_updated_option_data=row.get('last_updated_option_data'),
            last_updated_stock_data=row.get('last_updated_stock_data')
        ),
        OptionLeg(
            strike=row['buy_strike'],
            premium=row['buy_last_option_price'],
            is_call=row['option_type'] == 'call',
            is_long=is_credit,
            theta=row.get('buy_theta'),
            oi=row.get('buy_open_interest'),
            volume=row.get('buy_day_volume'),
            expected_move=row.get('buy_expected_move'),
            last_updated_massive=row.get('buy_last_updated'),
            last_updated_option_data=row.get('last_updated_option_data'),
            last_updated_stock_data=row.get('last_updated_stock_data')
        )
    ]

    metrics = calculate_strategy_metrics(
        current_price=row['close'],
        dte=row['days_to_expiration'],
        volatility=row['sell_iv'],
        legs=legs,
        iv_correction=iv_correction
    )
    
    return pd.Series({
        "max_profit": metrics.max_profit,
        "max_loss": metrics.max_loss,
        "bpr": metrics.bpr,
        "expected_value": metrics.expected_value,
        "spread_theta": metrics.total_theta,
        "profit_to_bpr": metrics.profit_to_bpr,
        "APDI": metrics.apdi,
        "APDI_EV": metrics.apdi_ev,
        "iv_correction_factor": metrics.iv_correction_factor,
        "corrected_volatility": metrics.corrected_volatility
    })

def _calculate_bs_price(S, K, sigma, t, r, is_call):
    """Central BS price calculation for a single option leg."""
    try:
        if pd.isna(S) or pd.isna(K) or pd.isna(sigma) or pd.isna(t) or sigma <= 0 or t <= 0:
            return None
        if is_call:
            return round(CallValue(S, K, sigma, t, r), 2)
        else:
            return round(PutValue(S, K, sigma, t, r), 2)
    except Exception:
        return None


def _calculate_spread_metrics(df: pd.DataFrame, strategy_type: str = 'credit', iv_correction: str = 'auto', risk_free_rate: float = RISK_FREE_RATE) -> pd.DataFrame:
    """Calculates all relevant metrics for the spreads."""
    if df.empty:
        return df

    # Spread Width
    df["spread_width"] = (df['sell_strike'] - df['buy_strike']).abs()

    # % Out-of-the-Money (OTM)
    df["%_otm"] = (df["sell_strike"] - df["close"]).abs() / df["close"] * 100

    # Black-Scholes theoretical prices
    is_call = df['option_type'] == 'call'
    df['sell_bs_price'] = df.apply(
        lambda r: _calculate_bs_price(r['close'], r['sell_strike'], r['sell_iv'], r['days_to_expiration'], risk_free_rate, r['option_type'] == 'call'), axis=1)
    df['buy_bs_price'] = df.apply(
        lambda r: _calculate_bs_price(r['close'], r['buy_strike'], r['buy_iv'], r['days_to_expiration'], risk_free_rate, r['option_type'] == 'call'), axis=1)

    # Calculate all generic metrics
    metrics_df = df.apply(lambda r: _calculate_metrics_for_row(r, strategy_type, iv_correction=iv_correction), axis=1)
    df = pd.concat([df, metrics_df], axis=1)

    # Filter out invalid spreads
    df = df[df['max_profit'] > 0].copy()
    df = df[df['bpr'] > 0].copy()

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
def calc_spreads(df: pd.DataFrame, strategy_type: str = 'credit', iv_correction: str = 'auto', risk_free_rate: float = RISK_FREE_RATE) -> pd.DataFrame:
    """Main calculation entry point for spreads."""
    if df.empty:
        return df

    df = _calculate_spread_metrics(df, strategy_type, iv_correction=iv_correction, risk_free_rate=risk_free_rate)
    df = _add_earnings_and_urls(df, strategy_type)

    return df

def get_page_spreads(df: pd.DataFrame, strategy_type: str = 'credit', iv_correction: str = 'auto', risk_free_rate: float = RISK_FREE_RATE) -> pd.DataFrame:
    """Prepares the DataFrame for display in the frontend."""
    if df.empty:
        return df

    df = calc_spreads(df, strategy_type, iv_correction=iv_correction, risk_free_rate=risk_free_rate)
    
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
        'sell_last_updated', 'sell_bs_price',
        'buy_strike', 'buy_last_option_price', 'buy_delta', 'buy_iv', 'buy_theta',
        'buy_open_interest', 'buy_expected_move', 'buy_day_volume',
        'buy_last_updated', 'buy_bs_price',
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
        "expiration_date": "2026-07-17",
        "option_type": "put",
        "delta_target": 0.2,
        "spread_width": 5,
        "min_open_interest": 0,
        "min_day_volume": 0,
        "min_iv_rank": 0,
        "min_iv_percentile":0,
        "strategy_type": "credit",
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
        LIVE_STOCK_PRICE AS close,
        earnings_date,
        days_to_expiration,
        days_to_earnings,
        open_interest AS option_open_interest,
        expected_move,
        analyst_mean_target,
        day_volume,
        company_name,
        company_industry,
        company_sector,
        historical_volatility_30d,
        iv_rank,
        iv_percentile
    FROM
        "OptionDataMerged"
    WHERE
        open_interest >= :min_open_interest
        AND day_volume >= :min_day_volume
        AND iv_rank >= :min_iv_rank
        AND iv_percentile >= :min_iv_percentile
),

TargetOptions AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY symbol, expiration_date, option_type
            ORDER BY abs(delta - :delta_target) ASC
        ) as delta_rank
    FROM
        FilteredOptions
    WHERE
        expiration_date = :expiration_date
        AND option_type = :option_type
)

SELECT
    -- symbol data
    sell.symbol,
    sell.expiration_date,
    sell.option_type,
    sell.close,
    sell.earnings_date,
    sell.company_name AS "Company",
    sell.days_to_expiration,
    sell.days_to_earnings,
    sell.analyst_mean_target,
    sell.company_industry,
    sell.company_sector,
    sell.historical_volatility_30d,
    sell.iv_rank,
    sell.iv_percentile,
    -- sell option
    sell.strike AS sell_strike,
    sell.last_option_price AS sell_last_option_price,
    sell.delta AS sell_delta,
    sell.iv AS sell_iv,
    sell.theta AS sell_theta,
    sell.option_open_interest AS sell_open_interest,
    sell.expected_move AS sell_expected_move,
    sell.day_volume AS sell_day_volume,
    -- buy option
    buy.strike AS buy_strike,
    buy.last_option_price AS buy_last_option_price,
    buy.delta AS buy_delta,
    buy.iv AS buy_iv,
    buy.theta AS buy_theta,
    buy.option_open_interest AS buy_open_interest,
    buy.expected_move AS buy_expected_move,
    buy.day_volume AS buy_day_volume
FROM
    TargetOptions sell
INNER JOIN
    FilteredOptions buy
    ON sell.symbol = buy.symbol
    AND sell.expiration_date = buy.expiration_date
    AND sell.option_type = buy.option_type
    AND buy.strike = (
        CASE
            WHEN :strategy_type = 'credit' THEN 
                CASE
                    WHEN sell.option_type = 'put' THEN sell.strike - :spread_width
                    WHEN sell.option_type = 'call' THEN sell.strike + :spread_width
                END
            WHEN :strategy_type = 'debit' THEN
                CASE
                    WHEN sell.option_type = 'put' THEN sell.strike + :spread_width
                    WHEN sell.option_type = 'call' THEN sell.strike - :spread_width
                END
        END
    )
WHERE
    sell.delta_rank = 1;

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