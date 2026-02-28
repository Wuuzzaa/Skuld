import math
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# ── DTE mapping for holding period ──────────────────────────────────
HOLDING_PERIOD_MAP = {
    "short": {"dte_range": (30, 90), "target_dte": 60},
    "medium": {"dte_range": (90, 180), "target_dte": 135},
    "long": {"dte_range": (180, 365), "target_dte": 270},
    "any": {"dte_range": (7, 730), "target_dte": None},  # No preference penalty
}

DEFAULT_WEIGHTS = {
    "cost": 0.30,
    "protection": 0.25,
    "liquidity": 0.15,
    "dte_match": 0.15,
    "time_value": 0.15,
}


def apply_quality_filters(
    df: pd.DataFrame,
    min_open_interest: int = 10,
    min_dte: int = 7,
    max_insurance_cost_pct: float = 20.0,
    min_abs_delta: float = 0.01,
) -> tuple[pd.DataFrame, dict]:
    """
    Applies Quality-Gate filters to remove unusable options.

    Hard filters (always applied):
        - open_interest > 0
        - days_to_expiration >= 7
        - option_price > 0
        - contract_type == 'put'

    Soft filters (configurable):
        - open_interest >= min_open_interest
        - insurance_cost_pct <= max_insurance_cost_pct
        - abs(greeks_delta) >= min_abs_delta  (if column exists)

    Args:
        df: DataFrame with put options including calculated metrics.
        min_open_interest: Minimum open interest (soft, default 10).
        min_dte: Minimum days to expiration (hard, default 7).
        max_insurance_cost_pct: Max insurance cost % (soft, default 20).
        min_abs_delta: Min absolute delta (soft, default 0.01).

    Returns:
        Tuple of (filtered DataFrame, statistics dict for UI transparency).
    """
    stats = {"total": len(df)}

    if df.empty:
        stats.update({"removed_oi_zero": 0, "removed_dte": 0, "removed_price": 0,
                       "removed_oi_low": 0, "removed_cost": 0, "removed_delta": 0,
                       "remaining": 0})
        return df, stats

    # ── Hard filters ────────────────────────────────────────────────
    mask_oi_zero = df['open_interest'] <= 0
    stats["removed_oi_zero"] = int(mask_oi_zero.sum())
    df = df[~mask_oi_zero]

    mask_dte = df['days_to_expiration'] < min_dte
    stats["removed_dte"] = int(mask_dte.sum())
    df = df[~mask_dte]

    mask_price = df['option_price'] <= 0
    stats["removed_price"] = int(mask_price.sum())
    df = df[~mask_price]

    # ── Soft filters ────────────────────────────────────────────────
    mask_oi_low = df['open_interest'] < min_open_interest
    stats["removed_oi_low"] = int(mask_oi_low.sum())
    df = df[~mask_oi_low]

    if 'insurance_cost_pct' in df.columns:
        mask_cost = df['insurance_cost_pct'] > max_insurance_cost_pct
        stats["removed_cost"] = int(mask_cost.sum())
        df = df[~mask_cost]
    else:
        stats["removed_cost"] = 0

    if 'greeks_delta' in df.columns:
        mask_delta = df['greeks_delta'].abs() < min_abs_delta
        stats["removed_delta"] = int(mask_delta.sum())
        df = df[~mask_delta]
    else:
        stats["removed_delta"] = 0

    stats["remaining"] = len(df)
    return df.copy(), stats


def calculate_smart_scores(
    df: pd.DataFrame,
    user_preferences: dict,
    weights: dict | None = None,
) -> pd.DataFrame:
    """
    Calculates a Smart Score (0-100) for every option row.

    Scoring dimensions:
    1. Cost Efficiency     (annualized_cost_pct)   – lower is better
    2. Protection Level    (locked_in_profit_pct)   – meets user goal
    3. Liquidity           (open_interest)          – log-scale
    4. DTE Match           (days_to_expiration)     – near target
    5. Time Value Efficiency (time_value_per_month) – lower is better

    Args:
        df: Filtered DataFrame with calculated metrics.
        user_preferences: Dict with keys:
            - goal: 'lock_profit' | 'limit_loss' | 'cheapest'
            - min_locked_in_profit_pct: float (target, e.g. 100.0)
            - target_dte: int or None (None = no DTE preference)
            - holding_period: str key from HOLDING_PERIOD_MAP
        weights: Optional custom weights dict (keys: cost, protection,
                 liquidity, dte_match, time_value).  Normalised internally.

    Returns:
        DataFrame with added 'smart_score' column, sorted descending.
    """
    if df.empty:
        df['smart_score'] = pd.Series(dtype=float)
        return df

    w = dict(weights or DEFAULT_WEIGHTS)

    # Normalise weights to sum = 1
    total_w = sum(w.values())
    if total_w > 0:
        w = {k: v / total_w for k, v in w.items()}

    # If user chose "any" DTE → set DTE-match weight to 0 and redistribute
    target_dte = user_preferences.get("target_dte")
    if target_dte is None:
        dte_weight = w.pop("dte_match", 0)
        if dte_weight > 0 and len(w) > 0:
            redistribute = dte_weight / len(w)
            w = {k: v + redistribute for k, v in w.items()}
        w["dte_match"] = 0

    target_profit = user_preferences.get("min_locked_in_profit_pct", 0.0)

    scores = []
    for _, row in df.iterrows():
        score = 0.0

        # 1. Cost Efficiency (30%) ─ normalised inverted
        score += _norm_inverted(row, 'annualized_cost_pct', df) * w.get("cost", 0)

        # 2. Protection Level (25%)
        score += _protection_score(row, target_profit) * w.get("protection", 0)

        # 3. Liquidity (15%) ─ log-scale
        oi = max(row.get('open_interest', 1), 1)
        liquidity = min(math.log10(oi) / math.log10(10000) * 100, 100)
        score += liquidity * w.get("liquidity", 0)

        # 4. DTE Match (15%)
        if target_dte is not None and w.get("dte_match", 0) > 0:
            dte_diff = abs(row['days_to_expiration'] - target_dte)
            dte_score = 100 if dte_diff <= 30 else max(100 - (dte_diff - 30) * 0.5, 0)
            score += dte_score * w["dte_match"]

        # 5. Time Value Efficiency (15%) ─ normalised inverted
        score += _norm_inverted(row, 'time_value_per_month', df) * w.get("time_value", 0)

        scores.append(round(score, 1))

    df = df.copy()
    df['smart_score'] = scores
    df = df.sort_values('smart_score', ascending=False).reset_index(drop=True)
    return df


