import pandas as pd

from src.database import select_into_dataframe


CURRENT_UNIVERSE_QUERY = """
WITH latest_dates AS (
    SELECT snapshot_date
    FROM (
        SELECT DISTINCT snapshot_date
        FROM "TechnicalIndicatorsCalculatedHistoryDaily"
        ORDER BY snapshot_date DESC
        LIMIT 2
    ) ranked_dates
),
date_info AS (
    SELECT
        MAX(snapshot_date) AS current_snapshot_date,
        MIN(snapshot_date) AS previous_snapshot_date
    FROM latest_dates
)
SELECT
    ti.symbol,
    COALESCE(ap.name, ti.symbol) AS company_name,
    COALESCE(ap.sector, 'Unknown') AS sector,
    COALESCE(ap.industry, 'Unknown') AS industry,
    sp.close AS close_price,
    ti."RSL",
    ti."RSI_14",
    ti."ADX_10",
    ti."SMA_50",
    ti."SMA_200",
    ti."EMA_50",
    ti."EMA_200",
    CASE WHEN sp.close > ti."SMA_50" THEN TRUE ELSE FALSE END AS above_sma_50,
    CASE WHEN sp.close > ti."SMA_200" THEN TRUE ELSE FALSE END AS above_sma_200,
    di.current_snapshot_date,
    di.previous_snapshot_date
FROM "TechnicalIndicatorsCalculated" ti
LEFT JOIN "StockPricesYahoo" sp
    ON sp.symbol = ti.symbol
LEFT JOIN "StockAssetProfilesYahoo" ap
    ON ap.symbol = ti.symbol
CROSS JOIN date_info di
WHERE ti."RSL" IS NOT NULL
"""


PREVIOUS_UNIVERSE_QUERY = """
WITH previous_snapshot AS (
    SELECT MIN(snapshot_date) AS previous_snapshot_date
    FROM (
        SELECT DISTINCT snapshot_date
        FROM "TechnicalIndicatorsCalculatedHistoryDaily"
        ORDER BY snapshot_date DESC
        LIMIT 2
    ) ranked_dates
)
SELECT
    hist.symbol,
    COALESCE(ap.name, hist.symbol) AS company_name,
    COALESCE(ap.sector, 'Unknown') AS sector,
    COALESCE(ap.industry, 'Unknown') AS industry,
    price.close AS close_price,
    hist."RSL",
    hist."RSI_14",
    hist."ADX_10",
    hist."SMA_50",
    hist."SMA_200",
    hist."EMA_50",
    hist."EMA_200",
    CASE WHEN price.close > hist."SMA_50" THEN TRUE ELSE FALSE END AS above_sma_50,
    CASE WHEN price.close > hist."SMA_200" THEN TRUE ELSE FALSE END AS above_sma_200,
    prev.previous_snapshot_date AS snapshot_date
FROM "TechnicalIndicatorsCalculatedHistoryDaily" hist
INNER JOIN previous_snapshot prev
    ON hist.snapshot_date = prev.previous_snapshot_date
LEFT JOIN "StockPricesYahooHistoryDaily" price
    ON price.symbol = hist.symbol
    AND price.snapshot_date = hist.snapshot_date
LEFT JOIN "StockAssetProfilesYahoo" ap
    ON ap.symbol = hist.symbol
WHERE hist."RSL" IS NOT NULL
"""


HISTORY_UNIVERSE_QUERY = """
SELECT
    hist.snapshot_date,
    hist.symbol,
    COALESCE(ap.name, hist.symbol) AS company_name,
    COALESCE(ap.sector, 'Unknown') AS sector,
    COALESCE(ap.industry, 'Unknown') AS industry,
    price.close AS close_price,
    hist."RSL",
    hist."RSI_14",
    hist."ADX_10",
    hist."SMA_50",
    hist."SMA_200",
    hist."EMA_50",
    hist."EMA_200",
    CASE WHEN price.close > hist."SMA_50" THEN TRUE ELSE FALSE END AS above_sma_50,
    CASE WHEN price.close > hist."SMA_200" THEN TRUE ELSE FALSE END AS above_sma_200
FROM "TechnicalIndicatorsCalculatedHistoryDaily" hist
LEFT JOIN "StockPricesYahooHistoryDaily" price
    ON price.symbol = hist.symbol
    AND price.snapshot_date = hist.snapshot_date
LEFT JOIN "StockAssetProfilesYahoo" ap
    ON ap.symbol = hist.symbol
WHERE hist."RSL" IS NOT NULL
    AND hist.snapshot_date >= CURRENT_DATE - (:lookback_days * INTERVAL '1 day')
ORDER BY hist.snapshot_date ASC, hist.symbol ASC
"""


