import pandas as pd
from datetime import datetime
from typing import Tuple, Dict, Any
from config import NUM_SIMULATIONS, RANDOM_SEED, RISK_FREE_RATE, PATH_LOG_FILE
from src.decorator_log_function import log_function
from src.monte_carlo_simulation import UniversalOptionsMonteCarloSimulator

# Constants
MULTIPLIER = 100
EARNINGS_WARNING_DAYS = 7
DIVIDEND_YIELD = 0  # TODO: Insert the dividend from the symbol here

# Column name constants
COL_SYMBOL = 'symbol'
COL_CLOSE = 'close'
COL_STRIKE = 'strike'
COL_OPTION_TYPE = 'option-type'
COL_DELTA = 'delta'
COL_PUTS = 'puts'
COL_CALLS = 'calls'


def _calculate_expected_value_for_symbol(row: pd.Series) -> float:
    """
    Calculate the expected value for an options spread using Monte Carlo simulation.

    Args:
        row: DataFrame row containing options spread data

    Returns:
        Expected value of the spread
    """
    monte_carlo_simulator = UniversalOptionsMonteCarloSimulator(
        num_simulations=NUM_SIMULATIONS,
        random_seed=RANDOM_SEED,
        current_price=row['close'],
        dte=row['days_to_expiration_sell'],
        volatility=row['iv_sell'],
        risk_free_rate=RISK_FREE_RATE,
        dividend_yield=DIVIDEND_YIELD,
    )

    options = [
        _create_option_config(row, is_sell=True),
        _create_option_config(row, is_sell=False)
    ]

    return monte_carlo_simulator.calculate_expected_value(options=options)


