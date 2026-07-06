"""RSL Momentum Rotation Strategy — ranking and sector-diversified selection."""

import pandas as pd


def calculate_rsl_momentum_ranking(
    df: pd.DataFrame,
    top_n: int = 5,
    max_per_sector: int = 2,
    exit_percentile: float = 50.0,
    min_rsl_threshold: float = 0.0,
    spy_filter_enabled: bool = False,
    spy_rsl: float | None = None,
) -> dict:
    """
    Rank S&P 500 stocks by RSL descending, apply sector diversification,
    and identify exit signals.

    Parameters
    ----------
    df : DataFrame with columns: symbol, company_name, sector, industry, rsl, price
    top_n : Number of top stocks to recommend (default 5)
    max_per_sector : Maximum stocks from same sector in top-N (default 2)
    exit_percentile : Stocks below this percentile trigger sell signal (default 50 = top half)
    min_rsl_threshold : Absolute RSL floor — candidates below this are excluded from top picks
                        (e.g. 1.0 means stock must trade above its SMA200). Set 0.0 to disable.
    spy_filter_enabled : When True, no new buys when SPY trades below its own SMA200 (spy_rsl < 1.0)
    spy_rsl : Current RSL of SPY (price / SMA200). Required when spy_filter_enabled=True.

    Returns
    -------
    dict with keys: ranking, top_picks, summary, regime
    """
    if df.empty:
        return {"ranking": [], "top_picks": [], "summary": {}, "regime": {}}

    df = df.copy()
    df = df.sort_values("rsl", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    total = len(df)

    # Percentile: rank 1 = ~100%, last rank = ~0%
    df["percentile"] = ((total - df["rank"] + 1) / total * 100).round(1)

    # Above threshold = in the top exit_percentile percent
    df["above_threshold"] = df["percentile"] >= (100 - exit_percentile)

    # Regime checks
    spy_is_bullish = True
    if spy_filter_enabled and spy_rsl is not None:
        spy_is_bullish = spy_rsl >= 1.0

    # Candidates eligible for top-pick selection:
    # - absolute RSL filter: stock must be above min_rsl_threshold
    # - spy filter: if market is bearish, no new picks at all (return empty top picks)
    if not spy_is_bullish:
        eligible_df = df.iloc[0:0]  # empty — no new buys in bear market
    elif min_rsl_threshold > 0:
        eligible_df = df[df["rsl"] >= min_rsl_threshold]
    else:
        eligible_df = df

    # Select top-N with sector diversification from eligible candidates only
    top_picks = _select_top_n_diversified(eligible_df, top_n, max_per_sector)

    # Mark top picks
    df["is_top_pick"] = df["symbol"].isin(top_picks)

    top_picks_df = df[df["is_top_pick"]]
    sector_dist = top_picks_df["sector"].value_counts().to_dict() if not top_picks_df.empty else {}

    cash_positions = top_n - len(top_picks)

    summary = {
        "total_stocks": total,
        "above_threshold": int(df["above_threshold"].sum()),
        "below_threshold": int(total - df["above_threshold"].sum()),
        "exit_percentile": exit_percentile,
        "avg_rsl_top_picks": round(float(top_picks_df["rsl"].mean()), 4) if not top_picks_df.empty else None,
        "avg_rsl_all": round(float(df["rsl"].mean()), 4),
        "max_rsl": round(float(df["rsl"].max()), 4),
        "min_rsl": round(float(df["rsl"].min()), 4),
        "sector_distribution": sector_dist,
        "cash_positions": cash_positions,
        "eligible_for_buy": len(eligible_df),
    }

    regime = {
        "spy_filter_enabled": spy_filter_enabled,
        "spy_rsl": spy_rsl,
        "spy_is_bullish": spy_is_bullish,
        "min_rsl_threshold": min_rsl_threshold,
        "cash_quota": round(cash_positions / top_n * 100, 1) if top_n > 0 else 0,
    }

    return {
        "ranking": df.to_dict(orient="records"),
        "top_picks": top_picks_df.to_dict(orient="records"),
        "summary": summary,
        "regime": regime,
    }


def _select_top_n_diversified(
    df: pd.DataFrame,
    top_n: int,
    max_per_sector: int,
) -> list[str]:
    """
    Walk through RSL-ranked list top-to-bottom, picking stocks until top_n reached,
    skipping if sector already has max_per_sector entries.
    """
    selected = []
    sector_count: dict[str, int] = {}

    for _, row in df.iterrows():
        if len(selected) >= top_n:
            break

        sector = row.get("sector") or "Unknown"
        current_count = sector_count.get(sector, 0)

        if current_count < max_per_sector:
            selected.append(row["symbol"])
            sector_count[sector] = current_count + 1

    return selected
