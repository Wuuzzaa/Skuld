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
from src.monte_carlo_simulation import UniversalOptionsMonteCarloSimulator

# Setup logging
logger = logging.getLogger(os.path.basename(__file__))

def _calculate_metrics_for_row(row: pd.Series, strategy_type: str = 'credit', iv_correction: str = 'auto', 
                               take_profit: float = None, stop_loss: float = None, dte_close: int = None) -> pd.Series:
    """Calculates all metrics for a single spread using the generic calculator."""
    is_credit = strategy_type == 'credit'
    
    legs = [
        OptionLeg(
            strike=row['sell_strike'],
            premium=row['sell_last_option_price'],
            is_call=row['option_type'] == 'call',
            is_long=not is_credit,
            delta=row.get('sell_delta'),
            iv=row.get('sell_iv'),
            theta=row.get('sell_theta'),
            oi=row.get('sell_open_interest'),
            volume=row.get('sell_day_volume'),
            expected_move=row.get('sell_expected_move'),
            take_profit_pct=take_profit,
            stop_loss_pct=stop_loss,
            dte_close=dte_close
        ),
        OptionLeg(
            strike=row['buy_strike'],
            premium=row['buy_last_option_price'],
            is_call=row['option_type'] == 'call',
            is_long=is_credit,
            delta=row.get('buy_delta'),
            iv=row.get('buy_iv'),
            theta=row.get('buy_theta'),
            oi=row.get('buy_open_interest'),
            volume=row.get('buy_day_volume'),
            expected_move=row.get('buy_expected_move'),
            take_profit_pct=take_profit,
            stop_loss_pct=stop_loss,
            dte_close=dte_close
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
        "expected_value_managed": metrics.expected_value_managed,
        "spread_theta": metrics.total_theta,
        "profit_to_bpr": metrics.profit_to_bpr,
        "APDI": metrics.apdi,
        "APDI_EV": metrics.apdi_ev,
        "iv_correction_factor": metrics.iv_correction_factor,
        "corrected_volatility": metrics.corrected_volatility,
        "delta": metrics.delta,
        "gamma": metrics.gamma,
        "vega": metrics.vega
    })

