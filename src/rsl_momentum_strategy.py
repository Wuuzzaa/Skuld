"""RSL Momentum Rotation Strategy — ranking and sector-diversified selection."""

import pandas as pd


def calculate_rsl_momentum_ranking(
    df: pd.DataFrame,
    top_n: int = 5,
    max_per_sector: int = 2,
    exit_percentile: float = 50.0,
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

    Returns
    -------
    dict with keys: ranking, top_picks, summary
    """
    if df.empty:
        return {"ranking": [], "top_picks": [], "summary": {}}

    df = df.copy()
    df = df.sort_values("rsl", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    total = len(df)

    # Percentile: rank 1 = ~100%, last rank = ~0%
    df["percentile"] = ((total - df["rank"] + 1) / total * 100).round(1)

    # Above threshold = in the top exit_percentile percent
    df["above_threshold"] = df["percentile"] >= (100 - exit_percentile)

    # Select top-N with sector diversification
    top_picks = _select_top_n_diversified(df, top_n, max_per_sector)

    # Mark top picks
    df["is_top_pick"] = df["symbol"].isin(top_picks)

    top_picks_df = df[df["is_top_pick"]]
    sector_dist = top_picks_df["sector"].value_counts().to_dict() if not top_picks_df.empty else {}

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
    }

    return {
        "ranking": df.to_dict(orient="records"),
        "top_picks": top_picks_df.to_dict(orient="records"),
        "summary": summary,
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
