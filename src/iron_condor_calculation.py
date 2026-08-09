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

def _calculate_combined_metrics(row: pd.Series, iv_correction: str = 'auto') -> pd.Series:
    """Calculates all metrics for an Iron Condor using the generic calculator."""
    legs = [
        # Put side
        OptionLeg(
            strike=row['sell_strike_put'], 
            premium=row['sell_last_option_price_put'], 
            is_call=False, 
            is_long=False, 
            theta=row.get('sell_theta_put'),
            oi=row.get('sell_open_interest_put'),
            volume=row.get('sell_day_volume_put'),
            expected_move=row.get('sell_expected_move_put'),
            last_updated_massive=row.get('sell_last_updated_put'),
            last_updated_option_data=row.get('last_updated_option_data'),
            last_updated_stock_data=row.get('last_updated_stock_data')
        ),
        OptionLeg(
            strike=row['buy_strike_put'], 
            premium=row['buy_last_option_price_put'], 
            is_call=False, 
            is_long=True, 
            theta=row.get('buy_theta_put'),
            oi=row.get('buy_open_interest_put'),
            volume=row.get('buy_day_volume_put'),
            expected_move=row.get('buy_expected_move_put'),
            last_updated_massive=row.get('buy_last_updated_put'),
            last_updated_option_data=row.get('last_updated_option_data'),
            last_updated_stock_data=row.get('last_updated_stock_data')
        ),
        # Call side
        OptionLeg(
            strike=row['sell_strike_call'], 
            premium=row['sell_last_option_price_call'], 
            is_call=True, 
            is_long=False, 
            theta=row.get('sell_theta_call'),
            oi=row.get('sell_open_interest_call'),
            volume=row.get('sell_day_volume_call'),
            expected_move=row.get('sell_expected_move_call'),
            last_updated_massive=row.get('sell_last_updated_call'),
            last_updated_option_data=row.get('last_updated_option_data'),
            last_updated_stock_data=row.get('last_updated_stock_data')
        ),
        OptionLeg(
            strike=row['buy_strike_call'], 
            premium=row['buy_last_option_price_call'], 
            is_call=True, 
            is_long=True, 
            theta=row.get('buy_theta_call'),
            oi=row.get('buy_open_interest_call'),
            volume=row.get('buy_day_volume_call'),
            expected_move=row.get('buy_expected_move_call'),
            last_updated_massive=row.get('buy_last_updated_call'),
            last_updated_option_data=row.get('last_updated_option_data'),
            last_updated_stock_data=row.get('last_updated_stock_data')
        ),
    ]

    metrics = calculate_strategy_metrics(
        current_price=row['close_put'],
        dte=max(row['days_to_expiration_put'], row['days_to_expiration_call']),
        volatility=row['sell_iv_put'],
        legs=legs,
        iv_correction=iv_correction
    )

    return pd.Series({
        "max_profit": metrics.max_profit,
        "max_loss": metrics.max_loss,
        "bpr": metrics.bpr,
        "expected_value": metrics.expected_value,
        "total_theta": metrics.total_theta,
        "profit_to_bpr": metrics.profit_to_bpr,
        "APDI": metrics.apdi,
        "APDI_EV": metrics.apdi_ev,
        "iv_correction_factor": metrics.iv_correction_factor,
        "corrected_volatility": metrics.corrected_volatility,
        "sell_iv": (row["sell_iv_put"] + row["sell_iv_call"]) / 2
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


def _calculate_iron_condor_metrics(df: pd.DataFrame, iv_correction: str = 'auto', risk_free_rate: float = RISK_FREE_RATE) -> pd.DataFrame:
    if df.empty:
        return df

    # Clean up column names from merge
    def _safe_assign(target_col, source_col):
        if source_col in df.columns:
            df[target_col] = df[source_col]
        elif target_col not in df.columns:
            df[target_col] = None

    # Check for Company name in both _put and _call suffixes if needed
    if "Company_put" in df.columns:
        df["Company"] = df["Company_put"]
    elif "Company_call" in df.columns:
        df["Company"] = df["Company_call"]
    elif "company_name_put" in df.columns:
        df["Company"] = df["company_name_put"]
    elif "company_name_call" in df.columns:
        df["Company"] = df["company_name_call"]
    elif "Company" not in df.columns:
        df["Company"] = None

    # Fallback to symbol if Company is still N/A or empty
    df["Company"] = df["Company"].replace("", None)
    df["Company"] = df["Company"].fillna(df["symbol"])
    
    _safe_assign("close", "close_put")
    _safe_assign("analyst_mean_target", "analyst_mean_target_put")
    _safe_assign("company_industry", "company_industry_put")
    _safe_assign("company_sector", "company_sector_put")
    _safe_assign("iv_rank", "iv_rank_put")
    _safe_assign("iv_percentile", "iv_percentile_put")
    _safe_assign("days_to_expiration", "days_to_expiration_put")
    _safe_assign("days_to_earnings", "days_to_earnings_put")

    # Spread Width (keep for reference)
    df["width_put"] = (df["sell_strike_put"] - df["buy_strike_put"]).abs()
    df["width_call"] = (df["buy_strike_call"] - df["sell_strike_call"]).abs()

    # Black-Scholes theoretical prices for all 4 legs
    df['sell_bs_price_put'] = df.apply(
        lambda r: _calculate_bs_price(r['close_put'], r['sell_strike_put'], r['sell_iv_put'], r['days_to_expiration_put'], risk_free_rate, False), axis=1)
    df['buy_bs_price_put'] = df.apply(
        lambda r: _calculate_bs_price(r['close_put'], r['buy_strike_put'], r['buy_iv_put'], r['days_to_expiration_put'], risk_free_rate, False), axis=1)
    df['sell_bs_price_call'] = df.apply(
        lambda r: _calculate_bs_price(r['close_call'], r['sell_strike_call'], r['sell_iv_call'], r['days_to_expiration_call'], risk_free_rate, True), axis=1)
    df['buy_bs_price_call'] = df.apply(
        lambda r: _calculate_bs_price(r['close_call'], r['buy_strike_call'], r['buy_iv_call'], r['days_to_expiration_call'], risk_free_rate, True), axis=1)

    # Calculate all generic metrics
    metrics_df = df.apply(lambda r: _calculate_combined_metrics(r, iv_correction=iv_correction), axis=1)
    df = pd.concat([df, metrics_df], axis=1)

    # % OTM
    df["%_otm_put"] = (df["close_put"] - df["sell_strike_put"]) / df["close_put"] * 100
    df["%_otm_call"] = (df["sell_strike_call"] - df["close_call"]) / df["close_call"] * 100

    df["max_dte"] = df[["days_to_expiration_put", "days_to_expiration_call"]].max(axis=1)

    return df

def _add_earnings_and_urls(df: pd.DataFrame) -> pd.DataFrame:
    df['earnings_date'] = pd.to_datetime(df['earnings_date_put'], errors='coerce')
    df['expiration_date_put'] = pd.to_datetime(df['expiration_date_put'], errors='coerce')
    df['expiration_date_call'] = pd.to_datetime(df['expiration_date_call'], errors='coerce')

    # Add earnings_warning
    df['earnings_warning'] = df.apply(
        lambda r: create_earnings_warning(r['earnings_date'], min(r['expiration_date_put'], r['expiration_date_call'])), 
        axis=1
    )
    df['optionstrat_url'] = df.apply(_build_optionstrat_url, axis=1)

    return df

def _build_optionstrat_url(row: pd.Series) -> str:
    base_url = "https://optionstrat.com/build/iron-condor"
    symbol = row['symbol'].upper()
    
    p_buy = f".{symbol}{format_expiration_date(row['expiration_date_put'])}P{format_strike(row['buy_strike_put'])}"
    p_sell = f"-.{symbol}{format_expiration_date(row['expiration_date_put'])}P{format_strike(row['sell_strike_put'])}"
    c_sell = f"-.{symbol}{format_expiration_date(row['expiration_date_call'])}C{format_strike(row['sell_strike_call'])}"
    c_buy = f".{symbol}{format_expiration_date(row['expiration_date_call'])}C{format_strike(row['buy_strike_call'])}"
    
    return f"{base_url}/{symbol}/{p_buy},{p_sell},{c_sell},{c_buy}"

@log_function
def calc_iron_condors(put_spreads: pd.DataFrame, call_spreads: pd.DataFrame, iv_correction: str = 'auto', risk_free_rate: float = RISK_FREE_RATE) -> pd.DataFrame:
    if put_spreads.empty or call_spreads.empty:
        return pd.DataFrame()

    combined = put_spreads.merge(
        call_spreads,
        on="symbol",
        suffixes=("_put", "_call")
    )

    if combined.empty:
        return combined

    logger.debug(f"Combined DF before metrics: {combined[['symbol', 'sell_theta_put', 'buy_theta_put', 'sell_theta_call', 'buy_theta_call']].head()}")
    combined = _calculate_iron_condor_metrics(combined, iv_correction=iv_correction, risk_free_rate=risk_free_rate)
    combined = _add_earnings_and_urls(combined)

    return combined

def get_page_iron_condors(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    columns = [
        'symbol',
        'Company',
        'earnings_date',
        'earnings_warning',
        'close',
        'analyst_mean_target',
        'company_industry',
        'company_sector',
        'iv_rank',
        'iv_percentile',
        'max_profit',
        'bpr',
        'expected_value',
        'sell_iv',
        'APDI',
        'APDI_EV',
        'optionstrat_url',
        'total_theta',
        'days_to_expiration',
        'days_to_earnings',
        
        # columns for details and AI prompt
        'sell_strike_put',
        'buy_strike_put',
        'sell_strike_call',
        'buy_strike_call',
        '%_otm_put',
        '%_otm_call',
        'sell_delta_put',
        'sell_delta_call',
        'expiration_date_put',
        'expiration_date_call',
        'sell_last_option_price_put', 'buy_last_option_price_put',
        'sell_last_option_price_call', 'buy_last_option_price_call',
        'sell_bs_price_put', 'buy_bs_price_put',
        'sell_bs_price_call', 'buy_bs_price_call',
        'sell_iv_put', 'buy_iv_put', 'sell_iv_call', 'buy_iv_call',
        'sell_theta_put', 'buy_theta_put', 'sell_theta_call', 'buy_theta_call',
        'sell_open_interest_put', 'buy_open_interest_put',
        'sell_open_interest_call', 'buy_open_interest_call',
        'buy_delta_put', 'buy_delta_call',
        'sell_day_volume_put', 'buy_day_volume_put',
        'sell_day_volume_call', 'buy_day_volume_call',
        'sell_expected_move_put', 'buy_expected_move_put',
        'sell_expected_move_call', 'buy_expected_move_call',
        'sell_last_updated_put', 'buy_last_updated_put',
        'sell_last_updated_call', 'buy_last_updated_call',
        'historical_volatility_30d_put'
    ]
    
    # Only keep columns that actually exist in the dataframe
    existing_columns = [col for col in columns if col in df.columns]

    return df[existing_columns]


def get_page_iron_condors_enhanced(df: pd.DataFrame) -> pd.DataFrame:
    """Like get_page_iron_condors but keeps asset_type column added by the enhanced page."""
    if df.empty:
        return df

    columns = [
        'symbol',
        'Company',
        'asset_type',
        'earnings_date',
        'earnings_warning',
        'close',
        'analyst_mean_target',
        'company_industry',
        'company_sector',
        'iv_rank',
        'iv_percentile',
        'max_profit',
        'bpr',
        'expected_value',
        'sell_iv',
        'APDI',
        'APDI_EV',
        'optionstrat_url',
        'total_theta',
        'days_to_expiration',
        'days_to_earnings',
        'sell_strike_put',
        'buy_strike_put',
        'sell_strike_call',
        'buy_strike_call',
        '%_otm_put',
        '%_otm_call',
        'sell_delta_put',
        'sell_delta_call',
        'expiration_date_put',
        'expiration_date_call',
        'sell_last_option_price_put', 'buy_last_option_price_put',
        'sell_last_option_price_call', 'buy_last_option_price_call',
        'sell_bs_price_put', 'buy_bs_price_put',
        'sell_bs_price_call', 'buy_bs_price_call',
        'sell_iv_put', 'buy_iv_put', 'sell_iv_call', 'buy_iv_call',
        'sell_theta_put', 'buy_theta_put', 'sell_theta_call', 'buy_theta_call',
        'sell_open_interest_put', 'buy_open_interest_put',
        'sell_open_interest_call', 'buy_open_interest_call',
        'buy_delta_put', 'buy_delta_call',
        'sell_day_volume_put', 'buy_day_volume_put',
        'sell_day_volume_call', 'buy_day_volume_call',
        'sell_expected_move_put', 'buy_expected_move_put',
        'sell_expected_move_call', 'buy_expected_move_call',
        'sell_last_updated_put', 'buy_last_updated_put',
        'sell_last_updated_call', 'buy_last_updated_call',
        'historical_volatility_30d_put'
    ]

    existing_columns = [col for col in columns if col in df.columns]
    return df[existing_columns]


# ---------------------------------------------------------------------------
# Short Strangle
# ---------------------------------------------------------------------------

def _build_strangle_optionstrat_url(row: pd.Series) -> str:
    base_url = "https://optionstrat.com/build/short-strangle"
    sym = row['symbol'].upper()
    p = f"-.{sym}{format_expiration_date(row['expiration_date_put'])}P{format_strike(row['strike_put'])}"
    c = f"-.{sym}{format_expiration_date(row['expiration_date_call'])}C{format_strike(row['strike_call'])}"
    return f"{base_url}/{sym}/{p},{c}"


@log_function
def calc_strangles(put_df: pd.DataFrame, call_df: pd.DataFrame,
                   iv_correction: str = 'auto', risk_free_rate: float = RISK_FREE_RATE) -> pd.DataFrame:
    if put_df.empty or call_df.empty:
        return pd.DataFrame()

    combined = put_df.merge(call_df, on='symbol', suffixes=('_put', '_call'))
    if combined.empty:
        return combined

    # Rename columns for unified access
    if 'Company_put' in combined.columns:
        combined['Company'] = combined['Company_put']
    elif 'Company' not in combined.columns:
        combined['Company'] = combined['symbol']
    combined['Company'] = combined['Company'].replace('', None).fillna(combined['symbol'])

    for field in ['close', 'analyst_mean_target', 'company_industry', 'company_sector',
                  'iv_rank', 'iv_percentile', 'days_to_expiration', 'days_to_earnings']:
        if f'{field}_put' in combined.columns:
            combined[field] = combined[f'{field}_put']

    # Credit = sum of both premiums
    combined['total_credit'] = (combined['last_option_price_put'] + combined['last_option_price_call'])
    combined['total_credit_dollar'] = combined['total_credit'] * 100

    # P&L boundaries
    combined['breakeven_put'] = combined['strike_put'] - combined['total_credit']
    combined['breakeven_call'] = combined['strike_call'] + combined['total_credit']
    combined['%_otm_put'] = (combined['close_put'] - combined['strike_put']) / combined['close_put'] * 100
    combined['%_otm_call'] = (combined['strike_call'] - combined['close_call']) / combined['close_call'] * 100

    # sell_iv = avg of both short IVs
    combined['sell_iv'] = (combined['iv_put'] + combined['iv_call']) / 2

    # Theta
    combined['total_theta'] = combined['theta_put'].fillna(0) + combined['theta_call'].fillna(0)

    # Earnings
    combined['earnings_date'] = pd.to_datetime(combined['earnings_date_put'], errors='coerce')
    combined['expiration_date_put'] = pd.to_datetime(combined['expiration_date_put'], errors='coerce')
    combined['expiration_date_call'] = pd.to_datetime(combined['expiration_date_call'], errors='coerce')
    combined['earnings_warning'] = combined.apply(
        lambda r: create_earnings_warning(r['earnings_date'], min(r['expiration_date_put'], r['expiration_date_call'])),
        axis=1
    )
    combined['optionstrat_url'] = combined.apply(_build_strangle_optionstrat_url, axis=1)

    return combined


def get_page_strangles(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    columns = [
        'symbol', 'Company', 'asset_type', 'earnings_date', 'earnings_warning',
        'close', 'analyst_mean_target', 'company_industry', 'company_sector',
        'iv_rank', 'iv_percentile', 'sell_iv', 'total_credit', 'total_credit_dollar',
        'breakeven_put', 'breakeven_call', '%_otm_put', '%_otm_call',
        'total_theta', 'days_to_expiration', 'days_to_earnings',
        'strike_put', 'strike_call',
        'last_option_price_put', 'last_option_price_call',
        'delta_put', 'delta_call', 'iv_put', 'iv_call',
        'theta_put', 'theta_call', 'open_interest_put', 'open_interest_call',
        'day_volume_put', 'day_volume_call',
        'expiration_date_put', 'expiration_date_call',
        'optionstrat_url',
    ]
    return df[[c for c in columns if c in df.columns]]


# ---------------------------------------------------------------------------
# Jade Lizard  (Short OTM Put  +  Short OTM Call Spread)
# ---------------------------------------------------------------------------

def _build_jade_lizard_optionstrat_url(row: pd.Series) -> str:
    base_url = "https://optionstrat.com/build/jade-lizard"
    sym = row['symbol'].upper()
    p_sell  = f"-.{sym}{format_expiration_date(row['expiration_date_put'])}P{format_strike(row['strike_put'])}"
    c_sell  = f"-.{sym}{format_expiration_date(row['expiration_date_call'])}C{format_strike(row['sell_strike_call'])}"
    c_buy   = f".{sym}{format_expiration_date(row['expiration_date_call'])}C{format_strike(row['buy_strike_call'])}"
    return f"{base_url}/{sym}/{p_sell},{c_sell},{c_buy}"


@log_function
def calc_jade_lizards(put_df: pd.DataFrame, call_spread_df: pd.DataFrame,
                      iv_correction: str = 'auto', risk_free_rate: float = RISK_FREE_RATE) -> pd.DataFrame:
    """put_df: plain short put legs (from jade_lizard_input.sql with option_type=put).
       call_spread_df: already-built call spreads (sell+buy) from iron_condors_enhanced_input.sql with option_type=call."""
    if put_df.empty or call_spread_df.empty:
        return pd.DataFrame()

    combined = put_df.merge(call_spread_df, on='symbol', suffixes=('_put', '_call'))
    if combined.empty:
        return combined

    if 'Company_put' in combined.columns:
        combined['Company'] = combined['Company_put']
    elif 'Company' not in combined.columns:
        combined['Company'] = combined['symbol']
    combined['Company'] = combined['Company'].replace('', None).fillna(combined['symbol'])

    for field in ['close', 'analyst_mean_target', 'company_industry', 'company_sector',
                  'iv_rank', 'iv_percentile', 'days_to_expiration', 'days_to_earnings']:
        if f'{field}_put' in combined.columns:
            combined[field] = combined[f'{field}_put']

    # call spread columns come from iron_condors_enhanced_input with _call suffix
    combined['sell_strike_call'] = combined.get('sell_strike_call', combined.get('sell_strike_call'))
    combined['buy_strike_call']  = combined.get('buy_strike_call',  combined.get('buy_strike_call'))

    combined['call_spread_width'] = (combined['buy_strike_call'] - combined['sell_strike_call']).abs()

    # Total credit = put premium + call spread net credit
    # put_df kommt aus short_strangle_input.sql: Spalte heisst 'last_option_price', nach merge '_put'
    put_price_col = 'last_option_price_put' if 'last_option_price_put' in combined.columns else 'last_option_price'
    combined['put_credit']        = combined[put_price_col]
    combined['call_spread_credit'] = combined['sell_last_option_price_call'] - combined['buy_last_option_price_call']
    combined['total_credit']      = combined['put_credit'] + combined['call_spread_credit']
    combined['total_credit_dollar'] = combined['total_credit'] * 100

    # Key tastylive rule: no upside risk when total_credit > call_spread_width
    combined['no_upside_risk'] = combined['total_credit'] > combined['call_spread_width']

    # Max loss: put side is undefined (put strike - credit if assigned), call side defined
    combined['max_loss_call_side'] = (combined['call_spread_width'] - combined['call_spread_credit']) * 100
    combined['breakeven_put'] = combined['strike_put'] - combined['total_credit']
    combined['%_otm_put'] = (combined['close_put'] - combined['strike_put']) / combined['close_put'] * 100
    combined['%_otm_call'] = (combined['sell_strike_call'] - combined['close_put']) / combined['close_put'] * 100

    combined['sell_iv'] = (combined['iv_put'] + combined.get('sell_iv_call', combined.get('iv_call', combined['iv_put']))) / 2
    combined['total_theta'] = combined['theta_put'].fillna(0) + combined.get('sell_theta_call', pd.Series(0, index=combined.index)).fillna(0)

    combined['earnings_date'] = pd.to_datetime(combined['earnings_date_put'], errors='coerce')
    combined['expiration_date_put']  = pd.to_datetime(combined['expiration_date_put'], errors='coerce')
    combined['expiration_date_call'] = pd.to_datetime(combined['expiration_date_call'], errors='coerce')
    combined['earnings_warning'] = combined.apply(
        lambda r: create_earnings_warning(r['earnings_date'], min(r['expiration_date_put'], r['expiration_date_call'])),
        axis=1
    )
    combined['optionstrat_url'] = combined.apply(_build_jade_lizard_optionstrat_url, axis=1)

    return combined


def get_page_jade_lizards(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    columns = [
        'symbol', 'Company', 'asset_type', 'earnings_date', 'earnings_warning',
        'close', 'analyst_mean_target', 'company_industry', 'company_sector',
        'iv_rank', 'iv_percentile', 'sell_iv',
        'total_credit', 'total_credit_dollar', 'no_upside_risk',
        'call_spread_width', 'put_credit', 'call_spread_credit',
        'breakeven_put', 'max_loss_call_side',
        '%_otm_put', '%_otm_call',
        'total_theta', 'days_to_expiration', 'days_to_earnings',
        'strike_put', 'sell_strike_call', 'buy_strike_call',
        'last_option_price_put',
        'sell_last_option_price_call', 'buy_last_option_price_call',
        'delta_put', 'sell_delta_call',
        'iv_put', 'sell_iv_call',
        'theta_put', 'sell_theta_call',
        'open_interest_put', 'sell_open_interest_call',
        'day_volume_put', 'sell_day_volume_call',
        'expiration_date_put', 'expiration_date_call',
        'optionstrat_url',
    ]
    return df[[c for c in columns if c in df.columns]]