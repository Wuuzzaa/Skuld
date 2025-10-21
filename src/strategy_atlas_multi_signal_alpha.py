import logging
from src.logger_config import setup_logging
import pandas as pd
import numpy as np
from config import *
from src.decorator_log_function import log_function

# enable logging
setup_logging(log_file=PATH_LOG_FILE, log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(__name__)
logger.info(f"Start {__name__} ({__file__})")
# Python backend for the Multi-Factor Technical Screening Strategy
# - Defines a single entry function `compute_signals(df, ...)` which returns `signals_df`.
# - The function expects a pandas DataFrame `df` containing at least `symbol` and `close` and the indicator columns you provided.
# - It is defensive to missing columns and fills missing numeric indicators with np.nan.
# - It **does not** execute on any `df` here; it only defines functions. Call compute_signals(your_df) in your backend.
#
# Usage example (in your backend):
# signals = compute_signals(df)
#
# NOTE: This cell only defines the backend; it prints a readiness message.




# --- Helper functions ---
def safe(colname, row, default=np.nan):
    """Return row[colname] if present in row, else default."""
    return row.get(colname, default)


def norm01(x, minv, maxv):
    """Normalize x to 0..1 between minv and maxv (clip outside)."""
    if np.isnan(x):
        return 0.0
    if maxv == minv:
        return 0.0
    return float(np.clip((x - minv) / (maxv - minv), 0.0, 1.0))


def weighted_cap(score, cap=100):
    return float(np.clip(score, 0, cap))


# interpret recommendations: we'll treat strings/numerics: if numeric, 1=buy maybe; if string 'buy' etc.
def interpret_rec(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return 0.0
    if isinstance(x, (int, float, np.number)):
        # Many providers use positive numbers (1..5) or scores. We'll normalize to 0..1 assuming range -1..2
        return float(x) / 5.0 if abs(x) > 1e-9 else 0.0
    xs = str(x).lower()
    if 'buy' in xs and 'strong' in xs:
        return 1.0
    if 'buy' in xs:
        return 0.9
    if 'neutral' in xs or 'hold' in xs:
        return 0.5
    if 'sell' in xs:
        return 0.0
    try:
        # try to parse numeric-like strings
        return float(xs) / 5.0
    except Exception:
        return 0.0

# We'll compute some global normalization baselines from existing numeric columns when needed
# Use percentiles for robust normalization
def col_percentile(col):
    if col in df.columns:
        vals = pd.to_numeric(df[col], errors='coerce').dropna()
        if len(vals) == 0:
            return (0.0, 1.0)
        return (np.nanpercentile(vals, 5), np.nanpercentile(vals, 95))
    return (0.0, 1.0)


@log_function
def calculate_atlas_multi_signal_alpha_strategy(
        df:pd.DataFrame,
        equity=100000.0,
        risk_per_trade_pct=0.005,
        score_threshold=70.0,
        adx_trend_threshold=25.0,
        rsi_meanrev_threshold=35.0,
        bb_stop_k=1.0,
        bb_target_cons_k=1.5,
        bb_target_agg_k=2.5):
    """
    Compute signals for each row (symbol) in df and return a signals DataFrame.

    Parameters:
      df: pandas.DataFrame with one row per symbol and columns with technical indicators.
      equity: portfolio equity used to compute suggested position sizing.
      risk_per_trade_pct: fractional risk per trade (e.g., 0.005 = 0.5%)
      score_threshold: minimal score to include symbol in suggestions (0-100)
      other multipliers for stops/targets

    Returns:
      signals_df: pandas.DataFrame with columns:
        ['symbol','signal_score','conviction','entry_price','stop_loss','target_conservative',
         'target_aggressive','trade_type','rationale_flags','confidence_reason','expected_holding_days_estimate',
         'position_size_shares','position_size_value']
    """
    rows_out = []

    # Baselines (example: AO, BBPower, volume)
    ao_min, ao_max = col_percentile('AO')
    bbpower_min, bbpower_max = col_percentile('BBPower')
    volume_min, volume_max = col_percentile('volume')
    adx_min, adx_max = col_percentile('ADX')
    rsi_min, rsi_max = 0.0, 100.0  # fixed bounds for RSI

    # iterate rows
    for _, row_series in df.iterrows():
        row = row_series.to_dict()
        symbol = safe('symbol', row, default=None) or safe('ticker', row, default=None) or 'UNKNOWN'
        close = safe('close', row, np.nan)

        # Basic derived fields
        ema50 = safe('EMA50', row, np.nan)
        ema100 = safe('EMA100', row, np.nan)
        vwma = safe('VWMA', row, np.nan)
        hull9 = safe('HullMA9', row, np.nan)
        ichimoku_rec = safe('Rec.Ichimoku', row, np.nan)
        macd_val = safe('MACD.macd', row, np.nan)
        macd_sig = safe('MACD.signal', row, np.nan)
        ao = safe('AO', row, np.nan)
        ao1 = safe('AO[1]', row, np.nan)
        mom = safe('Mom', row, np.nan)
        mom1 = safe('Mom[1]', row, np.nan)
        rsi = safe('RSI', row, np.nan)
        rsi1 = safe('RSI[1]', row, np.nan)
        cci = safe('CCI20', row, np.nan)
        stochK = safe('Stoch.K', row, np.nan)
        stochK1 = safe('Stoch.K[1]', row, np.nan)
        macd_bull = False if (np.isnan(macd_val) or np.isnan(macd_sig)) else (macd_val > macd_sig)
        adx = safe('ADX', row, np.nan)
        bb_upper = safe('BB.upper', row, np.nan)
        bb_lower = safe('BB.lower', row, np.nan)
        bb_width = np.nan
        if (not np.isnan(bb_upper)) and (not np.isnan(bb_lower)):
            bb_width = bb_upper - bb_lower
            if bb_width <= 0:
                bb_width = np.nan
        bbpower = safe('BBPower', row, np.nan)
        volume = safe('volume', row, np.nan)
        vwma_col = safe('VWMA', row, np.nan)

        # Pivot fields - prefer Classic if available, fall back to other sets
        pivot_middle = None
        pivot_r1 = None
        pivot_r2 = None
        pivot_s1 = None
        pivot_s2 = None
        # Try Classic
        if 'Pivot.M.Classic.Middle' in df.columns:
            pivot_middle = safe('Pivot.M.Classic.Middle', row, np.nan)
            pivot_r1 = safe('Pivot.M.Classic.R1', row, np.nan)
            pivot_r2 = safe('Pivot.M.Classic.R2', row, np.nan)
            pivot_s1 = safe('Pivot.M.Classic.S1', row, np.nan)
            pivot_s2 = safe('Pivot.M.Classic.S2', row, np.nan)
        else:
            # fallback to Fibonacci or Camarilla etc.
            pivot_middle = safe('Pivot.M.Fibonacci.Middle', row, np.nan)
            pivot_r1 = safe('Pivot.M.Fibonacci.R1', row, np.nan)
            pivot_r2 = safe('Pivot.M.Fibonacci.R2', row, np.nan)
            pivot_s1 = safe('Pivot.M.Fibonacci.S1', row, np.nan)
            pivot_s2 = safe('Pivot.M.Fibonacci.S2', row, np.nan)

        # --- Scoring components ---
        trend_score = 0.0
        momentum_score = 0.0
        meanrev_score = 0.0
        vol_break_score = 0.0
        volume_score = 0.0
        pivot_score = 0.0
        rationale_flags = []

        # Trend filter (max 25 points)
        # Criteria: close > EMA50 and EMA50 > EMA100 and VWMA > EMA50 give strong trend
        try:
            if not np.isnan(close) and not np.isnan(ema50) and not np.isnan(ema100) and not np.isnan(vwma):
                if (close > ema50) and (ema50 > ema100) and (vwma > ema50):
                    trend_score += 25.0
                    rationale_flags.append('TREND_STRONG_EMA_VWMA')
                elif (close > ema50) and (ema50 > ema100):
                    trend_score += 15.0
                    rationale_flags.append('TREND_EMA')
                elif ichimoku_rec == 'bullish' or (
                        not np.isnan(ichimoku_rec) and str(ichimoku_rec).lower().startswith('b')):
                    trend_score += 18.0
                    rationale_flags.append('TREND_ICHIMOKU')
                else:
                    # small partial if hull9 is aligned
                    if not np.isnan(hull9) and close > hull9:
                        trend_score += 8.0
                        rationale_flags.append('TREND_HULL9')
            else:
                # fallback: rely on Ichimoku if present
                if ichimoku_rec == 'bullish' or (
                        not np.isnan(ichimoku_rec) and str(ichimoku_rec).lower().startswith('b')):
                    trend_score += 18.0
                    rationale_flags.append('TREND_ICHIMOKU_ONLY')
        except Exception:
            pass

        # Momentum (max 25 points)
        try:
            if macd_bull:
                momentum_score += 15.0
                rationale_flags.append('MACD_BULL')
            if not np.isnan(ao) and not np.isnan(ao1) and ao > 0 and ao > ao1:
                momentum_score += 5.0
                rationale_flags.append('AO_POS_UP')
            if not np.isnan(mom) and mom > 0:
                momentum_score += 5.0
                rationale_flags.append('MOM_POS')
            # ADX as amplifier
            if not np.isnan(adx) and adx >= adx_trend_threshold:
                momentum_score *= 1.20
                rationale_flags.append('ADX_STRONG')
        except Exception:
            pass
        momentum_score = min(momentum_score, 25.0)

        # Mean Reversion (max 15)
        try:
            if not np.isnan(rsi) and rsi < rsi_meanrev_threshold:
                # only good mean-revert if trend is intact (close > ema50)
                if not np.isnan(ema50) and close > ema50:
                    meanrev_score += 10.0
                    rationale_flags.append('RSI_MEANREV_IN_TREND')
                else:
                    meanrev_score += 6.0
                    rationale_flags.append('RSI_MEANREV')
            if not np.isnan(cci) and cci < -100:
                meanrev_score += 4.0
                rationale_flags.append('CCI20_OVERSOLD')
            if not np.isnan(stochK) and not np.isnan(stochK1) and stochK < 20 and stochK > stochK1:
                meanrev_score += 3.0
                rationale_flags.append('STOCH_K_RISING')
        except Exception:
            pass
        meanrev_score = min(meanrev_score, 15.0)

        # Volatility / Breakout (max 15)
        try:
            # BB squeeze detection: BBPower low (normalize) AND BB width small
            bbpower_norm = norm01(bbpower, bbpower_min, bbpower_max) if not np.isnan(bbpower) else 0.0
            if not np.isnan(bb_width) and bb_width > 0:
                # small width = squeeze -> we reward potential breakout only if price near bands
                median_bb = (bb_upper + bb_lower) / 2.0 if (
                            not np.isnan(bb_upper) and not np.isnan(bb_lower)) else np.nan
                # if BBPower indicates compression (small normalized) -> reward
                if bbpower_norm < 0.4:
                    vol_break_score += 8.0
                    rationale_flags.append('BB_SQUEEZE')
                # price near lower band but other momentum bullish => potential squeeze->reversal long
                if (not np.isnan(close) and not np.isnan(bb_lower)) and (close < (bb_lower + 0.25 * bb_width)):
                    vol_break_score += 4.0
                    rationale_flags.append('PRICE_NEAR_BBLOWER')
                # price breaking above middle towards upper and MACD bullish -> breakout
                if (not np.isnan(pivot_middle) and not np.isnan(close) and close > pivot_middle and macd_bull):
                    vol_break_score += 3.0
                    rationale_flags.append('BREAK_ABOVE_PIVOT_MID_MACD')
            else:
                # if no BB available but MACD bull + AO positive, reward small
                if macd_bull and not np.isnan(ao) and ao > 0:
                    vol_break_score += 4.0
                    rationale_flags.append('MACD_AO_BREAK')
        except Exception:
            pass
        vol_break_score = min(vol_break_score, 15.0)

        # Volume confirmation (max 10)
        try:
            if not np.isnan(volume) and not np.isnan(vwma_col):
                if volume > vwma_col:
                    volume_score += 10.0
                    rationale_flags.append('VOLUME_SPIKE')
                else:
                    # relative strength of volume
                    vol_norm = norm01(volume, volume_min, volume_max)
                    volume_score += vol_norm * 6.0
            elif not np.isnan(vwma_col):
                volume_score += 4.0
        except Exception:
            pass
        volume_score = min(volume_score, 10.0)

        # Pivot / Support (max 10)
        try:
            if (not np.isnan(pivot_s1) and not np.isnan(close)) and (
            close > pivot_s1 and close < pivot_middle if not np.isnan(pivot_middle) else close > pivot_s1):
                pivot_score += 7.0
                rationale_flags.append('PRICE_BETWEEN_S1_MID')
            if (not np.isnan(pivot_s2) and not np.isnan(close)) and (close > pivot_s2 and close < pivot_s1):
                pivot_score += 9.0
                rationale_flags.append('PRICE_BETWEEN_S2_S1')
            # If price already above R1 that's a breakout
            if (not np.isnan(pivot_r1) and not np.isnan(close)) and close > pivot_r1:
                pivot_score += 6.0
                rationale_flags.append('PRICE_ABOVE_R1')
        except Exception:
            pass
        pivot_score = min(pivot_score, 10.0)

        # Aggregate weighted score
        # weights: Trend 25, Momentum 25, MeanRev 15, VolBreak 15, Volume 10, Pivot 10
        total_score_raw = (trend_score) + (momentum_score) + (meanrev_score) + (vol_break_score) + (volume_score) + (
            pivot_score)
        # Normalize to 0-100 (sum of maxima is 100)
        signal_score = weighted_cap(total_score_raw, 100.0)

        # Conviction calculation (0-100)
        # 60% from normalized signal_score, 20% from Recommend.* consensus, 20% from ADX strength
        # Recommend aggregation
        recommend_all = safe('Recommend.All', row, np.nan)
        recommend_ma = safe('Recommend.MA', row, np.nan)
        recommend_other = safe('Recommend.Other', row, np.nan)

        rec_vals = [interpret_rec(recommend_all), interpret_rec(recommend_ma), interpret_rec(recommend_other)]
        rec_mean = np.nanmean(rec_vals) if len(rec_vals) > 0 else 0.0
        rec_score_component = float(np.clip(rec_mean, 0.0, 1.0))

        # ADX contribution: map ADX to 0..1 (20->0.4, 25->0.6, 40->1.0)
        adx_contrib = 0.0
        if not np.isnan(adx):
            if adx < 20:
                adx_contrib = 0.2 * (adx / 20.0)
            elif adx < 25:
                adx_contrib = 0.2 + 0.4 * ((adx - 20.0) / 5.0)
            else:
                # scale 25..60 -> 0.6..1.0
                adx_contrib = 0.6 + 0.4 * np.clip((adx - 25.0) / 35.0, 0.0, 1.0)
        # combine
        conviction = 0.60 * (signal_score) + 0.20 * (rec_score_component * 100.0) + 0.20 * (adx_contrib * 100.0)
        conviction = float(np.clip(conviction, 0.0, 100.0))

        # Determine trade type heuristically
        trade_type = 'NO_TRADE'
        if signal_score >= score_threshold:
            # pick best fitting trade type
            if macd_bull and (not np.isnan(close) and not np.isnan(pivot_r1)) and close > pivot_r1:
                trade_type = 'TREND_BREAKOUT'
            elif (not np.isnan(rsi) and rsi < rsi_meanrev_threshold) and (not np.isnan(ema50) and close > ema50):
                trade_type = 'MEAN_REVERT_IN_TREND'
            elif bbpower_norm < 0.4 and (not np.isnan(bb_width)) and volume > vwma_col:
                trade_type = 'VOLATILITY_BREAKOUT'
            elif (not np.isnan(pivot_s1) and close > pivot_s1 and safe('P.SAR', row, np.nan) == 'bullish'):
                trade_type = 'PIVOT_REVERSION'
            else:
                trade_type = 'MULTI_FACTOR'
        else:
            trade_type = 'NO_TRADE'

        # Entry price: default to close, could be adjusted for limit entries
        entry_price = float(close) if not np.isnan(close) else np.nan

        # Stop loss: use pivot_s1 if present, else entry - k*bb_width, else entry * 0.97 (3% fallback)
        stop_loss = np.nan
        if not np.isnan(pivot_s1):
            stop_loss = float(pivot_s1)
        elif not np.isnan(bb_width) and not np.isnan(entry_price):
            stop_loss = float(max(0.0, entry_price - bb_stop_k * bb_width))
        elif not np.isnan(entry_price):
            stop_loss = float(entry_price * 0.97)

        # Targets using BB width and pivot levels
        target_conservative = np.nan
        target_aggressive = np.nan
        if not np.isnan(pivot_r1):
            target_conservative = float(min(pivot_r1, entry_price + bb_target_cons_k * (
                bb_width if not np.isnan(bb_width) else entry_price * 0.02)))
        else:
            target_conservative = float(
                entry_price + bb_target_cons_k * (bb_width if not np.isnan(bb_width) else entry_price * 0.02))
        if not np.isnan(pivot_r2):
            target_aggressive = float(min(pivot_r2, entry_price + bb_target_agg_k * (
                bb_width if not np.isnan(bb_width) else entry_price * 0.03)))
        else:
            target_aggressive = float(
                entry_price + bb_target_agg_k * (bb_width if not np.isnan(bb_width) else entry_price * 0.03))

        # Position sizing (shares) based on risk per trade
        position_size_shares = np.nan
        position_size_value = np.nan
        if not np.isnan(entry_price) and not np.isnan(stop_loss) and (entry_price > stop_loss):
            risk_per_share = entry_price - stop_loss
            risk_amount = equity * risk_per_trade_pct
            position_size_shares = int(np.floor(risk_amount / risk_per_share)) if risk_per_share > 0 else 0
            position_size_value = position_size_shares * entry_price
        else:
            # if stop is greater or nan, default to small suggested value
            position_size_shares = 0
            position_size_value = 0.0

        # Confidence reason: short text explaining top contributors
        top_reasons = []
        if trend_score >= 20:
            top_reasons.append('TREND')
        if momentum_score >= 15:
            top_reasons.append('MOMENTUM')
        if meanrev_score >= 8:
            top_reasons.append('MEANREV')
        if vol_break_score >= 8:
            top_reasons.append('VOL_BREAK')
        if volume_score >= 6:
            top_reasons.append('VOLUME')

        confidence_reason = ','.join(top_reasons) if len(top_reasons) > 0 else 'LOW_SCORE'

        # expected holding days estimate: heuristic based on trade type & conviction
        if trade_type == 'TREND_BREAKOUT':
            expected_holding = int(np.clip(3 + (conviction / 20.0), 3, 30))  # 3..30 days
        elif trade_type == 'MEAN_REVERT_IN_TREND':
            expected_holding = int(np.clip(2 + (conviction / 30.0), 2, 14))
        elif trade_type == 'VOLATILITY_BREAKOUT':
            expected_holding = int(np.clip(3 + (conviction / 25.0), 3, 21))
        elif trade_type == 'PIVOT_REVERSION':
            expected_holding = int(np.clip(1 + (conviction / 50.0), 1, 10))
        else:
            expected_holding = int(np.clip(3 + (conviction / 33.0), 1, 30))

        # Build output row
        out = {
            'symbol': symbol,
            'signal_score': round(float(signal_score), 2),
            'conviction': round(float(conviction), 2),
            'entry_price': entry_price,
            'stop_loss': round(stop_loss, 6) if not np.isnan(stop_loss) else np.nan,
            'target_conservative': round(target_conservative, 6) if not np.isnan(target_conservative) else np.nan,
            'target_aggressive': round(target_aggressive, 6) if not np.isnan(target_aggressive) else np.nan,
            'trade_type': trade_type,
            'rationale_flags': ';'.join(list(dict.fromkeys(rationale_flags))) if rationale_flags else '',
            'confidence_reason': confidence_reason,
            'expected_holding_days_estimate': int(expected_holding),
            'position_size_shares': int(position_size_shares),
            'position_size_value': float(position_size_value)
        }
        rows_out.append(out)

    signals_df = pd.DataFrame(rows_out)
    # sort by signal_score desc then conviction
    if 'signal_score' in signals_df.columns:
        signals_df = signals_df.sort_values(by=['signal_score', 'conviction'], ascending=False).reset_index(drop=True)

    return signals_df

if __name__ == "__main__":
    """
    Keep the main for testing purposes
    """

    import time
    import logging
    from src.logger_config import setup_logging
    from src.database import select_into_dataframe

    start = time.time()
    sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'atlas_multi_signal_alpha.sql'

    df = select_into_dataframe(sql_file_path=sql_file_path)
    df = calculate_atlas_multi_signal_alpha_strategy(df)
    ende = time.time()

