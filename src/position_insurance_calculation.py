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
        - insurance_cost_pct
        - downside_protection_pct
        - annualized_cost
        - annualized_cost_pct
        - upside_drag_pct
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
    
    # 7. Insurance Cost % = (Put Price / Stock Price) * 100
    #    Shows the cost of insurance as a percentage of the current stock value
    df['insurance_cost_pct'] = df.apply(
        lambda row: (row['option_price'] / row['live_stock_price'] * 100) if row['live_stock_price'] > 0 else 0,
        axis=1
    )

    # 8. Downside Protection % = ((Stock Price - Strike) / Stock Price) * 100
    #    How far the stock must fall before the put kicks in.
    #    Negative values mean the put is already ITM (stronger protection).
    df['downside_protection_pct'] = df.apply(
        lambda row: ((row['live_stock_price'] - row['strike_price']) / row['live_stock_price'] * 100) if row['live_stock_price'] > 0 else 0,
        axis=1
    )

    # 9. Annualized Cost ($) = (Time Value / DTE) * 365
    #    Makes time-value costs comparable across different expirations
    df['annualized_cost'] = df.apply(
        lambda row: (row['time_value'] / row['days_to_expiration']) * 365 if row['days_to_expiration'] > 0 else 0,
        axis=1
    )

    # 10. Annualized Cost % = (Annualized Cost / Stock Price) * 100
    #     Percentage annual cost relative to stock price
    df['annualized_cost_pct'] = df.apply(
        lambda row: (row['annualized_cost'] / row['live_stock_price'] * 100) if row['live_stock_price'] > 0 else 0,
        axis=1
    )

    # 11. Upside Drag % = (Put Price / Stock Price) * 100
    #     Performance drag from the put cost on upside moves
    #     Same formula as insurance_cost_pct but separate column for semantic clarity in UI
    df['upside_drag_pct'] = df['insurance_cost_pct']

    return df


def calculate_collar_metrics(
    put_df: pd.DataFrame,
    call_price: float,
    call_strike: float,
    cost_basis: float
) -> pd.DataFrame:
    """
    Calculates Collar metrics for a selected Call applied to all Put rows.

    The Collar strategy combines a Protective Put (already calculated) with
    a Covered Call to offset the put premium. The user selects ONE call
    (strike + price) which is applied to every put row for comparison.

    Args:
        put_df: DataFrame with Put options (already enriched with Married-Put metrics
                via calculate_position_insurance_metrics). Must contain:
                - strike_price (put strike)
                - option_price (put price)
                - live_stock_price
        call_price: Midpoint price of the selected Call option.
        call_strike: Strike price of the selected Call option.
        cost_basis: Original cost basis per share.

    Returns:
        DataFrame with additional Collar columns:
        - collar_new_cost_basis
        - collar_locked_in_profit
        - collar_locked_in_profit_pct
        - collar_net_cost
        - collar_max_profit
        - collar_max_profit_pct
        - pct_assigned
        - pct_assigned_with_put
    """
    if put_df.empty:
        return put_df

    df = put_df.copy()

    # Collar New Cost Basis = Cost Basis + Put Price - Call Price
    df['collar_new_cost_basis'] = cost_basis + df['option_price'] - call_price

    # Collar Locked-in Profit = Put Strike - Collar New Cost Basis
    df['collar_locked_in_profit'] = df['strike_price'] - df['collar_new_cost_basis']

    # Collar Locked-in Profit % = (Collar Locked-in Profit / Collar NCB) * 100
    df['collar_locked_in_profit_pct'] = df.apply(
        lambda row: (row['collar_locked_in_profit'] / row['collar_new_cost_basis'] * 100)
        if row['collar_new_cost_basis'] != 0 else 0,
        axis=1
    )

    # Collar Net Cost = Put Price - Call Price
    # Positive = Debit (you pay), Negative = Credit (you receive)
    df['collar_net_cost'] = df['option_price'] - call_price

    # Collar Max Profit = Call Strike - Collar New Cost Basis
    # Maximum gain if stock rises to or above the call strike (shares get called away)
    df['collar_max_profit'] = call_strike - df['collar_new_cost_basis']

    # Collar Max Profit % = (Collar Max Profit / Collar NCB) * 100
    df['collar_max_profit_pct'] = df.apply(
        lambda row: (row['collar_max_profit'] / row['collar_new_cost_basis'] * 100)
        if row['collar_new_cost_basis'] != 0 else 0,
        axis=1
    )

    # % Assigned = (Call Strike - Collar NCB) / Collar NCB * 100
    # Same as collar_max_profit_pct (gain if assigned at call strike)
    df['pct_assigned'] = df['collar_max_profit_pct']

    # Put Value at Call Strike = max(0, Put Strike - Call Strike)
    # If put strike > call strike, the put still has value at assignment price
    df['_put_value_at_call_strike'] = (df['strike_price'] - call_strike).clip(lower=0)

    # % Assigned with Put = (Call Strike - Collar NCB + Put Value at Call Strike) / Collar NCB * 100
    df['pct_assigned_with_put'] = df.apply(
        lambda row: ((call_strike - row['collar_new_cost_basis'] + row['_put_value_at_call_strike'])
                     / row['collar_new_cost_basis'] * 100)
        if row['collar_new_cost_basis'] != 0 else 0,
        axis=1
    )

    # Drop helper column
    df.drop(columns=['_put_value_at_call_strike'], inplace=True)

    return df