def _calculate_spread_metrics(df: pd.DataFrame, strategy_type: str = 'credit', iv_correction: str = 'auto',
                             take_profit: float = None, stop_loss: float = None, dte_close: int = None) -> pd.DataFrame:
    """Calculates all relevant metrics for the spreads using batch processing."""
    if df.empty:
        return df

    # Spread Width
    df["spread_width"] = (df['sell_strike'] - df['buy_strike']).abs()

    # % Out-of-the-Money (OTM)
    df["%_otm"] = (df["sell_strike"] - df["close"]).abs() / df["close"] * 100

    # Grouping by ticker (and other simulation parameters) to use batch simulation
    # Parameters for simulation: current_price (close), volatility (sell_iv), dte (days_to_expiration)
    # We round these slightly to increase grouping potential (e.g. if close varies by 0.01)
    df['_sim_group'] = df.apply(lambda r: f"{r['symbol']}_{round(r['close'], 2)}_{round(r['sell_iv'], 3)}_{r['days_to_expiration']}", axis=1)
    
    all_results = []
    
    for group_id, group_df in df.groupby('_sim_group'):
        first_row = group_df.iloc[0]
        
        # Initialize simulator for this group
        # Use num_simulations=2500 for screening to be extra fast, or use default
        from src.options_utils import NUM_SIMULATIONS
        # If it's a large screening, we might want to reduce simulations
        n_sim = 5000 if len(group_df) < 20 else 2500
        
        simulator = UniversalOptionsMonteCarloSimulator(
            current_price=first_row['close'],
            volatility=first_row['sell_iv'],
            dte=int(first_row['days_to_expiration']),
            num_simulations=n_sim,
            iv_correction=iv_correction
        )
        
        # Prepare strategies for batch
        strategies = []
        is_credit = strategy_type == 'credit'
        
        for idx, row in group_df.iterrows():
            legs = [
                {
                    'strike': row['sell_strike'],
                    'premium': row['sell_last_option_price'],
                    'is_call': row['option_type'] == 'call',
                    'is_long': not is_credit,
                    'take_profit_pct': take_profit,
                    'stop_loss_pct': stop_loss,
                    'dte_close': dte_close
                },
                {
                    'strike': row['buy_strike'],
                    'premium': row['buy_last_option_price'],
                    'is_call': row['option_type'] == 'call',
                    'is_long': is_credit,
                    'take_profit_pct': take_profit,
                    'stop_loss_pct': stop_loss,
                    'dte_close': dte_close
                }
            ]
            strategies.append(legs)
            
        # 1. Batch EV Managed
        ev_managed_list = simulator.calculate_expected_value_batch(strategies)
        
        # 2. Batch EV Static (for comparison)
        static_strategies = []
        for s in strategies:
            static_s = [leg.copy() for leg in s]
            for leg in static_s:
                leg['take_profit_pct'] = None
                leg['stop_loss_pct'] = None
                leg['dte_close'] = None
            static_strategies.append(static_s)
        ev_static_list = simulator.calculate_expected_value_batch(static_strategies)
        
        # 3. Batch Greeks
        # Only calculate Greeks for strategies that are potentially profitable
        greeks_results = simulator.calculate_greeks_batch(strategies)
        
        # 4. Other metrics
        group_results = []
        for i, (idx, row) in enumerate(group_df.iterrows()):
            # Analytical fields
            if is_credit:
                max_profit = (row['sell_last_option_price'] - row['buy_last_option_price']) * 100
                max_loss = (row['spread_width'] * 100) - max_profit
            else:
                # Debit: row['sell_last_option_price'] is ITM price, row['buy_last_option_price'] is OTM price
                max_loss = (row['sell_last_option_price'] - row['buy_last_option_price']) * 100
                max_profit = (row['spread_width'] * 100) - max_loss
            
            bpr = max(0.0, max_loss)
            
            greeks = greeks_results[i]
            
            res = {
                "max_profit": max_profit,
                "max_loss": max_loss,
                "bpr": bpr,
                "expected_value": ev_static_list[i],
                "expected_value_managed": ev_managed_list[i],
                "spread_theta": (row.get('sell_theta', 0) or 0) * (-1 if is_credit else 1) + (row.get('buy_theta', 0) or 0) * (1 if is_credit else -1),
                "profit_to_bpr": (max_profit / bpr * 100) if bpr > 0 else 0,
                "iv_correction_factor": simulator.iv_correction_factor,
                "corrected_volatility": simulator.volatility,
                "delta": greeks['delta'],
                "gamma": greeks['gamma'],
                "vega": greeks['vega']
            }
            # APDI
            res["APDI"] = (res["max_profit"] / max(1, row['days_to_expiration']) / max(1, res["bpr"]) * 100)
            res["APDI_EV"] = (res["expected_value_managed"] / max(1, row['days_to_expiration']) / max(1, res["bpr"]) * 100)
            
            group_results.append(res)
            
        group_res_df = pd.DataFrame(group_results, index=group_df.index)
        all_results.append(group_res_df)
        
    if all_results:
        metrics_df = pd.concat(all_results).sort_index()
        df = pd.concat([df, metrics_df], axis=1)
    
    df.drop(columns=['_sim_group'], inplace=True)

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
def calc_spreads(df: pd.DataFrame, strategy_type: str = 'credit', iv_correction: str = 'auto',
                 take_profit: float = None, stop_loss: float = None, dte_close: int = None) -> pd.DataFrame:
    """Main calculation entry point for spreads."""
    if df.empty:
        return df
    
    df = _calculate_spread_metrics(df, strategy_type, iv_correction=iv_correction,
                                   take_profit=take_profit, stop_loss=stop_loss, dte_close=dte_close)
    df = _add_earnings_and_urls(df, strategy_type)
    
    return df

def get_page_spreads(df: pd.DataFrame, strategy_type: str = 'credit', iv_correction: str = 'auto',
                     take_profit: float = None, stop_loss: float = None, dte_close: int = None) -> pd.DataFrame:
    """Prepares the DataFrame for display in the frontend."""
    if df.empty:
        return df
        
    df = calc_spreads(df, strategy_type, iv_correction=iv_correction,
                      take_profit=take_profit, stop_loss=stop_loss, dte_close=dte_close)
    
    if df.empty:
        return df

    columns = [
        'symbol', 'Company', 'earnings_date', 'earnings_warning', 'close', 
        'analyst_mean_target', 'company_industry', 'company_sector', 
        'historical_volatility_30d', 'iv_rank', 'iv_percentile',
        'spread_width', 'max_profit', 'bpr', 'profit_to_bpr', 'spread_theta', 
        'expected_value', 'expected_value_managed', 'iv_correction_factor', 'APDI', 'APDI_EV', 'optionstrat_url',
        'delta', 'gamma', 'vega',
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