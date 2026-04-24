import pandas as pd
from typing import Tuple, Dict, Any
from src.decorator_log_function import log_function
from src.options_utils import (
    MULTIPLIER,
    calculate_apdi,
    create_earnings_warning,
    format_strike,
    format_expiration_date,
    calculate_expected_value
)

# Column name constants
COL_SYMBOL = 'symbol'
COL_CLOSE = 'close'
COL_STRIKE = 'strike'
COL_OPTION_TYPE = 'option-type'
COL_DELTA = 'delta'
COL_PUTS = 'put'
COL_CALLS = 'call'


def _calculate_expected_value_for_symbol(row: pd.Series) -> float:
    options = [
        _create_option_config(row, is_sell=True),
        _create_option_config(row, is_sell=False)
    ]

    return calculate_expected_value(
        current_price=row['close'],
        dte=row['days_to_expiration'],
        volatility=row['sell_iv'],
        options=options
    )


def _create_option_config(row: pd.Series, is_sell: bool) -> Dict[str, Any]:
    """
    Create option configuration dictionary for Monte Carlo simulation.

    Args:
        row: DataFrame row containing options spread data
        is_sell: True for sell option, False for buy option

    Returns:
        Dictionary with option configuration
    """
    prefix = 'sell_' if is_sell else 'buy_'
    return {
        'strike': row[f'{prefix}strike'],
        'premium': row[f'{prefix}last_option_price'],
        'is_call': row['option_type'] == COL_CALLS,
        'is_long': not is_sell
    }


