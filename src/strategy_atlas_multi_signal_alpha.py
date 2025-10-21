import logging
from src.logger_config import setup_logging
import pandas as pd
import numpy as np
from config import *
from src.decorator_log_function import log_function
from enum import Enum
from dataclasses import dataclass

setup_logging(log_file=PATH_LOG_FILE, log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(__name__)
logger.info(f"Start {__name__} ({__file__})")


class TradeType(Enum):
    NO_TRADE = "NO_TRADE"
    TREND_BREAKOUT = "TREND_BREAKOUT"
    MEAN_REVERT_IN_TREND = "MEAN_REVERT_IN_TREND"
    VOLATILITY_BREAKOUT = "VOLATILITY_BREAKOUT"
    PIVOT_REVERSION = "PIVOT_REVERSION"
    MULTI_FACTOR = "MULTI_FACTOR"
    DIRECTIONAL_ALIGNMENT = "DIRECTIONAL_ALIGNMENT"


@dataclass
class SignalConfig:
    """Optimierte Parameter für maximale Profitabilität"""
    score_threshold: float = 68.0
    adx_trend_threshold: float = 20.0
    di_difference_threshold: float = 10.0  # ADX+DI vs ADX-DI
    rsi_meanrev_threshold: float = 28.0
    rsi_overbought_threshold: float = 72.0
    stoch_oversold: float = 20.0
    stoch_overbought: float = 80.0
    wr_oversold: float = -80.0  # Williams %R
    uo_threshold: float = 30.0  # Ultimate Oscillator
    bb_stop_k: float = 1.3
    bb_target_cons_k: float = 2.0
    bb_target_agg_k: float = 3.0
    min_trend_strength: float = 0.7
    max_position_size_pct: float = 0.015
    psar_confirmation_weight: float = 0.15  # Parabolic SAR Weight


def safe(colname, row, default=np.nan):
    return row.get(colname, default)


def norm01(x, minv, maxv):
    if np.isnan(x):
        return 0.5
    if maxv == minv:
        return 0.5
    return float(np.clip((x - minv) / (maxv - minv), 0.0, 1.0))


def weighted_cap(score, cap=100):
    return float(np.clip(score, 0, cap))


def col_percentile(col, df, percentile_low=5, percentile_high=95):
    if col in df.columns:
        vals = pd.to_numeric(df[col], errors='coerce').dropna()
        if len(vals) == 0:
            return (0.0, 1.0)
        return (np.percentile(vals, percentile_low), np.percentile(vals, percentile_high))
    return (0.0, 1.0)


def interpret_rec_enhanced(x, recommendation_type="all"):
    """Intelligente Recommendation-Interpretation"""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return 0.0
    if isinstance(x, (int, float, np.number)):
        return float(np.clip(x / 5.0, 0.0, 1.0))
    xs = str(x).lower().strip()
    if 'strong buy' in xs:
        return 1.0
    if 'buy' in xs:
        return 0.8
    if 'strong sell' in xs:
        return 0.0
    if 'sell' in xs:
        return 0.15
    if 'neutral' in xs or 'hold' in xs:
        return 0.5
    try:
        return float(np.clip(float(xs) / 5.0, 0.0, 1.0))
    except:
        return 0.0


def check_directional_alignment(ema5, ema10, ema20, ema50, ema100, ema200, close, vwma):
    """Prüfe Alignment aller Moving Averages (0..1)"""
    alignment_score = 0.0
    count = 0

    # Aufsteigend ordnen
    mas = [ema5, ema10, ema20, ema50, ema100, ema200, vwma]
    mas_clean = [m for m in mas if not np.isnan(m)]

    if len(mas_clean) >= 3:
        # Prüfe ob sortiert (für Uptrend)
        is_ascending = all(mas_clean[i] < mas_clean[i + 1] for i in range(len(mas_clean) - 1))
        if is_ascending:
            alignment_score = min(1.0, len(mas_clean) / 7.0)

    # Close oberhalb aller MAs?
    above_mas = sum(1 for m in mas_clean if not np.isnan(m) and close > m)
    ma_proximity = above_mas / len(mas_clean) if mas_clean else 0.0

    return min(1.0, 0.6 * alignment_score + 0.4 * ma_proximity)


def calculate_multiple_indicators_consensus(
        rsi, stoch_k, cci, wr, uo, bbpower, macd_val, macd_sig, ao, mom
):
    """Berechne Konsens aus ALLEN Oszillatoren"""
    bullish_count = 0
    total_count = 0
    scores = []

    # RSI (> 50 = bullish, < 30 = oversold buy)
    if not np.isnan(rsi):
        total_count += 1
        if rsi > 55:
            bullish_count += 1
            scores.append(0.8)
        elif rsi > 50:
            scores.append(0.6)
        elif rsi < 30:
            scores.append(0.4)  # Oversold
        elif rsi < 35:
            scores.append(0.45)
        else:
            scores.append(0.5)

    # Stochastic K (> 50 = bullish)
    if not np.isnan(stoch_k):
        total_count += 1
        if stoch_k > 60:
            bullish_count += 1
            scores.append(0.8)
        elif stoch_k > 50:
            scores.append(0.65)
        elif stoch_k < 20:
            scores.append(0.3)  # Oversold
        else:
            scores.append(0.5)

    # CCI (> 0 = bullish, > 100 = overbought)
    if not np.isnan(cci):
        total_count += 1
        if cci > 100:
            scores.append(0.7)
            bullish_count += 1
        elif cci > 0:
            scores.append(0.65)
            bullish_count += 1
        elif cci < -100:
            scores.append(0.2)  # Oversold
        else:
            scores.append(0.5)

    # Williams %R (höher/näher 0 = bullish, < -80 = oversold)
    if not np.isnan(wr):
        total_count += 1
        if wr > -50:
            bullish_count += 1
            scores.append(0.75)
        elif wr > -80:
            scores.append(0.6)
        elif wr < -80:
            scores.append(0.25)  # Oversold
        else:
            scores.append(0.5)

    # Ultimate Oscillator (> 50 = bullish)
    if not np.isnan(uo):
        total_count += 1
        if uo > 70:
            bullish_count += 1
            scores.append(0.85)
        elif uo > 50:
            bullish_count += 1
            scores.append(0.7)
        elif uo < 30:
            scores.append(0.3)
        else:
            scores.append(0.5)

    # BBPower (normalisiert 0..1)
    if not np.isnan(bbpower):
        total_count += 1
        bbpower_norm = np.clip(bbpower, -1, 1)
        if bbpower_norm > 0.2:
            bullish_count += 1
        scores.append((bbpower_norm + 1) / 2)  # Normalisiere auf 0..1

    # MACD (bullish wenn macd > signal)
    if not np.isnan(macd_val) and not np.isnan(macd_sig):
        total_count += 1
        if macd_val > macd_sig:
            bullish_count += 1
            scores.append(0.8)
        else:
            scores.append(0.3)

    # AO (Awesome Oscillator, > 0 = bullish)
    if not np.isnan(ao):
        total_count += 1
        if ao > 0:
            bullish_count += 1
            scores.append(0.7)
        elif ao > -0.001:
            scores.append(0.5)
        else:
            scores.append(0.2)

    # Momentum (> 0 = bullish)
    if not np.isnan(mom):
        total_count += 1
        if mom > 0:
            bullish_count += 1
            scores.append(0.7)
        else:
            scores.append(0.3)

    consensus_score = np.mean(scores) if scores else 0.5
    bullish_ratio = bullish_count / total_count if total_count > 0 else 0.5

    return consensus_score, bullish_ratio, total_count


def detect_reversal_patterns(rsi, rsi1, stoch_k, stoch_k1, cci, cci1, close, low, bb_lower):
    """Erkenne Reversal-Patterns für Mean Reversion"""
    reversal_strength = 0.0

    # RSI divergence & bottoming
    if not np.isnan(rsi) and not np.isnan(rsi1):
        if rsi < 25 and rsi > rsi1:  # Extremer Oversold + Rising
            reversal_strength += 0.30
        elif rsi < 35 and rsi > rsi1:
            reversal_strength += 0.15

    # Stoch crossing
    if not np.isnan(stoch_k) and not np.isnan(stoch_k1):
        if stoch_k < 20 and stoch_k > stoch_k1:
            reversal_strength += 0.25

    # CCI extremum
    if not np.isnan(cci) and not np.isnan(cci1):
        if cci < -150:  # Extreme oversold
            reversal_strength += 0.20
        elif cci < -100 and cci > cci1:
            reversal_strength += 0.10

    # Price touching lower BB
    if not np.isnan(close) and not np.isnan(low) and not np.isnan(bb_lower):
        if low <= bb_lower and close > bb_lower * 1.005:  # Touched aber recovered
            reversal_strength += 0.15

    return min(1.0, reversal_strength)


def detect_breakout_patterns(close, high, bb_upper, bb_lower, volume, vwma_vol, psar, macd_val, macd_sig):
    """Erkenne Breakout-Patterns"""
    breakout_strength = 0.0

    # Price above upper BB
    if not np.isnan(close) and not np.isnan(bb_upper) and close > bb_upper:
        breakout_strength += 0.30

    # Price making new high
    if not np.isnan(high) and not np.isnan(close) and high >= close * 0.995:
        breakout_strength += 0.15

    # Volume confirmation
    if not np.isnan(volume) and not np.isnan(vwma_vol) and volume > vwma_vol * 1.3:
        breakout_strength += 0.25

    # MACD bullish
    if not np.isnan(macd_val) and not np.isnan(macd_sig) and macd_val > macd_sig:
        breakout_strength += 0.15

    # Parabolic SAR bullish
    if isinstance(psar, str) and 'bullish' in str(psar).lower():
        breakout_strength += 0.15

    return min(1.0, breakout_strength)


@log_function
def calculate_atlas_multi_signal_alpha_strategy(
        df: pd.DataFrame,
        equity: float = 100000.0,
        risk_per_trade_pct: float = 0.005,
        config: SignalConfig = None):
    """
    ELITE Multi-Factor Strategy mit ALLEN verfügbaren Indikatoren.

    Key Improvements:
    - Multiple Indicators Consensus (10+ Oszillatoren)
    - Directional Alignment aller Moving Averages
    - Parabolic SAR Confirmation
    - ADX Directional Components (DI+ vs DI-)
    - Williams %R, Ultimate Oscillator Integration
    - Multiple Pivot Systems
    - Stochastic RSI & W%R Recommendations
    - Advanced Pattern Detection (Reversal + Breakout)
    """
    if config is None:
        config = SignalConfig()

    df.to_csv("debug_input.csv", index=False)

    rows_out = []

    # Globale Baselines
    ao_min, ao_max = col_percentile('AO', df)
    bbpower_min, bbpower_max = col_percentile('BBPower', df)
    volume_min, volume_max = col_percentile('volume', df)
    adx_min, adx_max = col_percentile('ADX', df)
    uo_min, uo_max = col_percentile('UO', df)
    di_diff_min, di_diff_max = col_percentile('ADX+DI', df)

    for _, row_series in df.iterrows():
        row = row_series.to_dict()
        symbol = safe('symbol', row, 'UNKNOWN')
        close = safe('close', row, np.nan)
        open_p = safe('open', row, np.nan)
        high = safe('high', row, np.nan)
        low = safe('low', row, np.nan)
        change = safe('change', row, np.nan)
        psar = safe('P.SAR', row, None)

        # === MOVING AVERAGES (alle laden) ===
        ema5 = safe('EMA5', row, np.nan)
        ema10 = safe('EMA10', row, np.nan)
        ema20 = safe('EMA20', row, np.nan)
        ema50 = safe('EMA50', row, np.nan)
        ema100 = safe('EMA100', row, np.nan)
        ema200 = safe('EMA200', row, np.nan)
        sma5 = safe('SMA5', row, np.nan)
        sma20 = safe('SMA20', row, np.nan)
        sma50 = safe('SMA50', row, np.nan)
        sma200 = safe('SMA200', row, np.nan)
        vwma = safe('VWMA', row, np.nan)
        hull9 = safe('HullMA9', row, np.nan)
        ichimoku_bline = safe('Ichimoku.BLine', row, np.nan)

        # === MOMENTUM OSCILLATORS ===
        rsi = safe('RSI', row, np.nan)
        rsi1 = safe('RSI[1]', row, np.nan)

        stoch_k = safe('Stoch.K', row, np.nan)
        stoch_d = safe('Stoch.D', row, np.nan)
        stoch_k1 = safe('Stoch.K[1]', row, np.nan)
        stoch_d1 = safe('Stoch.D[1]', row, np.nan)
        stoch_rsi_k = safe('Stoch.RSI.K', row, np.nan)

        cci = safe('CCI20', row, np.nan)
        cci1 = safe('CCI20[1]', row, np.nan)

        wr = safe('W.R', row, np.nan)

        uo = safe('UO', row, np.nan)

        bbpower = safe('BBPower', row, np.nan)

        # === MACD & MOMENTUM ===
        macd_val = safe('MACD.macd', row, np.nan)
        macd_sig = safe('MACD.signal', row, np.nan)
        macd_hist = safe('MACD.histogram', row, np.nan) if 'MACD.histogram' in row else np.nan

        ao = safe('AO', row, np.nan)
        ao1 = safe('AO[1]', row, np.nan)
        ao2 = safe('AO[2]', row, np.nan)

        mom = safe('Mom', row, np.nan)
        mom1 = safe('Mom[1]', row, np.nan)

        # === ADX & DIREKTIONALE KOMPONENTEN ===
        adx = safe('ADX', row, np.nan)
        di_plus = safe('ADX+DI', row, np.nan)
        di_minus = safe('ADX-DI', row, np.nan)
        di_plus1 = safe('ADX+DI[1]', row, np.nan)
        di_minus1 = safe('ADX-DI[1]', row, np.nan)

        di_difference = (di_plus - di_minus) if (not np.isnan(di_plus) and not np.isnan(di_minus)) else np.nan
        di_crossing_bullish = False
        if not np.isnan(di_plus) and not np.isnan(di_minus) and not np.isnan(di_plus1) and not np.isnan(di_minus1):
            di_crossing_bullish = (di_plus1 <= di_minus1) and (di_plus > di_minus)

        # === BOLLINGER BANDS ===
        bb_upper = safe('BB.upper', row, np.nan)
        bb_lower = safe('BB.lower', row, np.nan)
        bb_middle = (bb_upper + bb_lower) / 2 if (not np.isnan(bb_upper) and not np.isnan(bb_lower)) else np.nan
        bb_width = (bb_upper - bb_lower) if (not np.isnan(bb_upper) and not np.isnan(bb_lower)) else np.nan

        # === PIVOT SYSTEMS ===
        pivot_systems = {
            'Classic': {
                'M': safe('Pivot.M.Classic.Middle', row, np.nan),
                'R1': safe('Pivot.M.Classic.R1', row, np.nan),
                'R2': safe('Pivot.M.Classic.R2', row, np.nan),
                'R3': safe('Pivot.M.Classic.R3', row, np.nan),
                'S1': safe('Pivot.M.Classic.S1', row, np.nan),
                'S2': safe('Pivot.M.Classic.S2', row, np.nan),
                'S3': safe('Pivot.M.Classic.S3', row, np.nan),
            },
            'Fibonacci': {
                'M': safe('Pivot.M.Fibonacci.Middle', row, np.nan),
                'R1': safe('Pivot.M.Fibonacci.R1', row, np.nan),
                'R2': safe('Pivot.M.Fibonacci.R2', row, np.nan),
                'R3': safe('Pivot.M.Fibonacci.R3', row, np.nan),
                'S1': safe('Pivot.M.Fibonacci.S1', row, np.nan),
                'S2': safe('Pivot.M.Fibonacci.S2', row, np.nan),
                'S3': safe('Pivot.M.Fibonacci.S3', row, np.nan),
            },
            'Camarilla': {
                'M': safe('Pivot.M.Camarilla.Middle', row, np.nan),
                'R1': safe('Pivot.M.Camarilla.R1', row, np.nan),
                'R2': safe('Pivot.M.Camarilla.R2', row, np.nan),
                'S1': safe('Pivot.M.Camarilla.S1', row, np.nan),
                'S2': safe('Pivot.M.Camarilla.S2', row, np.nan),
            },
            'Demark': {
                'M': safe('Pivot.M.Demark.Middle', row, np.nan),
                'R1': safe('Pivot.M.Demark.R1', row, np.nan),
                'S1': safe('Pivot.M.Demark.S1', row, np.nan),
            }
        }

        # Nutze Classic, fallback zu anderen
        pivot_middle = pivot_systems['Classic']['M']
        if np.isnan(pivot_middle):
            pivot_middle = pivot_systems['Fibonacci']['M']

        pivot_r1 = pivot_systems['Classic']['R1'] or pivot_systems['Fibonacci']['R1']
        pivot_r2 = pivot_systems['Classic']['R2'] or pivot_systems['Fibonacci']['R2']
        pivot_s1 = pivot_systems['Classic']['S1'] or pivot_systems['Fibonacci']['S1']
        pivot_s2 = pivot_systems['Classic']['S2'] or pivot_systems['Fibonacci']['S2']

        # === VOLUME ===
        volume = safe('volume', row, np.nan)
        volume1 = safe('volume', row, np.nan)  # Wenn nicht vorhanden, wird np.nan
        vol_avg = np.nanmean([volume, volume1]) if not (np.isnan(volume) and np.isnan(volume1)) else np.nan

        # === RECOMMENDATIONS ===
        rec_all = safe('Recommend.All', row, np.nan)
        rec_ma = safe('Recommend.MA', row, np.nan)
        rec_other = safe('Recommend.Other', row, np.nan)
        rec_ichimoku = safe('Rec.Ichimoku', row, np.nan)
        rec_stoch_rsi = safe('Rec.Stoch.RSI', row, np.nan)
        rec_wr = safe('Rec.WR', row, np.nan)
        rec_bbpower = safe('Rec.BBPower', row, np.nan)
        rec_uo = safe('Rec.UO', row, np.nan)
        rec_vwma = safe('Rec.VWMA', row, np.nan)
        rec_hull = safe('Rec.HullMA9', row, np.nan)

        # === SCORING ===
        trend_score = 0.0
        momentum_score = 0.0
        meanrev_score = 0.0
        vol_break_score = 0.0
        volume_score = 0.0
        pivot_score = 0.0
        pattern_score = 0.0
        di_score = 0.0
        consensus_score = 0.0
        rationale_flags = []

        # --- 1. DIRECTIONAL ALIGNMENT (Max 25 Punkte) ---
        try:
            alignment = check_directional_alignment(ema5, ema10, ema20, ema50, ema100, ema200, close, vwma)
            trend_score += 25.0 * alignment

            if alignment > 0.85:
                trend_score += 5.0
                rationale_flags.append('PERFECT_MA_ALIGNMENT')
            elif alignment > 0.7:
                rationale_flags.append('STRONG_MA_ALIGNMENT')

            # Hull MA als zusätzliches Filter
            if not np.isnan(hull9) and close > hull9:
                if not np.isnan(ema50) and hull9 > ema50:
                    trend_score += 8.0
                    rationale_flags.append('HULL_ABOVE_EMA50')
        except Exception as e:
            logger.warning(f"Alignment Error: {e}")

        # --- 2. ADX & DIRECTIONAL COMPONENTS (Max 20 Punkte) ---
        try:
            if not np.isnan(adx):
                if adx >= config.adx_trend_threshold:
                    adx_norm = norm01(adx, 20.0, 60.0)
                    trend_score += 15.0 * adx_norm
                    rationale_flags.append('ADX_STRONG')

            # DI+ über DI- ist bullish
            if not np.isnan(di_plus) and not np.isnan(di_minus):
                if di_plus > di_minus + config.di_difference_threshold:
                    di_score += 12.0
                    rationale_flags.append('DI_PLUS_DOMINANT')
                elif di_plus > di_minus:
                    di_score += 6.0
                    rationale_flags.append('DI_PLUS_HIGHER')

            # DI Crossing
            if di_crossing_bullish:
                di_score += 8.0
                rationale_flags.append('DI_BULLISH_CROSS')

            trend_score += di_score
        except Exception as e:
            logger.warning(f"ADX Error: {e}")

        trend_score = min(trend_score, 35.0)

        # --- 3. MULTIPLE INDICATORS CONSENSUS (Max 30 Punkte) ---
        try:
            consensus, bullish_ratio, indicator_count = calculate_multiple_indicators_consensus(
                rsi, stoch_k, cci, wr, uo, bbpower, macd_val, macd_sig, ao, mom
            )

            consensus_score = 30.0 * consensus

            # Bonus für viele bullish Indikatoren
            if bullish_ratio >= 0.75 and indicator_count >= 8:
                consensus_score += 8.0
                rationale_flags.append('STRONG_INDICATOR_CONSENSUS')
            elif bullish_ratio >= 0.6 and indicator_count >= 6:
                rationale_flags.append('GOOD_INDICATOR_ALIGNMENT')

            momentum_score += consensus_score
        except Exception as e:
            logger.warning(f"Consensus Error: {e}")

        # --- 4. PARABOLIC SAR CONFIRMATION (Max 10 Punkte) ---
        try:
            if isinstance(psar, str) and 'bullish' in str(psar).lower():
                momentum_score += 10.0
                rationale_flags.append('PSAR_BULLISH')
            elif not np.isnan(psar):
                psar_float = float(psar) if psar else np.nan
                if not np.isnan(psar_float) and close > psar_float:
                    momentum_score += 5.0
                    rationale_flags.append('PRICE_ABOVE_SAR')
        except Exception as e:
            logger.warning(f"SAR Error: {e}")

        momentum_score = min(momentum_score, 40.0)

        # --- 5. REVERSAL PATTERN DETECTION (Max 15 Punkte) ---
        try:
            reversal_strength = detect_reversal_patterns(rsi, rsi1, stoch_k, stoch_k1, cci, cci1, close, low, bb_lower)
            meanrev_score += 15.0 * reversal_strength

            if reversal_strength > 0.7:
                rationale_flags.append('STRONG_REVERSAL_SETUP')
            elif reversal_strength > 0.4:
                rationale_flags.append('REVERSAL_FORMING')
        except Exception as e:
            logger.warning(f"Reversal Error: {e}")

        meanrev_score = min(meanrev_score, 18.0)

        # --- 6. BREAKOUT PATTERN DETECTION (Max 18 Punkte) ---
        try:
            breakout_strength = detect_breakout_patterns(close, high, bb_upper, bb_lower, volume, vwma, psar, macd_val,
                                                         macd_sig)
            vol_break_score += 18.0 * breakout_strength

            if breakout_strength > 0.8:
                rationale_flags.append('STRONG_BREAKOUT_SETUP')
            elif breakout_strength > 0.5:
                rationale_flags.append('BREAKOUT_FORMING')
        except Exception as e:
            logger.warning(f"Breakout Error: {e}")

        vol_break_score = min(vol_break_score, 20.0)

        # --- 7. VOLUME CONFIRMATION (Max 10 Punkte) ---
        try:
            if not np.isnan(volume) and not np.isnan(vwma):
                if volume > vwma * 1.25:
                    volume_score += 10.0
                    rationale_flags.append('VOLUME_SPIKE')
                elif volume > vwma:
                    volume_score += 6.0
                    rationale_flags.append('VOLUME_ABOVE_AVG')
        except Exception as e:
            logger.warning(f"Volume Error: {e}")

        volume_score = min(volume_score, 10.0)

        # --- 8. PIVOT LEVELS & SUPPORT/RESISTANCE (Max 12 Punkte) ---
        try:
            pivot_r1_vals = [pivot_systems[sys]['R1'] for sys in pivot_systems if
                             not np.isnan(pivot_systems[sys]['R1'])]
            pivot_s1_vals = [pivot_systems[sys]['S1'] for sys in pivot_systems if
                             not np.isnan(pivot_systems[sys]['S1'])]

            if pivot_r1_vals and close > np.mean(pivot_r1_vals):
                pivot_score += 8.0
                rationale_flags.append('ABOVE_RESISTANCE')

            if pivot_s1_vals and close > np.mean(pivot_s1_vals):
                pivot_score += 6.0
                rationale_flags.append('ABOVE_SUPPORT')
        except Exception as e:
            logger.warning(f"Pivot Error: {e}")

        pivot_score = min(pivot_score, 12.0)

        # --- 9. RECOMMENDATION AGGREGATION (Max 8 Punkte) ---
        try:
            rec_scores = [
                interpret_rec_enhanced(rec_all),
                interpret_rec_enhanced(rec_ma),
                interpret_rec_enhanced(rec_other),
                interpret_rec_enhanced(rec_ichimoku),
                interpret_rec_enhanced(rec_stoch_rsi),
                interpret_rec_enhanced(rec_wr),
                interpret_rec_enhanced(rec_bbpower),
                interpret_rec_enhanced(rec_uo),
            ]

            rec_scores_clean = [s for s in rec_scores if not np.isnan(s) and s > 0]
            if rec_scores_clean:
                rec_mean = np.mean(rec_scores_clean)
                momentum_score += 8.0 * rec_mean

                if rec_mean > 0.75:
                    rationale_flags.append('REC_STRONG_BUY')
                elif rec_mean > 0.6:
                    rationale_flags.append('REC_BUY')
        except Exception as e:
            logger.warning(f"Recommendation Error: {e}")

        # === AGGREGATE SCORE ===
        total_score_raw = (trend_score + momentum_score + meanrev_score + vol_break_score +
                           volume_score + pivot_score)
        signal_score = weighted_cap(total_score_raw, 100.0)

        # Trend muss stabil sein
        trend_requirement_met = trend_score >= 20.0

        # === CONVICTION (0-100) ===
        # 50% Signal Score, 30% Recommendations, 20% ADX Stärke
        adx_norm = norm01(adx, 15.0, 50.0) if not np.isnan(adx) else 0.5

        conviction = (0.50 * signal_score +
                      0.30 * (np.mean([s for s in rec_scores if not np.isnan(s)]) * 100 if rec_scores else 50) +
                      0.20 * (adx_norm * 100))
        conviction = float(np.clip(conviction, 0.0, 100.0))

        # === TRADE TYPE DETERMINATION ===
        trade_type = TradeType.NO_TRADE.value

        if signal_score >= config.score_threshold and trend_requirement_met:
            # Priorisiere nach Pattern
            breakout_strength = detect_breakout_patterns(close, high, bb_upper, bb_lower, volume, vwma, psar, macd_val,
                                                         macd_sig)
            reversal_strength = detect_reversal_patterns(rsi, rsi1, stoch_k, stoch_k1, cci, cci1, close, low, bb_lower)

            if breakout_strength > 0.65 and not np.isnan(macd_val) and macd_val > macd_sig:
                trade_type = TradeType.TREND_BREAKOUT.value
            elif reversal_strength > 0.6 and not np.isnan(rsi) and rsi < config.rsi_meanrev_threshold:
                trade_type = TradeType.MEAN_REVERT_IN_TREND.value
            elif vol_break_score >= 12.0:
                trade_type = TradeType.VOLATILITY_BREAKOUT.value
            elif consensus > 0.70:
                trade_type = TradeType.DIRECTIONAL_ALIGNMENT.value
            else:
                trade_type = TradeType.MULTI_FACTOR.value

        # === ENTRY / STOP / TARGET ===
        entry_price = float(close) if not np.isnan(close) else np.nan

        # Stop Loss: Mehrschichtiges System
        stop_loss = np.nan
        stops_to_consider = []

        # Pivot S1/S2
        if not np.isnan(pivot_s1) and pivot_s1 < entry_price:
            stops_to_consider.append(float(pivot_s1) * 0.98)  # Leicht unter Pivot

        # Ichimoku Kijun
        if not np.isnan(ichimoku_bline) and ichimoku_bline < entry_price:
            stops_to_consider.append(float(ichimoku_bline) * 0.98)

        # Lower Bollinger Band
        if not np.isnan(bb_lower) and bb_lower < entry_price:
            stops_to_consider.append(float(bb_lower) * 0.97)

        # EMA200 (Long-term)
        if not np.isnan(ema200) and ema200 < entry_price:
            stops_to_consider.append(float(ema200) * 0.99)

        # Wähle höchsten Stop (beste Balance zwischen Schutz & Reversal-Raum)
        if stops_to_consider:
            stop_loss = max(stops_to_consider)
        elif not np.isnan(bb_width) and not np.isnan(entry_price):
            stop_loss = float(max(0.01, entry_price - config.bb_stop_k * bb_width))
        elif not np.isnan(entry_price):
            stop_loss = float(entry_price * 0.94)

        # === TARGETS (mehrere Szenarien) ===
        target_conservative = np.nan
        target_aggressive = np.nan

        if not np.isnan(entry_price) and not np.isnan(stop_loss) and entry_price > stop_loss:
            risk = entry_price - stop_loss

            # Target 1: Pivot R1 oder 1.5x Risk
            if not np.isnan(pivot_r1) and pivot_r1 > entry_price:
                target_conservative = float(pivot_r1)
            else:
                target_conservative = float(entry_price + 1.5 * risk)

            # Target 2: Pivot R2 oder 3x Risk
            if not np.isnan(pivot_r2) and pivot_r2 > entry_price:
                target_aggressive = float(pivot_r2)
            else:
                target_aggressive = float(entry_price + 3.0 * risk)

        # === POSITION SIZING (risikoadjustiert) ===
        position_size_shares = 0
        position_size_value = 0.0

        if (not np.isnan(entry_price) and not np.isnan(stop_loss) and
                entry_price > stop_loss and trade_type != TradeType.NO_TRADE.value):

            risk_per_share = entry_price - stop_loss
            max_risk_amount = equity * min(risk_per_trade_pct, config.max_position_size_pct)

            # Conviction-Multiplikator (höhere Conviction = mehr Risiko)
            conviction_multiplier = 0.5 + (conviction / 200.0)  # 0.5..1.0
            adjusted_risk = max_risk_amount * conviction_multiplier

            if risk_per_share > 0:
                position_size_shares = int(np.floor(adjusted_risk / risk_per_share))
                position_size_value = position_size_shares * entry_price

        # === CONFIDENCE REASON ===
        top_reasons = []
        if trend_score >= 25:
            top_reasons.append('TREND')
        if consensus_score >= 20:
            top_reasons.append('CONSENSUS')
        if meanrev_score >= 10:
            top_reasons.append('REVERSAL')
        if vol_break_score >= 12:
            top_reasons.append('BREAKOUT')
        if di_score >= 8:
            top_reasons.append('DI_STRONG')
        if volume_score >= 8:
            top_reasons.append('VOLUME')

        confidence_reason = ','.join(top_reasons) if top_reasons else 'WEAK'

        # === EXPECTED HOLDING DAYS ===
        expected_holding = 5
        if trade_type == TradeType.TREND_BREAKOUT.value:
            expected_holding = int(np.clip(7 + conviction / 12.0, 7, 50))
        elif trade_type == TradeType.MEAN_REVERT_IN_TREND.value:
            expected_holding = int(np.clip(2 + conviction / 25.0, 2, 14))
        elif trade_type == TradeType.VOLATILITY_BREAKOUT.value:
            expected_holding = int(np.clip(4 + conviction / 20.0, 4, 25))
        elif trade_type == TradeType.DIRECTIONAL_ALIGNMENT.value:
            expected_holding = int(np.clip(5 + conviction / 18.0, 5, 30))
        else:
            expected_holding = int(np.clip(4 + conviction / 22.0, 2, 30))

        # === RISK/REWARD ===
        rr_ratio = np.nan
        if not np.isnan(entry_price) and not np.isnan(stop_loss) and not np.isnan(target_conservative):
            if entry_price > stop_loss:
                rr_ratio = (target_conservative - entry_price) / (entry_price - stop_loss)

        # === OUTPUT ===
        out = {
            'symbol': symbol,
            'signal_score': round(float(signal_score), 2),
            'conviction': round(float(conviction), 2),
            'entry_price': round(entry_price, 6) if not np.isnan(entry_price) else np.nan,
            'stop_loss': round(stop_loss, 6) if not np.isnan(stop_loss) else np.nan,
            'target_conservative': round(target_conservative, 6) if not np.isnan(target_conservative) else np.nan,
            'target_aggressive': round(target_aggressive, 6) if not np.isnan(target_aggressive) else np.nan,
            'trade_type': trade_type,
            'rationale_flags': ';'.join(list(dict.fromkeys(rationale_flags))) if rationale_flags else 'NONE',
            'confidence_reason': confidence_reason,
            'expected_holding_days_estimate': int(expected_holding),
            'position_size_shares': int(position_size_shares),
            'position_size_value': round(float(position_size_value), 2),
            'risk_reward_ratio': round(rr_ratio, 2) if not np.isnan(rr_ratio) else np.nan,
            'trend_score': round(trend_score, 2),
            'momentum_score': round(momentum_score, 2),
            'consensus_strength': round(bullish_ratio * 100, 2) if 'bullish_ratio' in locals() else np.nan,
            'di_dominance': round(di_score, 2),
            'pattern_quality': round(max(breakout_strength, reversal_strength) * 100,
                                     2) if 'breakout_strength' in locals() else np.nan,
        }

        rows_out.append(out)

    signals_df = pd.DataFrame(rows_out)

    # Sortierung: Erst Trade Type, dann Risk/Reward, dann Score
    trade_type_order = {
        'TREND_BREAKOUT': 0,
        'VOLATILITY_BREAKOUT': 1,
        'MEAN_REVERT_IN_TREND': 2,
        'DIRECTIONAL_ALIGNMENT': 3,
        'MULTI_FACTOR': 4,
        'NO_TRADE': 999
    }
    signals_df['_trade_order'] = signals_df['trade_type'].map(trade_type_order)

    signals_df = (signals_df.sort_values(
        by=['_trade_order', 'risk_reward_ratio', 'signal_score', 'conviction'],
        ascending=[True, False, False, False],
        na_position='last'
    ).drop('_trade_order', axis=1).reset_index(drop=True))

    # Logging
    trade_count = len(signals_df[signals_df['trade_type'] != 'NO_TRADE'])
    avg_rr = signals_df[signals_df['trade_type'] != 'NO_TRADE']['risk_reward_ratio'].mean()

    logger.info(f"Generated {len(signals_df)} signals. Tradeable: {trade_count}. Avg R:R: {avg_rr:.2f}")
    logger.info(f"Signal Distribution: {signals_df['trade_type'].value_counts().to_dict()}")

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