def _create_option_config(row: pd.Series, is_sell: bool) -> Dict[str, Any]:
    """
    Create option configuration dictionary for Monte Carlo simulation.

    Args:
        row: DataFrame row containing options spread data
        is_sell: True for sell option, False for buy option

    Returns:
        Dictionary with option configuration
    """
    suffix = '_sell' if is_sell else '_buy'
    return {
        'strike': row[f'strike{suffix}'],
        'premium': row[f'mid{suffix}'],
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
    """
    Calculate all spread metrics and add derived columns.

    Args:
        spreads: DataFrame containing merged put and call spreads

    Returns:
        DataFrame with calculated metrics
    """
    # Copy sell columns to standardized names
    spreads["expected_move"] = spreads["expected_move_sell"]
    spreads["ivr"] = spreads["iv_rank_sell"]
    spreads["ivp"] = spreads["iv_percentile_sell"]
    spreads["open_intrest"] = spreads["option_open_interest_sell"]
    spreads["earnings_date"] = spreads['earnings_date_sell']
    spreads['option_type'] = spreads['option-type_sell']

    # Calculate spread width
    spreads["spread_width"] = abs(spreads['strike_sell'] - spreads['strike_buy'])

    # Calculate max profit
    spreads["max_profit"] = MULTIPLIER * (spreads["bid_sell"] - spreads["ask_buy"])

    # Remove spreads without profit potential
    spreads = spreads[spreads['max_profit'] > 0].reset_index(drop=True)

    # Calculate buying power reduction (BPR)
    spreads["bpr"] = spreads["spread_width"] * MULTIPLIER - spreads["max_profit"]

    # Remove spreads with negative BPR
    spreads = spreads[spreads['bpr'] > 0].reset_index(drop=True)

    # Calculate profit-to-BPR ratio
    spreads["profit_to_bpr"] = spreads["max_profit"] / spreads["bpr"]

    # Calculate spread theta
    spreads["spread_theta"] = spreads["theta_sell"] - spreads["theta_buy"]

    return spreads


def _add_earnings_and_urls(spreads: pd.DataFrame) -> pd.DataFrame:
    """
    Add earnings warnings and OptionStrat URLs to the spreads DataFrame.

    Args:
        spreads: DataFrame containing spread data

    Returns:
        DataFrame with earnings warnings and URLs added
    """
    # Convert date fields to datetime
    spreads['earnings_date_sell'] = pd.to_datetime(
        spreads['earnings_date_sell'],
        errors='coerce'
    )
    spreads['expiration_date_sell'] = pd.to_datetime(
        spreads['expiration_date_sell'],
        errors='coerce'
    )

    # Add earnings warning
    spreads['earnings_warning'] = spreads.apply(_create_earnings_warning, axis=1)

    # Generate OptionStrat URLs
    spreads['optionstrat_url'] = spreads.apply(_build_optionstrat_url, axis=1)

    return spreads


def _create_earnings_warning(row: pd.Series) -> str:
    """
    Create an earnings warning if earnings occur within EARNINGS_WARNING_DAYS
    days before expiration.

    Args:
        row: DataFrame row containing earnings and expiration dates

    Returns:
        Warning string or empty string
    """
    if (pd.notna(row['earnings_date_sell']) and
            pd.notna(row['expiration_date_sell']) and
            row['earnings_date_sell'] > pd.Timestamp.now()):

        days_before_expiration = (
                row['expiration_date_sell'] - row['earnings_date_sell']
        ).days

        # Warning only if earnings are before expiration and within warning period
        if 0 <= days_before_expiration <= EARNINGS_WARNING_DAYS:
            return f'⚠️ {days_before_expiration} days'

    return ''


@log_function
def calc_spreads(
        df: pd.DataFrame,
        delta_target: float,
        spread_width: float
) -> pd.DataFrame:
    """
    Calculate option spreads based on delta target and spread width.

    Workflow:
    1. Select sell options via delta target
    2. Select buy options via spread width
    3. Calculate spread metrics and expected values
    4. Add earnings warnings and URLs

    Args:
        df: DataFrame containing options data
        delta_target: Target delta for sell options (e.g., 0.30)
        spread_width: Width of the spread in dollars (e.g., 5.0)

    Returns:
        DataFrame containing calculated spreads with relevant columns
    """
    # Step 1: Select sell options by delta
    sell_puts, sell_calls = _get_sell_options_by_delta_target(df, delta_target)

    # Step 2: Add buy options based on spread width
    puts, calls = _add_buy_options(df, sell_puts, sell_calls, spread_width)

    # Step 3: Merge puts and calls
    assert list(puts.columns) == list(calls.columns), \
        "Columns of puts and calls do not match!"

    spreads = pd.concat([puts, calls], ignore_index=True)

    # Clear memory
    del puts, calls, sell_puts, sell_calls

    # Remove symbols without matching buy strike
    spreads = spreads.dropna(subset=['strike_buy'])

    # Step 4: Calculate spread metrics
    spreads = _calculate_spread_metrics(spreads)

    # Step 5: Calculate expected value (computationally expensive)
    spreads["expected_value"] = spreads.apply(
        _calculate_expected_value_for_symbol,
        axis=1
    )

    # Step 6: Add earnings warnings and URLs
    spreads = _add_earnings_and_urls(spreads)

    # Step 7: Select relevant columns for output
    output_columns = [
        'symbol',
        'earnings_date',
        'earnings_warning',
        'ivr',
        'ivp',
        'open_intrest',
        'close',
        'option_type',
        'strike_sell',
        'bid_sell',
        'delta_sell',
        'iv_sell',
        'strike_buy',
        'ask_buy',
        'max_profit',
        'bpr',
        'profit_to_bpr',
        'expected_move',
        'expected_value',
        'optionstrat_url',
    ]

    return spreads[output_columns]


def _build_optionstrat_url(row: pd.Series) -> str:
    """
    Build an OptionStrat URL for the given spread.

    Works for both Bull Put Spreads and Bear Call Spreads.

    Args:
        row: DataFrame row containing spread information

    Returns:
        Complete OptionStrat URL as string

    Examples:
        Bull Put: https://optionstrat.com/build/bull-put-spread/KO/.KO260220P57.5,-.KO260220P70
        Bear Call: https://optionstrat.com/build/bear-call-spread/KO/-.KO260220C57.5,.KO260220C70
    """
    base_url = "https://optionstrat.com/build"

    symbol = row['symbol'].upper()
    date_str = _format_expiration_date(row['expiration_date_sell'])
    opt_type_str = row['option-type_sell'].lower()

    if opt_type_str == COL_PUTS:
        strategy = 'bull-put-spread'
        options_string = _build_put_spread_options(row, symbol, date_str)
    else:  # calls
        strategy = 'bear-call-spread'
        options_string = _build_call_spread_options(row, symbol, date_str)

    return f"{base_url}/{strategy}/{symbol}/{options_string}"


def _format_expiration_date(exp_date: Any) -> str:
    """
    Format expiration date to YYMMDD string.

    Args:
        exp_date: Date as string or datetime object

    Returns:
        Formatted date string (YYMMDD)
    """
    if isinstance(exp_date, str):
        exp_date = datetime.strptime(exp_date, '%Y-%m-%d')

    return exp_date.strftime('%y%m%d')


def _format_strike(strike: float) -> str:
    """
    Format strike price, removing unnecessary decimals.

    Args:
        strike: Strike price

    Returns:
        Formatted strike as string (68.0 -> "68", 57.5 -> "57.5")
    """
    return str(int(strike)) if strike == int(strike) else str(strike)


def _build_put_spread_options(row: pd.Series, symbol: str, date_str: str) -> str:
    """
    Build options string for Bull Put Spread.

    Bull Put: Sell LOWER strike, Buy HIGHER strike

    Args:
        row: DataFrame row with strike information
        symbol: Ticker symbol
        date_str: Formatted expiration date

    Returns:
        Options string for URL
    """
    lower_strike = min(row['strike_sell'], row['strike_buy'])
    higher_strike = max(row['strike_sell'], row['strike_buy'])

    first_option = f".{symbol}{date_str}P{_format_strike(lower_strike)}"
    second_option = f"-.{symbol}{date_str}P{_format_strike(higher_strike)}"

    return f"{first_option},{second_option}"


def _build_call_spread_options(row: pd.Series, symbol: str, date_str: str) -> str:
    """
    Build options string for Bear Call Spread.

    Bear Call: Buy LOWER strike, Sell HIGHER strike

    Args:
        row: DataFrame row with strike information
        symbol: Ticker symbol
        date_str: Formatted expiration date

    Returns:
        Options string for URL
    """
    lower_strike = min(row['strike_sell'], row['strike_buy'])
    higher_strike = max(row['strike_sell'], row['strike_buy'])

    first_option = f"-.{symbol}{date_str}C{_format_strike(lower_strike)}"
    second_option = f".{symbol}{date_str}C{_format_strike(higher_strike)}"

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
    setup_logging(log_file=PATH_LOG_FILE, log_level=logging.DEBUG, console_output=True)
    logger = logging.getLogger(__name__)
    logger.info(f"Start {__name__} ({__file__})")

    expiration_date = '2025-11-21'
    delta_target = 0.2
    spread_width = 5

    sql_query = """
    SOME SUPPER NICE QUERY HERE
    """

    start = time.time()
    df = select_into_dataframe(query=sql_query, params={"expiration_date": expiration_date})
    spreads_df = calc_spreads(df, delta_target, spread_width)
    ende = time.time()

    print(spreads_df.head())
    print(spreads_df.shape)
    print(f"Runtime: {ende - start:.6f} seconds")