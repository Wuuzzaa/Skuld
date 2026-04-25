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

# Setup logging
logger = logging.getLogger(os.path.basename(__file__))

def _calculate_combined_metrics(row: pd.Series, iv_correction: str = 'auto') -> pd.Series:
    """Calculates all metrics for an Iron Condor using the generic calculator."""
    legs = [
        # Put side
        OptionLeg(strike=row['sell_strike_put'], premium=row['sell_last_option_price_put'], is_call=False, is_long=False, theta=row.get('sell_theta_put')),
        OptionLeg(strike=row['buy_strike_put'], premium=row['buy_last_option_price_put'], is_call=False, is_long=True, theta=row.get('buy_theta_put')),
        # Call side
        OptionLeg(strike=row['sell_strike_call'], premium=row['sell_last_option_price_call'], is_call=True, is_long=False, theta=row.get('sell_theta_call')),
        OptionLeg(strike=row['buy_strike_call'], premium=row['buy_last_option_price_call'], is_call=True, is_long=True, theta=row.get('buy_theta_call')),
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

def _calculate_iron_condor_metrics(df: pd.DataFrame, iv_correction: str = 'auto') -> pd.DataFrame:
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
def calc_iron_condors(put_spreads: pd.DataFrame, call_spreads: pd.DataFrame, iv_correction: str = 'auto') -> pd.DataFrame:
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
    combined = _calculate_iron_condor_metrics(combined, iv_correction=iv_correction)
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
        'sell_iv_put', 'buy_iv_put', 'sell_iv_call', 'buy_iv_call',
        'sell_theta_put', 'buy_theta_put', 'sell_theta_call', 'buy_theta_call',
        'sell_open_interest_put', 'buy_open_interest_put',
        'sell_open_interest_call', 'buy_open_interest_call',
        'buy_delta_put', 'buy_delta_call',
        'sell_day_volume_put', 'buy_day_volume_put',
        'sell_day_volume_call', 'buy_day_volume_call',
        'sell_expected_move_put', 'buy_expected_move_put',
        'sell_expected_move_call', 'buy_expected_move_call',
        'historical_volatility_30d_put'
    ]
    
    # Only keep columns that actually exist in the dataframe
    existing_columns = [col for col in columns if col in df.columns]
    
    return df[existing_columns]