def _get_sell_options_by_delta_target(
        df: pd.DataFrame,
        delta_target: float
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Find the sell options (put and call) per symbol by choosing the option
    with the closest delta to the delta_target.

    For puts, the delta_target is automatically inverted to match the
    negative delta values in the data.

    Args:
        df: DataFrame containing options data
        delta_target: Target delta value (positive)

    Returns:
        Tuple of (sell_puts, sell_calls) DataFrames
    """
    # Split into puts and calls
    puts = df[df[COL_OPTION_TYPE] == COL_PUTS].copy()
    calls = df[df[COL_OPTION_TYPE] == COL_CALLS].copy()

    # Invert delta_target for puts because put deltas are negative in the data
    puts["delta_diff"] = (puts[COL_DELTA] - (-delta_target)).abs()
    calls["delta_diff"] = (calls[COL_DELTA] - delta_target).abs()

    # Find the best matching option (smallest delta_diff) per symbol
    sell_puts = puts.loc[puts.groupby(COL_SYMBOL)["delta_diff"].idxmin().dropna()]
    sell_calls = calls.loc[calls.groupby(COL_SYMBOL)["delta_diff"].idxmin().dropna()]

    return sell_puts, sell_calls


def _add_buy_options(
        df: pd.DataFrame,
        sell_puts: pd.DataFrame,
        sell_calls: pd.DataFrame,
        spread_width: float
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Find the long options based on the short options and spread width.

    For puts: strike = sell_strike - spread_width
    For calls: strike = sell_strike + spread_width

    Note: Only perfect matching strikes (+/- spread_width) are selected.

    Args:
        df: DataFrame containing all options data
        sell_puts: DataFrame containing selected sell puts
        sell_calls: DataFrame containing selected sell calls
        spread_width: Width of the spread in dollars

    Returns:
        Tuple of (put_spreads, call_spreads) DataFrames
    """
    puts = df[df[COL_OPTION_TYPE] == COL_PUTS].copy()
    calls = df[df[COL_OPTION_TYPE] == COL_CALLS].copy()

    # Merge for puts
    put_spreads = sell_puts.merge(
        puts,
        how="left",
        left_on=[COL_SYMBOL, COL_CLOSE, sell_puts[COL_STRIKE] - spread_width],
        right_on=[COL_SYMBOL, COL_CLOSE, COL_STRIKE],
        suffixes=("_sell", "_buy")
    )

    # Merge for calls
    call_spreads = sell_calls.merge(
        calls,
        how="left",
        left_on=[COL_SYMBOL, COL_CLOSE, sell_calls[COL_STRIKE] + spread_width],
        right_on=[COL_SYMBOL, COL_CLOSE, COL_STRIKE],
        suffixes=("_sell", "_buy")
    )

    return put_spreads, call_spreads


def _calculate_spread_metrics(spreads: pd.DataFrame) -> pd.DataFrame:
    # Calculate spread width
    spreads["spread_width"] = abs(spreads['sell_strike'] - spreads['buy_strike'])

    # Calculate max profit
    spreads["max_profit"] = MULTIPLIER * (spreads["sell_last_option_price"] - spreads["buy_last_option_price"])

    # Remove spreads without profit potential
    spreads = spreads[spreads['max_profit'] > 0].reset_index(drop=True)

    # Calculate buying power reduction (BPR)
    spreads["bpr"] = spreads["spread_width"] * MULTIPLIER - spreads["max_profit"]

    # Remove spreads with negative BPR
    spreads = spreads[spreads['bpr'] > 0].reset_index(drop=True)

    # Calculate profit-to-BPR ratio
    spreads["profit_to_bpr"] = spreads["max_profit"] / spreads["bpr"]

    # Calculate spread theta
    spreads["spread_theta"] = spreads["sell_theta"] - spreads["buy_theta"]

    # Calculate % Out-of-the-Money (OTM)
    spreads["%_otm"] = abs(spreads["sell_strike"] - spreads["close"]) / spreads["close"] * 100

    # Calculate expected value (computationally expensive)
    spreads["expected_value"] = spreads.apply(
        _calculate_expected_value_for_symbol,
        axis=1
    )

    # Annualized Profit per Dollar Invested
    spreads["APDI"] = spreads.apply(
        lambda r: calculate_apdi(r["max_profit"], r["days_to_expiration"], r["bpr"]),
        axis=1
    )

    # Annualized Profit per Dollar Invested with Expected Value as base instead of max profit
    spreads["APDI_EV"] = spreads.apply(
        lambda r: calculate_apdi(r["expected_value"], r["days_to_expiration"], r["bpr"]),
        axis=1
    )

    return spreads


def _add_earnings_and_urls(spreads: pd.DataFrame) -> pd.DataFrame:
    # Convert date fields to datetime
    spreads['earnings_date'] = pd.to_datetime(
        spreads['earnings_date'],
        errors='coerce'
    )
    spreads['expiration_date'] = pd.to_datetime(
        spreads['expiration_date'],
        errors='coerce'
    )

    # Add earnings warning
    spreads['earnings_warning'] = spreads.apply(
        lambda r: create_earnings_warning(r['earnings_date'], r['expiration_date']), 
        axis=1
    )

    # Generate OptionStrat URLs
    if not spreads.empty:
        spreads['optionstrat_url'] = spreads.apply(_build_optionstrat_url, axis=1)
    else:
        spreads['optionstrat_url'] = []

    return spreads


@log_function
def calc_spreads(
        df: pd.DataFrame,
) -> pd.DataFrame:
    if df.empty:
        raise ValueError("Input DataFrame is empty no data")

    # Calculate spread metrics
    df = _calculate_spread_metrics(df)

    # Add earnings warnings and URLs
    df = _add_earnings_and_urls(df)

    return df

def get_page_spreads(df: pd.DataFrame) -> pd.DataFrame:
    """
    Use this for the Frontend. It calculates the spreads and get rid of not needed columns in the frontend.
    """
    df = calc_spreads(df)

    columns = [
            #############
            # symbol data
            #############
            'symbol',
            'earnings_date',
            'earnings_warning',
            'close',
            'analyst_mean_target',
            # 'recommendation', #todo replace later with own recommendation based on technical indicators
            "company_industry",
            "company_sector",
            "historical_volatility_30d",
            "iv_rank",
            "iv_percentile",
            #'days_to_expiration',
            'days_to_earnings',
            #############
            # sell option data
            #############
            'sell_strike',
            'sell_last_option_price',
            'sell_delta',
            'sell_iv',
            '%_otm',
            #'sell_theta',
            #'sell_open_interest',
            'sell_expected_move',
            "sell_day_volume",
            #############
            # buy option data
            #############
            'buy_strike',
            'buy_last_option_price',
            'buy_delta',
            #'buy_iv',
            #'buy_theta',
            #'buy_open_interest',
            #'buy_expected_move',
            #############
            # spread data
            #############
            #'spread_width',
            'max_profit',
            'bpr',
            'profit_to_bpr',
            #'spread_theta',
            'expected_value',
            'APDI',
            'APDI_EV',
            'optionstrat_url',

            # needed for the ai promt drop later in the page :D
            'option_type',
            'expiration_date',
    ]
    df = df[columns]
    pass


    return df


def _build_optionstrat_url(row: pd.Series) -> str:
    """
    Build an OptionStrat URL for the given spread.
    """
    base_url = "https://optionstrat.com/build"
    symbol = row['symbol'].upper()
    date_str = format_expiration_date(row['expiration_date'])
    opt_type_str = row['option_type'].lower()

    if opt_type_str == COL_PUTS:
        strategy = 'bull-put-spread'
        options_string = _build_put_spread_options(row, symbol, date_str)
    else:  # calls
        strategy = 'bear-call-spread'
        options_string = _build_call_spread_options(row, symbol, date_str)

    return f"{base_url}/{strategy}/{symbol}/{options_string}"


def _build_put_spread_options(row: pd.Series, symbol: str, date_str: str) -> str:
    lower_strike = min(row['sell_strike'], row['buy_strike'])
    higher_strike = max(row['sell_strike'], row['buy_strike'])

    first_option = f".{symbol}{date_str}P{format_strike(lower_strike)}"
    second_option = f"-.{symbol}{date_str}P{format_strike(higher_strike)}"

    return f"{first_option},{second_option}"


def _build_call_spread_options(row: pd.Series, symbol: str, date_str: str) -> str:
    lower_strike = min(row['sell_strike'], row['buy_strike'])
    higher_strike = max(row['sell_strike'], row['buy_strike'])

    first_option = f"-.{symbol}{date_str}C{format_strike(lower_strike)}"
    second_option = f".{symbol}{date_str}C{format_strike(higher_strike)}"

    return f"{first_option},{second_option}"

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