SYMBOL_HISTORY_QUERY = """
SELECT
    hist.snapshot_date,
    hist.symbol,
    price.close AS close_price,
    hist."RSL",
    hist."RSI_14",
    hist."ADX_10",
    hist."SMA_50",
    hist."SMA_200"
FROM "TechnicalIndicatorsCalculatedHistoryDaily" hist
LEFT JOIN "StockPricesYahooHistoryDaily" price
    ON price.symbol = hist.symbol
    AND price.snapshot_date = hist.snapshot_date
WHERE hist.symbol = :symbol
    AND hist.snapshot_date >= CURRENT_DATE - INTERVAL '180 days'
ORDER BY hist.snapshot_date ASC
"""


def load_trend_following_universe() -> tuple[pd.DataFrame, pd.DataFrame]:
    current_df = select_into_dataframe(query=CURRENT_UNIVERSE_QUERY)
    previous_df = select_into_dataframe(query=PREVIOUS_UNIVERSE_QUERY)
    return current_df, previous_df


def load_trend_following_history(lookback_days: int) -> pd.DataFrame:
    return select_into_dataframe(
        query=HISTORY_UNIVERSE_QUERY,
        params={"lookback_days": max(int(lookback_days), 30)},
    )


def load_symbol_history(symbol: str) -> pd.DataFrame:
    if not symbol:
        return pd.DataFrame()
    return select_into_dataframe(query=SYMBOL_HISTORY_QUERY, params={"symbol": symbol})


def _prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    prepared = df.copy()
    numeric_columns = [
        "close_price",
        "RSL",
        "RSI_14",
        "ADX_10",
        "SMA_50",
        "SMA_200",
        "EMA_50",
        "EMA_200",
    ]
    for column in numeric_columns:
        if column in prepared.columns:
            prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

    for column in ["above_sma_50", "above_sma_200"]:
        if column in prepared.columns:
            prepared[column] = prepared[column].fillna(False).astype(bool)

    for column in ["sector", "industry"]:
        if column in prepared.columns:
            prepared[column] = prepared[column].fillna("Unknown")

    if "company_name" in prepared.columns:
        prepared["company_name"] = prepared["company_name"].fillna(prepared["symbol"])
    if "snapshot_date" in prepared.columns:
        prepared["snapshot_date"] = pd.to_datetime(prepared["snapshot_date"])

    return prepared


def _filter_universe(
    df: pd.DataFrame,
    min_rsl: float,
    require_above_sma200: bool,
    min_adx: float,
    min_rsi: float,
) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    filtered = df.copy()
    filtered = filtered[filtered["RSL"].notna()]
    filtered = filtered[filtered["RSL"] >= min_rsl]
    filtered = filtered[filtered["ADX_10"].fillna(0) >= min_adx]
    filtered = filtered[filtered["RSI_14"].fillna(0) >= min_rsi]

    if require_above_sma200:
        filtered = filtered[filtered["above_sma_200"]]

    return filtered.reset_index(drop=True)


def _rank_universe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        ranked = df.copy()
        ranked["base_rank"] = pd.Series(dtype="int64")
        return ranked

    ranked = df.sort_values(
        by=["RSL", "ADX_10", "RSI_14", "symbol"],
        ascending=[False, False, False, True],
        kind="stable",
    ).reset_index(drop=True)
    ranked["base_rank"] = range(1, len(ranked) + 1)
    return ranked


