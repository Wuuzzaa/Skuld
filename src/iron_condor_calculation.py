import pandas as pd
from config import NUM_SIMULATIONS, RANDOM_SEED, RISK_FREE_RATE
from src.decorator_log_function import log_function
from src.monte_carlo_simulation import UniversalOptionsMonteCarloSimulator

# Constants
MULTIPLIER = 100
EARNINGS_WARNING_DAYS = 7
DIVIDEND_YIELD = 0

def _calculate_combined_ev(row: pd.Series) -> float:
    """
    Calculates the combined Expected Value for an Iron Condor using Monte Carlo simulation.
    Processes 4 legs: Short Put, Long Put, Short Call, Long Call.
    """
    # Use the IV of one of the short options as a proxy for the strategy IV
    volatility = row['sell_iv_put'] 
    
    monte_carlo_simulator = UniversalOptionsMonteCarloSimulator(
        num_simulations=NUM_SIMULATIONS,
        random_seed=RANDOM_SEED,
        current_price=row['close_put'],
        dte=max(row['days_to_expiration_put'], row['days_to_expiration_call']),
        volatility=volatility,
        risk_free_rate=RISK_FREE_RATE,
        dividend_yield=DIVIDEND_YIELD,
    )

    options = [
        # Put side
        {'strike': row['sell_strike_put'], 'premium': row['sell_last_option_price_put'], 'is_call': False, 'is_long': False},
        {'strike': row['buy_strike_put'], 'premium': row['buy_last_option_price_put'], 'is_call': False, 'is_long': True},
        # Call side
        {'strike': row['sell_strike_call'], 'premium': row['sell_last_option_price_call'], 'is_call': True, 'is_long': False},
        {'strike': row['buy_strike_call'], 'premium': row['buy_last_option_price_call'], 'is_call': True, 'is_long': True},
    ]

    return monte_carlo_simulator.calculate_expected_value(options=options)

def _calculate_iron_condor_metrics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    # Combined Max Profit
    df["max_profit"] = MULTIPLIER * (
        (df["sell_last_option_price_put"] - df["buy_last_option_price_put"]) +
        (df["sell_last_option_price_call"] - df["buy_last_option_price_call"])
    )

    # Buying Power Reduction (BPR)
    df["width_put"] = (df["sell_strike_put"] - df["buy_strike_put"]).abs()
    df["width_call"] = (df["buy_strike_call"] - df["sell_strike_call"]).abs()
    df["bpr"] = df[["width_put", "width_call"]].max(axis=1) * MULTIPLIER - df["max_profit"]

    # Spread Theta
    df["combined_theta"] = (df["sell_theta_put"] - df["buy_theta_put"]) + (df["sell_theta_call"] - df["buy_theta_call"])

    # Expected Value
    df["expected_value"] = df.apply(_calculate_combined_ev, axis=1)

    # APDI
    df["max_dte"] = df[["days_to_expiration_put", "days_to_expiration_call"]].max(axis=1)
    df["APDI"] = (df["max_profit"] / df["max_dte"] / df["bpr"]) * 36500
    df["APDI_EV"] = (df["expected_value"] / df["max_dte"] / df["bpr"]) * 36500

    return df

def _add_earnings_and_urls(df: pd.DataFrame) -> pd.DataFrame:
    df['earnings_date'] = pd.to_datetime(df['earnings_date_put'], errors='coerce')
    df['expiration_date_put'] = pd.to_datetime(df['expiration_date_put'], errors='coerce')
    df['expiration_date_call'] = pd.to_datetime(df['expiration_date_call'], errors='coerce')

    df['earnings_warning'] = df.apply(_create_earnings_warning, axis=1)
    df['optionstrat_url'] = df.apply(_build_optionstrat_url, axis=1)

    return df

def _create_earnings_warning(row: pd.Series) -> str:
    earliest_exp = pd.to_datetime(min(row['expiration_date_put'], row['expiration_date_call']))
    if (pd.notna(row['earnings_date']) and pd.notna(earliest_exp) and row['earnings_date'] > pd.Timestamp.now()):
        days_before_expiration = (earliest_exp - row['earnings_date']).days
        if 0 <= days_before_expiration <= EARNINGS_WARNING_DAYS:
            return f'⚠️ {days_before_expiration} days'
    return ''

def _build_optionstrat_url(row: pd.Series) -> str:
    base_url = "https://optionstrat.com/build/iron-condor"
    symbol = row['symbol'].upper()
    
    def fmt_date(d): return pd.to_datetime(d).strftime('%y%m%d')
    def fmt_strike(s): return str(int(s)) if s == int(s) else str(s)
    
    p_buy = f".{symbol}{fmt_date(row['expiration_date_put'])}P{fmt_strike(row['buy_strike_put'])}"
    p_sell = f"-.{symbol}{fmt_date(row['expiration_date_put'])}P{fmt_strike(row['sell_strike_put'])}"
    c_sell = f"-.{symbol}{fmt_date(row['expiration_date_call'])}C{fmt_strike(row['sell_strike_call'])}"
    c_buy = f".{symbol}{fmt_date(row['expiration_date_call'])}C{fmt_strike(row['buy_strike_call'])}"
    
    return f"{base_url}/{symbol}/{p_buy},{p_sell},{c_sell},{c_buy}"

@log_function
def calc_iron_condors(put_spreads: pd.DataFrame, call_spreads: pd.DataFrame) -> pd.DataFrame:
    if put_spreads.empty or call_spreads.empty:
        return pd.DataFrame()

    combined = put_spreads.merge(
        call_spreads,
        on="symbol",
        suffixes=("_put", "_call")
    )

    if combined.empty:
        return combined

    combined = _calculate_iron_condor_metrics(combined)
    combined = _add_earnings_and_urls(combined)

    return combined

def get_page_iron_condors(put_spreads: pd.DataFrame, call_spreads: pd.DataFrame) -> pd.DataFrame:
    df = calc_iron_condors(put_spreads, call_spreads)
    if df.empty:
        return df

    columns = [
        'symbol',
        'earnings_date',
        'earnings_warning',
        'close_put',
        'analyst_mean_target_put',
        'company_industry_put',
        'company_sector_put',
        'iv_rank_put',
        'iv_percentile_put',
        'sell_strike_put',
        'buy_strike_put',
        'sell_strike_call',
        'buy_strike_call',
        'sell_delta_put',
        'sell_delta_call',
        'expiration_date_put',
        'expiration_date_call',
        'max_profit',
        'bpr',
        'expected_value',
        'APDI',
        'APDI_EV',
        'optionstrat_url'
    ]
    
    display_map = {
        'close_put': 'close',
        'analyst_mean_target_put': 'analyst_target',
        'company_industry_put': 'industry',
        'company_sector_put': 'sector',
        'iv_rank_put': 'iv_rank',
        'iv_percentile_put': 'iv_percentile'
    }
    
    return df[columns].rename(columns=display_map)