import pandas as pd
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def calculate_position_insurance_metrics(df: pd.DataFrame, cost_basis: float) -> pd.DataFrame:
    """
    Calculates Position Insurance metrics for a DataFrame of Put options.

    Args:
        df: DataFrame containing option data with columns:
            - strike_price
            - option_price (day_close)
            - days_to_expiration
            - live_stock_price (or stock_close)
            - expiration_date
        cost_basis: The user's cost basis per share.

    Returns:
        DataFrame with added metrics:
        - new_cost_basis
        - locked_in_profit (value and %)
        - risk (value and %)
        - time_value
        - time_value_per_month
    """
    if df.empty:
        return df

    # Ensure necessary columns exist
    required_columns = ['strike_price', 'option_price', 'days_to_expiration', 'live_stock_price']
    for col in required_columns:
        if col not in df.columns:
            logger.error(f"Missing column {col} in calculation dataframe")
            return df

    # Use live_stock_price, fallback to stock_close if needed/available, or just use what's there
    current_price = df['live_stock_price']
    
    # 1. New Cost Basis = Cost Basis + Put Price
    df['new_cost_basis'] = cost_basis + df['option_price']

    # 2. Locked-in Profit = Strike Price - New Cost Basis
    df['locked_in_profit'] = df['strike_price'] - df['new_cost_basis']

    # 3. Locked-in Profit % = Locked-in Profit / New Cost Basis
    df['locked_in_profit_pct'] = (df['locked_in_profit'] / df['new_cost_basis']) * 100

    # 4. Risk (Max Loss) = If Locked-in Profit is negative, it's the loss.
    #    Actually "Risk" is usually defined relative to the Cost Basis or Current Value.
    #    From requirements: "Maximales Risiko (%) Falls Locked-in Profit negativ: |Locked-in Profit| / Neuer Einstandskurs * 100"
    df['risk_pct'] = df.apply(
        lambda row: (abs(row['locked_in_profit']) / row['new_cost_basis'] * 100) if row['locked_in_profit'] < 0 else 0,
        axis=1
    )

    # 5. Time Value (Zeitwert)
    #    Intrinsic Value of Put = Max(0, Strike - Stock Price)
    #    Time Value = Put Price - Intrinsic Value
    df['intrinsic_value'] = (df['strike_price'] - current_price).clip(lower=0)
    df['time_value'] = df['option_price'] - df['intrinsic_value']

    # 6. Time Value per Month
    #    Formula: Put-Zeitwert / (Tage bis Verfall / 30)
    #    Avoid division by zero
    df['time_value_per_month'] = df.apply(
        lambda row: row['time_value'] / (row['days_to_expiration'] / 30) if row['days_to_expiration'] > 0 else 0,
        axis=1
    )
    
    # Unrealized Profit (for reference, though this is usually singular per stock, not per option)
    # This might be better calculated outside or displayed in the header
    
    return df