def _apply_sector_cap(df: pd.DataFrame, max_per_sector: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df.empty:
        empty_ranked = df.copy()
        empty_blocked = df.copy()
        empty_blocked["blocked_reason"] = pd.Series(dtype="object")
        return empty_ranked, empty_blocked

    if max_per_sector <= 0:
        capped = df.copy().reset_index(drop=True)
        capped["rank"] = range(1, len(capped) + 1)
        empty_blocked = df.iloc[0:0].copy()
        empty_blocked["blocked_reason"] = pd.Series(dtype="object")
        return capped, empty_blocked

    selected_rows = []
    blocked_rows = []
    sector_counts: dict[str, int] = {}

    for _, row in df.iterrows():
        sector = row.get("sector", "Unknown") or "Unknown"
        count = sector_counts.get(sector, 0)
        row_dict = row.to_dict()
        if count >= max_per_sector:
            row_dict["blocked_reason"] = "Sector cap reached"
            blocked_rows.append(row_dict)
            continue
        sector_counts[sector] = count + 1
        selected_rows.append(row_dict)

    capped = pd.DataFrame(selected_rows)
    blocked = pd.DataFrame(blocked_rows)

    if capped.empty:
        capped = df.iloc[0:0].copy()
    capped = capped.reset_index(drop=True)
    capped["rank"] = range(1, len(capped) + 1)

    if blocked.empty:
        blocked = df.iloc[0:0].copy()
        blocked["blocked_reason"] = pd.Series(dtype="object")
    else:
        blocked = blocked.reset_index(drop=True)

    return capped, blocked


def _format_booleans(df: pd.DataFrame) -> pd.DataFrame:
    formatted = df.copy()
    for column in ["above_sma_50", "above_sma_200"]:
        if column in formatted.columns:
            formatted[column] = formatted[column].map({True: "Yes", False: "No"})
    return formatted


def _build_snapshot_selection(
    df: pd.DataFrame,
    top_n: int,
    watchlist_size: int,
    min_rsl: float,
    require_above_sma200: bool,
    min_adx: float,
    min_rsi: float,
    max_per_sector: int,
) -> dict[str, pd.DataFrame]:
    prepared = _prepare_dataframe(df)
    filtered = _filter_universe(
        prepared,
        min_rsl=min_rsl,
        require_above_sma200=require_above_sma200,
        min_adx=min_adx,
        min_rsi=min_rsi,
    )
    ranked_before_cap = _rank_universe(filtered)
    ranked, sector_blocked = _apply_sector_cap(ranked_before_cap, max_per_sector=max_per_sector)
    portfolio = ranked.head(top_n).copy()
    watchlist = ranked.iloc[top_n : top_n + watchlist_size].copy()
    return {
        "prepared": prepared,
        "filtered": filtered,
        "ranked_before_cap": ranked_before_cap,
        "ranked": ranked,
        "portfolio": portfolio,
        "watchlist": watchlist,
        "sector_blocked": sector_blocked,
    }


def _build_exit_reason(
    symbol: str,
    current_selection: dict[str, pd.DataFrame],
    min_rsl: float,
    require_above_sma200: bool,
    min_adx: float,
    min_rsi: float,
    top_n: int,
) -> str:
    prepared = current_selection["prepared"]
    filtered = current_selection["filtered"]
    ranked = current_selection["ranked"]
    sector_blocked = current_selection["sector_blocked"]

    prepared_lookup = prepared.set_index("symbol") if not prepared.empty else pd.DataFrame()
    filtered_symbols = set(filtered["symbol"].tolist()) if not filtered.empty else set()
    ranked_lookup = ranked.set_index("symbol") if not ranked.empty else pd.DataFrame()
    sector_blocked_symbols = set(sector_blocked["symbol"].tolist()) if not sector_blocked.empty else set()

    if prepared_lookup.empty or symbol not in prepared_lookup.index:
        return "Missing from current snapshot"

    row = prepared_lookup.loc[symbol]
    reasons = []
    if pd.isna(row.get("RSL")) or row.get("RSL", 0) < min_rsl:
        reasons.append("RSL below threshold")
    if row.get("ADX_10", 0) < min_adx:
        reasons.append("ADX below threshold")
    if row.get("RSI_14", 0) < min_rsi:
        reasons.append("RSI below threshold")
    if require_above_sma200 and not bool(row.get("above_sma_200", False)):
        reasons.append("Below SMA 200")

    if reasons:
        return ", ".join(reasons)
    if symbol in sector_blocked_symbols:
        return "Sector cap displaced by stronger peer"
    if not ranked_lookup.empty and symbol in ranked_lookup.index:
        rank = ranked_lookup.at[symbol, "rank"]
        if rank > top_n:
            return "Rank fell below portfolio cutoff"
    if symbol not in filtered_symbols:
        return "No longer passed the selection filter"
    return "No longer selected"


def calculate_trend_following_strategy(
    current_df: pd.DataFrame,
    previous_df: pd.DataFrame,
    top_n: int,
    watchlist_size: int,
    min_rsl: float,
    require_above_sma200: bool,
    min_adx: float,
    min_rsi: float,
    max_per_sector: int,
) -> dict[str, pd.DataFrame | dict]:
    current_selection = _build_snapshot_selection(
        current_df,
        top_n=top_n,
        watchlist_size=watchlist_size,
        min_rsl=min_rsl,
        require_above_sma200=require_above_sma200,
        min_adx=min_adx,
        min_rsi=min_rsi,
        max_per_sector=max_per_sector,
    )
    previous_selection = _build_snapshot_selection(
        previous_df,
        top_n=top_n,
        watchlist_size=watchlist_size,
        min_rsl=min_rsl,
        require_above_sma200=require_above_sma200,
        min_adx=min_adx,
        min_rsi=min_rsi,
        max_per_sector=max_per_sector,
    )

    current_ranked = current_selection["ranked"].copy()
    previous_ranked = previous_selection["ranked"].copy()
    current_portfolio = current_selection["portfolio"].copy()
    previous_portfolio = previous_selection["portfolio"].copy()
    watchlist = current_selection["watchlist"].copy()

    previous_rank_map = previous_ranked.set_index("symbol")["rank"].to_dict() if not previous_ranked.empty else {}
    previous_rsl_map = previous_ranked.set_index("symbol")["RSL"].to_dict() if not previous_ranked.empty else {}
    previous_portfolio_symbols = set(previous_portfolio["symbol"].tolist()) if not previous_portfolio.empty else set()
    current_portfolio_symbols = set(current_portfolio["symbol"].tolist()) if not current_portfolio.empty else set()
    watchlist_symbols = set(watchlist["symbol"].tolist()) if not watchlist.empty else set()

    if current_ranked.empty:
        current_ranked["prev_rank"] = pd.Series(dtype="float64")
        current_ranked["rank_change"] = pd.Series(dtype="float64")
        current_ranked["zone"] = pd.Series(dtype="object")
        current_ranked["portfolio_status"] = pd.Series(dtype="object")
    else:
        current_ranked["prev_rank"] = current_ranked["symbol"].map(previous_rank_map)
        current_ranked["rank_change"] = current_ranked["prev_rank"] - current_ranked["rank"]
        current_ranked["zone"] = current_ranked["symbol"].map(
            lambda symbol: "Portfolio"
            if symbol in current_portfolio_symbols
            else "Watchlist"
            if symbol in watchlist_symbols
            else "Bench"
        )
        current_ranked["portfolio_status"] = current_ranked["symbol"].map(
            lambda symbol: "HOLD"
            if symbol in previous_portfolio_symbols and symbol in current_portfolio_symbols
            else "BUY"
            if symbol in current_portfolio_symbols
            else "WATCH"
            if symbol in watchlist_symbols
            else "PASS"
        )

    if not current_portfolio.empty:
        current_portfolio = current_ranked[current_ranked["symbol"].isin(current_portfolio_symbols)].copy()
    if not watchlist.empty:
        watchlist = current_ranked[current_ranked["symbol"].isin(watchlist_symbols)].copy()
        watchlist["watchlist_reason"] = watchlist["symbol"].map(
            lambda symbol: "Dropped from portfolio but still eligible"
            if symbol in previous_portfolio_symbols
            else "Next in line for entry"
        )
        watchlist["distance_to_portfolio"] = watchlist["rank"] - top_n

    current_lookup = current_ranked.set_index("symbol") if not current_ranked.empty else pd.DataFrame()

    action_rows = []
    for _, row in current_portfolio.iterrows():
        symbol = row["symbol"]
        action_rows.append(
            {
                "action": "HOLD" if symbol in previous_portfolio_symbols else "BUY",
                "symbol": symbol,
                "company_name": row.get("company_name"),
                "sector": row.get("sector"),
                "zone": row.get("zone"),
                "current_rank": row.get("rank"),
                "previous_rank": row.get("prev_rank"),
                "rank_change": row.get("rank_change"),
                "current_rsl": row.get("RSL"),
                "previous_rsl": previous_rsl_map.get(symbol),
                "reason": "Still in portfolio" if symbol in previous_portfolio_symbols else "Entered portfolio from ranking/watchlist",
            }
        )

    for _, row in previous_portfolio.iterrows():
        symbol = row["symbol"]
        if symbol in current_portfolio_symbols:
            continue
        current_rank = current_lookup.at[symbol, "rank"] if not current_lookup.empty and symbol in current_lookup.index else None
        current_rsl = current_lookup.at[symbol, "RSL"] if not current_lookup.empty and symbol in current_lookup.index else None
        current_zone = current_lookup.at[symbol, "zone"] if not current_lookup.empty and symbol in current_lookup.index else "Filtered Out"
        current_rank_change = current_lookup.at[symbol, "rank_change"] if not current_lookup.empty and symbol in current_lookup.index else None
        action_rows.append(
            {
                "action": "SELL",
                "symbol": symbol,
                "company_name": row.get("company_name"),
                "sector": row.get("sector"),
                "zone": current_zone,
                "current_rank": current_rank,
                "previous_rank": row.get("rank"),
                "rank_change": current_rank_change,
                "current_rsl": current_rsl,
                "previous_rsl": row.get("RSL"),
                "reason": _build_exit_reason(
                    symbol,
                    current_selection=current_selection,
                    min_rsl=min_rsl,
                    require_above_sma200=require_above_sma200,
                    min_adx=min_adx,
                    min_rsi=min_rsi,
                    top_n=top_n,
                ),
            }
        )

    actions_df = pd.DataFrame(action_rows)
    if not actions_df.empty:
        action_order = {"BUY": 0, "HOLD": 1, "SELL": 2}
        actions_df["_sort"] = actions_df["action"].map(action_order)
        actions_df = actions_df.sort_values(
            by=["_sort", "current_rank", "previous_rank", "symbol"],
            kind="stable",
        ).drop(columns=["_sort"]).reset_index(drop=True)

    exit_df = actions_df[actions_df["action"] == "SELL"].copy() if not actions_df.empty else pd.DataFrame()
    rank_delta_df = current_ranked[current_ranked["prev_rank"].notna()].copy() if not current_ranked.empty else pd.DataFrame()
    if not rank_delta_df.empty:
        rank_delta_df = rank_delta_df.sort_values(by=["rank", "symbol"], kind="stable").reset_index(drop=True)

    sector_blocked_df = current_selection["sector_blocked"].copy()
    if not sector_blocked_df.empty:
        sector_blocked_df = sector_blocked_df[
            [
                column
                for column in [
                    "symbol",
                    "company_name",
                    "sector",
                    "base_rank",
                    "RSL",
                    "ADX_10",
                    "RSI_14",
                    "blocked_reason",
                ]
                if column in sector_blocked_df.columns
            ]
        ].copy()

    summary = {
        "current_snapshot_date": current_selection["prepared"]["current_snapshot_date"].iloc[0]
        if not current_selection["prepared"].empty and "current_snapshot_date" in current_selection["prepared"].columns
        else None,
        "previous_snapshot_date": current_selection["prepared"]["previous_snapshot_date"].iloc[0]
        if not current_selection["prepared"].empty and "previous_snapshot_date" in current_selection["prepared"].columns
        else None,
        "raw_candidate_count": int(len(current_selection["prepared"])),
        "filtered_count": int(len(current_selection["filtered"])),
        "candidate_count": int(len(current_ranked)),
        "portfolio_count": int(len(current_portfolio)),
        "watchlist_count": int(len(watchlist)),
        "buy_count": int((actions_df["action"] == "BUY").sum()) if not actions_df.empty else 0,
        "hold_count": int((actions_df["action"] == "HOLD").sum()) if not actions_df.empty else 0,
        "sell_count": int((actions_df["action"] == "SELL").sum()) if not actions_df.empty else 0,
        "sector_blocked_count": int(len(sector_blocked_df)),
    }

    ranking_columns = [
        "rank",
        "base_rank",
        "prev_rank",
        "rank_change",
        "zone",
        "portfolio_status",
        "symbol",
        "company_name",
        "sector",
        "industry",
        "close_price",
        "RSL",
        "ADX_10",
        "RSI_14",
        "above_sma_50",
        "above_sma_200",
        "SMA_50",
        "SMA_200",
        "EMA_50",
        "EMA_200",
    ]
    portfolio_columns = [
        "rank",
        "prev_rank",
        "rank_change",
        "symbol",
        "company_name",
        "sector",
        "industry",
        "close_price",
        "RSL",
        "ADX_10",
        "RSI_14",
        "above_sma_50",
        "above_sma_200",
    ]
    watchlist_columns = [
        "rank",
        "prev_rank",
        "rank_change",
        "distance_to_portfolio",
        "symbol",
        "company_name",
        "sector",
        "industry",
        "close_price",
        "RSL",
        "ADX_10",
        "RSI_14",
        "watchlist_reason",
    ]
    rank_delta_columns = [
        "symbol",
        "company_name",
        "sector",
        "rank",
        "prev_rank",
        "rank_change",
        "zone",
        "RSL",
    ]

    current_ranked = _format_booleans(current_ranked)
    current_portfolio = _format_booleans(current_portfolio)

    return {
        "summary": summary,
        "ranking": current_ranked[[column for column in ranking_columns if column in current_ranked.columns]].copy(),
        "portfolio": current_portfolio[[column for column in portfolio_columns if column in current_portfolio.columns]].copy(),
        "watchlist": watchlist[[column for column in watchlist_columns if column in watchlist.columns]].copy(),
        "actions": actions_df,
        "exits": exit_df,
        "rank_delta": rank_delta_df[[column for column in rank_delta_columns if column in rank_delta_df.columns]].copy()
        if not rank_delta_df.empty
        else pd.DataFrame(columns=rank_delta_columns),
        "sector_blocked": sector_blocked_df,
    }


def calculate_trend_following_backtest(
    history_df: pd.DataFrame,
    top_n: int,
    watchlist_size: int,
    min_rsl: float,
    require_above_sma200: bool,
    min_adx: float,
    min_rsi: float,
    max_per_sector: int,
) -> dict[str, pd.DataFrame | dict]:
    prepared_history = _prepare_dataframe(history_df)
    if prepared_history.empty or "snapshot_date" not in prepared_history.columns:
        return {
            "summary": {
                "periods": 0,
                "start_date": None,
                "end_date": None,
                "cumulative_return": 0.0,
                "annualized_return": 0.0,
                "max_drawdown": 0.0,
                "avg_turnover": 0.0,
                "hit_rate": 0.0,
            },
            "equity_curve": pd.DataFrame(),
            "rebalance_log": pd.DataFrame(),
            "period_stats": pd.DataFrame(),
            "recent_history": pd.DataFrame(),
        }

    snapshot_dates = sorted(prepared_history["snapshot_date"].dropna().unique())
    if len(snapshot_dates) < 2:
        return {
            "summary": {
                "periods": 0,
                "start_date": snapshot_dates[0] if len(snapshot_dates) == 1 else None,
                "end_date": snapshot_dates[-1] if len(snapshot_dates) == 1 else None,
                "cumulative_return": 0.0,
                "annualized_return": 0.0,
                "max_drawdown": 0.0,
                "avg_turnover": 0.0,
                "hit_rate": 0.0,
            },
            "equity_curve": pd.DataFrame(),
            "rebalance_log": pd.DataFrame(),
            "period_stats": pd.DataFrame(),
            "recent_history": pd.DataFrame(),
        }

    equity = 1.0
    max_equity = 1.0
    positive_positions = 0
    total_positions = 0
    previous_portfolio_symbols: set[str] = set()
    equity_rows = []
    rebalance_rows = []
    recent_history_rows = []

    for current_date, next_date in zip(snapshot_dates[:-1], snapshot_dates[1:]):
        current_slice = prepared_history[prepared_history["snapshot_date"] == current_date].copy()
        next_slice = prepared_history[prepared_history["snapshot_date"] == next_date].copy()
        selection = _build_snapshot_selection(
            current_slice,
            top_n=top_n,
            watchlist_size=watchlist_size,
            min_rsl=min_rsl,
            require_above_sma200=require_above_sma200,
            min_adx=min_adx,
            min_rsi=min_rsi,
            max_per_sector=max_per_sector,
        )
        portfolio = selection["portfolio"].copy()
        portfolio_symbols = set(portfolio["symbol"].tolist()) if not portfolio.empty else set()
        next_prices = next_slice.set_index("symbol")["close_price"].to_dict() if not next_slice.empty else {}

        position_returns = []
        for _, row in portfolio.iterrows():
            symbol = row["symbol"]
            current_price = row.get("close_price")
            next_price = next_prices.get(symbol)
            if pd.isna(current_price) or pd.isna(next_price) or current_price in [0, None]:
                continue
            position_return = (float(next_price) / float(current_price)) - 1.0
            position_returns.append(position_return)
            recent_history_rows.append(
                {
                    "from_date": current_date,
                    "to_date": next_date,
                    "symbol": symbol,
                    "entry_price": current_price,
                    "exit_price": next_price,
                    "position_return": position_return,
                }
            )

        buys = portfolio_symbols - previous_portfolio_symbols
        sells = previous_portfolio_symbols - portfolio_symbols
        if previous_portfolio_symbols:
            turnover = (len(buys) + len(sells)) / max(2 * top_n, 1)
        else:
            turnover = len(buys) / max(top_n, 1)

        period_return = sum(position_returns) / len(position_returns) if position_returns else 0.0
        period_hit_rate = (
            sum(1 for value in position_returns if value > 0) / len(position_returns)
            if position_returns
            else 0.0
        )

        positive_positions += sum(1 for value in position_returns if value > 0)
        total_positions += len(position_returns)

        equity *= 1.0 + period_return
        max_equity = max(max_equity, equity)
        drawdown = (equity / max_equity) - 1.0

        equity_rows.append(
            {
                "snapshot_date": next_date,
                "equity": equity,
                "period_return": period_return,
                "turnover": turnover,
                "hit_rate": period_hit_rate,
                "holdings": len(portfolio_symbols),
                "buys": len(buys),
                "sells": len(sells),
                "drawdown": drawdown,
            }
        )
        rebalance_rows.append(
            {
                "rebalance_date": current_date,
                "next_date": next_date,
                "holdings": len(portfolio_symbols),
                "buys": len(buys),
                "sells": len(sells),
                "turnover": turnover,
                "period_return": period_return,
                "hit_rate": period_hit_rate,
                "positions": ", ".join(sorted(portfolio_symbols)),
            }
        )

        previous_portfolio_symbols = portfolio_symbols

    equity_curve_df = pd.DataFrame(equity_rows)
    rebalance_log_df = pd.DataFrame(rebalance_rows)
    recent_history_df = pd.DataFrame(recent_history_rows)

    if not equity_curve_df.empty:
        equity_curve_df["snapshot_date"] = pd.to_datetime(equity_curve_df["snapshot_date"])
        max_drawdown = float(equity_curve_df["drawdown"].min())
        avg_turnover = float(equity_curve_df["turnover"].mean())
        start_date = snapshot_dates[0]
        end_date = snapshot_dates[-1]
        elapsed_days = max((pd.Timestamp(end_date) - pd.Timestamp(start_date)).days, 1)
        cumulative_return = float(equity_curve_df["equity"].iloc[-1] - 1.0)
        annualized_return = float((equity_curve_df["equity"].iloc[-1] ** (365 / elapsed_days)) - 1.0)
    else:
        max_drawdown = 0.0
        avg_turnover = 0.0
        start_date = snapshot_dates[0]
        end_date = snapshot_dates[-1]
        cumulative_return = 0.0
        annualized_return = 0.0

    summary = {
        "periods": int(len(equity_curve_df)),
        "start_date": start_date,
        "end_date": end_date,
        "cumulative_return": cumulative_return,
        "annualized_return": annualized_return,
        "max_drawdown": max_drawdown,
        "avg_turnover": avg_turnover,
        "hit_rate": (positive_positions / total_positions) if total_positions else 0.0,
    }

    return {
        "summary": summary,
        "equity_curve": equity_curve_df,
        "rebalance_log": rebalance_log_df,
        "period_stats": equity_curve_df.copy(),
        "recent_history": recent_history_df,
    }