def get_top_recommendations(df: pd.DataFrame, user_preferences: dict) -> dict:
    """
    Extracts three highlight recommendations from scored results.

    Returns dict with keys:
        - cheapest:        Lowest annualized_cost_pct that meets the user goal.
        - best_protection: Highest locked_in_profit_pct in the cheapest 20%.
        - best_balance:    Highest smart_score overall.
    Any key may be ``None`` if no qualifying row exists.
    """
    result = {"cheapest": None, "best_protection": None, "best_balance": None}

    if df.empty or 'smart_score' not in df.columns:
        return result

    target = user_preferences.get("min_locked_in_profit_pct", 0.0)

    # Best balance = highest smart_score (already sorted)
    result["best_balance"] = df.iloc[0]

    # Cheapest that meets goal
    meets_goal = df[df['locked_in_profit_pct'] >= target]
    if meets_goal.empty:
        # Fallback: cheapest overall
        cheapest_idx = df['annualized_cost_pct'].idxmin()
        result["cheapest"] = df.loc[cheapest_idx]
    else:
        cheapest_idx = meets_goal['annualized_cost_pct'].idxmin()
        result["cheapest"] = meets_goal.loc[cheapest_idx]

    # Best protection among cheapest 20%
    n_top20 = max(1, len(df) // 5)
    cheapest_20pct = df.nsmallest(n_top20, 'annualized_cost_pct')
    best_prot_idx = cheapest_20pct['locked_in_profit_pct'].idxmax()
    result["best_protection"] = cheapest_20pct.loc[best_prot_idx]

    return result


def generate_comparison_insight(top1: pd.Series, top2: pd.Series) -> str:
    """
    Template-based insight comparing the top-2 recommendations.
    Returns a markdown string.
    """
    if top1 is None or top2 is None:
        return ""

    cost_diff = abs(top1['annualized_cost_pct'] - top2['annualized_cost_pct'])
    dte_diff = abs(top1['days_to_expiration'] - top2['days_to_expiration'])
    profit_diff = abs(top1['locked_in_profit_pct'] - top2['locked_in_profit_pct'])

    if cost_diff < 1.0 and dte_diff > 60:
        return (
            f"💡 **Erkenntnis:** {top1['option_label']} und {top2['option_label']} "
            f"kosten fast gleich viel ({top1['annualized_cost_pct']:.1f}% vs. "
            f"{top2['annualized_cost_pct']:.1f}% p.a.), aber es liegen {int(dte_diff)} Tage "
            f"Laufzeit dazwischen. Bei ähnlichen Kosten → längere Laufzeit bevorzugen."
        )
    elif profit_diff < 5.0 and cost_diff > 3.0:
        cheaper = top1 if top1['annualized_cost_pct'] < top2['annualized_cost_pct'] else top2
        return (
            f"💡 **Erkenntnis:** Ähnlicher Schutz ({top1['locked_in_profit_pct']:.0f}% vs. "
            f"{top2['locked_in_profit_pct']:.0f}%), aber {cheaper['option_label']} ist "
            f"{cost_diff:.1f}% p.a. günstiger. Klare Wahl."
        )
    else:
        return (
            f"💡 **Top-Wahl:** {top1['option_label']} bietet das beste Gesamtpaket "
            f"mit Score {top1['smart_score']}."
        )


# ── internal helpers ────────────────────────────────────────────────

def _norm_inverted(row: pd.Series, col: str, df: pd.DataFrame) -> float:
    """Normalise a column value to 0-100 (inverted: lowest = 100)."""
    val = row.get(col, 0)
    mn = df[col].min()
    mx = df[col].max()
    if mx > mn:
        return (1 - (val - mn) / (mx - mn)) * 100
    return 100.0


def _protection_score(row: pd.Series, target_profit_pct: float) -> float:
    """Score protection: how well does the row meet the user's profit goal."""
    actual = row.get('locked_in_profit_pct', 0)
    if target_profit_pct <= 0:
        # Goal = "cheapest" – no protection target, mild bonus
        return min(actual, 100)
    if actual >= target_profit_pct:
        overshoot = actual - target_profit_pct
        return max(100 - overshoot, 70)
    else:
        return (actual / target_profit_pct) * 60 if target_profit_pct > 0 else 0
