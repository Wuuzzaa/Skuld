import pandas as pd
import streamlit as st

from src.page_display_dataframe import page_display_dataframe
from src.trend_following_strategy import (
    calculate_trend_following_strategy,
    load_symbol_history,
    load_trend_following_universe,
)


def _format_pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value:.1%}"


def _format_number(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{int(value)}"


def _format_date(value: object) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _build_filter_summary(
    top_n: int,
    watchlist_size: int,
    min_rsl: float,
    min_adx: float,
    min_rsi: float,
    max_per_sector: int,
    require_above_sma200: bool,
) -> str:
    rule_parts = [
        f"Top {top_n} positions",
        f"Watchlist {watchlist_size}",
        f"RSL >= {min_rsl:.2f}",
        f"ADX >= {min_adx:.0f}",
        f"RSI >= {min_rsi:.0f}",
        f"max {max_per_sector} per sector",
    ]
    if require_above_sma200:
        rule_parts.append("Close > SMA 200")
    return " | ".join(rule_parts)


def _build_exit_reason_summary(exits_df: pd.DataFrame) -> pd.DataFrame:
    if exits_df.empty or "reason" not in exits_df.columns:
        return pd.DataFrame(columns=["Exit Reason", "Count"])
    reason_counts = (
        exits_df["reason"]
        .fillna("Unknown")
        .value_counts()
        .rename_axis("Exit Reason")
        .reset_index(name="Count")
    )
    return reason_counts


def _build_action_summary(actions_df: pd.DataFrame) -> pd.DataFrame:
    if actions_df.empty or "action" not in actions_df.columns:
        return pd.DataFrame(columns=["Action", "Count"])
    action_counts = (
        actions_df["action"]
        .value_counts()
        .rename_axis("Action")
        .reset_index(name="Count")
    )
    return action_counts


def _rename_ranking_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(
        columns={
            "company_name": "Company",
            "sector": "Sector",
            "industry": "Industry",
            "close_price": "Close",
            "rank": "Rank",
            "base_rank": "Pre-Cap Rank",
            "prev_rank": "Prev Rank",
            "rank_change": "Rank Change",
            "zone": "Zone",
            "portfolio_status": "Status",
            "above_sma_50": "Above SMA 50",
            "above_sma_200": "Above SMA 200",
        }
    )


def _build_weekly_checklist(summary: dict[str, object]) -> list[str]:
    checklist = [
        f"Pruefe zuerst die {summary['portfolio_count']} aktuellen Portfolio-Werte.",
        f"Pruefe danach {summary['sell_count']} moegliche Abgaenge mit Exit-Grund.",
        f"Pruefe zum Schluss {summary['watchlist_count']} Nachruecker in der Watchlist-Zone.",
    ]
    return checklist


st.subheader("Trend Following")
st.caption(
    "Einfacher Wochen-Check fuer das RSL-Trendmodell: halten, verkaufen, beobachten, nachruecken."
)

with st.expander("How to read this page", expanded=True):
    st.markdown(
        """
1. Weekly Decision: Hier siehst du sofort, was diese Woche zu tun ist.
2. Current Portfolio: Das sind die Werte, die das Modell aktuell halten wuerde.
3. Watchlist Zone: Das sind die naechsten Kandidaten fuer einen Nachrueckplatz.
4. Exit Reasons: Hier steht, warum ein bisheriger Wert rausfallen wuerde.
        """
    )

with st.sidebar:
    st.markdown("### Model Setup")
    top_n = st.number_input(
        "Portfolio Size",
        min_value=1,
        max_value=50,
        value=5,
        step=1,
        help="How many names the live model should hold.",
    )
    watchlist_size = st.number_input(
        "Watchlist Size",
        min_value=0,
        max_value=50,
        value=8,
        step=1,
        help="How many ranked names just below the portfolio should stay visible as near-entry candidates.",
    )

    st.markdown("### Entry Rules")
    min_rsl = st.number_input(
        "Minimum RSL",
        min_value=0.50,
        max_value=3.00,
        value=1.00,
        step=0.05,
        format="%.2f",
        help="Primary ranking floor. Lower values widen the universe.",
    )
    min_adx = st.number_input(
        "Minimum ADX",
        min_value=0.0,
        max_value=100.0,
        value=15.0,
        step=1.0,
        help="Trend-strength filter.",
    )
    min_rsi = st.number_input(
        "Minimum RSI",
        min_value=0.0,
        max_value=100.0,
        value=50.0,
        step=1.0,
        help="Momentum confirmation filter.",
    )
    require_above_sma200 = st.checkbox(
        "Require Close > SMA 200",
        value=True,
        help="Keeps the model aligned with the long-term trend.",
    )
    max_per_sector = st.number_input(
        "Max Per Sector",
        min_value=1,
        max_value=10,
        value=2,
        step=1,
        help="Prevents the ranking from clustering too heavily in one sector.",
    )

    st.markdown("### Active Rules")
    st.caption(
        _build_filter_summary(
            top_n=int(top_n),
            watchlist_size=int(watchlist_size),
            min_rsl=float(min_rsl),
            min_adx=float(min_adx),
            min_rsi=float(min_rsi),
            max_per_sector=int(max_per_sector),
            require_above_sma200=bool(require_above_sma200),
        )
    )

with st.spinner("Loading trend-following model..."):
    current_df, previous_df = load_trend_following_universe()

    strategy = calculate_trend_following_strategy(
        current_df=current_df,
        previous_df=previous_df,
        top_n=int(top_n),
        watchlist_size=int(watchlist_size),
        min_rsl=float(min_rsl),
        require_above_sma200=bool(require_above_sma200),
        min_adx=float(min_adx),
        min_rsi=float(min_rsi),
        max_per_sector=int(max_per_sector),
    )

summary = strategy["summary"]
portfolio_df = strategy["portfolio"]
watchlist_df = strategy["watchlist"]
actions_df = strategy["actions"]
exits_df = strategy["exits"]
ranking_df = strategy["ranking"]
rank_delta_df = strategy["rank_delta"]
sector_blocked_df = strategy["sector_blocked"]

action_summary_df = _build_action_summary(actions_df)
exit_reason_summary_df = _build_exit_reason_summary(exits_df)
weekly_checklist = _build_weekly_checklist(summary)

metric_col1, metric_col2, metric_col3, metric_col4, metric_col5, metric_col6 = st.columns(6)
metric_col1.metric("Snapshot", _format_date(summary["current_snapshot_date"]))
metric_col2.metric("Candidates", _format_number(summary["candidate_count"]))
metric_col3.metric("Portfolio", _format_number(summary["portfolio_count"]))
metric_col4.metric("Watchlist", _format_number(summary["watchlist_count"]))
metric_col5.metric("Buys / Holds", f"{summary['buy_count']} / {summary['hold_count']}")
metric_col6.metric("Sells", _format_number(summary["sell_count"]))

st.info(
    f"Wochenstatus: {summary['portfolio_count']} Haltepositionen, {summary['buy_count']} neue Kandidaten, "
    f"{summary['sell_count']} moegliche Exits und {summary['watchlist_count']} Werte knapp hinter dem Portfolio."
)

checklist_col, summary_col = st.columns([1.2, 1])
with checklist_col:
    st.markdown("### Weekly Decision")
    for item in weekly_checklist:
        st.write(f"- {item}")
with summary_col:
    st.markdown("### Action Mix")
    if action_summary_df.empty:
        st.info("Keine Aktionsdaten vorhanden.")
    else:
        st.bar_chart(action_summary_df.set_index("Action")[["Count"]])

main_tab, detail_tab = st.tabs(["Weekly Review", "Symbol Detail"])

with main_tab:
    top_col1, top_col2 = st.columns([1, 1])

    with top_col1:
        st.markdown("### Current Portfolio")
        st.caption("Das sind die Werte, die du diese Woche zunaechst halten wuerdest.")
        if portfolio_df.empty:
            st.info("Keine Werte erfuellen aktuell die Regeln.")
        else:
            portfolio_display = portfolio_df.rename(
                columns={
                    "company_name": "Company",
                    "sector": "Sector",
                    "industry": "Industry",
                    "close_price": "Close",
                    "rank": "Rank",
                    "prev_rank": "Prev Rank",
                    "rank_change": "Rank Change",
                    "above_sma_50": "Above SMA 50",
                    "above_sma_200": "Above SMA 200",
                }
            )
            page_display_dataframe(portfolio_display, symbol_column="symbol")

    with top_col2:
        st.markdown("### Watchlist Zone")
        st.caption("Diese Werte sind die naechsten Nachruecker, falls ein Platz frei wird.")
        if watchlist_df.empty:
            st.info("Aktuell gibt es keine Watchlist-Kandidaten.")
        else:
            watchlist_display = watchlist_df.rename(
                columns={
                    "company_name": "Company",
                    "sector": "Sector",
                    "industry": "Industry",
                    "close_price": "Close",
                    "rank": "Rank",
                    "prev_rank": "Prev Rank",
                    "rank_change": "Rank Change",
                    "distance_to_portfolio": "Distance To Portfolio",
                    "watchlist_reason": "Watchlist Reason",
                }
            )
            page_display_dataframe(watchlist_display, symbol_column="symbol")

    st.markdown("### Weekly Changes")
    st.caption("Hier entscheidest du praktisch: neu rein, drin bleiben oder raus.")
    if actions_df.empty:
        st.info("Keine Wochenaenderungen verfuegbar.")
    else:
        actions_display = actions_df.rename(
            columns={
                "company_name": "Company",
                "sector": "Sector",
                "zone": "Zone",
                "current_rank": "Current Rank",
                "previous_rank": "Previous Rank",
                "rank_change": "Rank Change",
                "current_rsl": "Current RSL",
                "previous_rsl": "Previous RSL",
                "reason": "Reason",
                "action": "Action",
            }
        )
        page_display_dataframe(actions_display, symbol_column="symbol")

    mid_col1, mid_col2 = st.columns([1.2, 1])
    with mid_col1:
        st.markdown("### Exit Reasons")
        st.caption("Nur wichtig, wenn ein bisheriger Portfoliowert diese Woche rausfaellt.")
        if exits_df.empty:
            st.info("Aktuell keine Exit-Signale.")
        else:
            exits_display = exits_df.rename(
                columns={
                    "company_name": "Company",
                    "sector": "Sector",
                    "zone": "Zone",
                    "current_rank": "Current Rank",
                    "previous_rank": "Previous Rank",
                    "rank_change": "Rank Change",
                    "current_rsl": "Current RSL",
                    "previous_rsl": "Previous RSL",
                    "reason": "Exit Reason",
                }
            )
            page_display_dataframe(exits_display, symbol_column="symbol")

    with mid_col2:
        st.markdown("### Main Exit Drivers")
        if exit_reason_summary_df.empty:
            st.info("Keine Exit-Treiber vorhanden.")
        else:
            st.bar_chart(exit_reason_summary_df.set_index("Exit Reason")[["Count"]])

    with st.expander("Rank Movement", expanded=False):
        st.caption("Optional: nur oeffnen, wenn du Rangverschiebungen im Detail sehen willst.")
        if rank_delta_df.empty:
            st.info("Keine Vorperiode fuer Rangvergleich vorhanden.")
        else:
            rank_delta_chart = rank_delta_df.head(20).copy()
            rank_delta_chart["rank_change"] = pd.to_numeric(rank_delta_chart["rank_change"], errors="coerce").fillna(0)
            st.bar_chart(rank_delta_chart.set_index("symbol")[["rank_change"]])

    with st.expander("Full Ranking", expanded=False):
        st.caption("Optional: nur nutzen, wenn du ueber Portfolio und Watchlist hinaus tiefer in die Rangliste schauen willst.")
        ranking_limit = st.select_slider(
            "Ranking Depth",
            options=[20, 50, 100],
            value=50,
            help="Begrenzt die Rangliste auf die fuer die Wochenauswertung wichtigsten Werte.",
        )
        if ranking_df.empty:
            st.info("Keine Rangliste verfuegbar.")
        else:
            ranking_display = _rename_ranking_columns(ranking_df.head(ranking_limit))
            page_display_dataframe(ranking_display, symbol_column="symbol")

    if not sector_blocked_df.empty:
        with st.expander("Sector Cap Exclusions", expanded=False):
            blocked_display = sector_blocked_df.rename(
                columns={
                    "company_name": "Company",
                    "sector": "Sector",
                    "base_rank": "Pre-Cap Rank",
                    "blocked_reason": "Blocked Reason",
                }
            )
            page_display_dataframe(blocked_display, symbol_column="symbol")

with detail_tab:
    history_symbol_options = []
    if not portfolio_df.empty:
        history_symbol_options.extend(portfolio_df["symbol"].tolist())
    if not watchlist_df.empty:
        history_symbol_options.extend(watchlist_df["symbol"].tolist())
    if not ranking_df.empty:
        history_symbol_options.extend(ranking_df.head(20)["symbol"].tolist())
    history_symbol_options = list(dict.fromkeys(history_symbol_options))

    st.markdown("### Symbol Trend Detail")
    st.caption("Optional: oeffne diese Ansicht nur, wenn du einen einzelnen Wert genauer pruefen willst.")
    if history_symbol_options:
        selected_symbol = st.selectbox(
            "Symbol for Trend Detail",
            options=history_symbol_options,
            index=0,
        )

        selected_snapshot = ranking_df[ranking_df["symbol"] == selected_symbol].head(1)
        if not selected_snapshot.empty:
            snapshot_col1, snapshot_col2, snapshot_col3, snapshot_col4 = st.columns(4)
            snapshot_col1.metric("Zone", str(selected_snapshot.iloc[0].get("zone", "n/a")))
            snapshot_col2.metric("Rank", _format_number(selected_snapshot.iloc[0].get("rank")))
            snapshot_col3.metric("RSL", f"{float(selected_snapshot.iloc[0].get('RSL')):.2f}" if pd.notna(selected_snapshot.iloc[0].get("RSL")) else "n/a")
            snapshot_col4.metric("RSI / ADX", (
                f"{float(selected_snapshot.iloc[0].get('RSI_14')):.0f} / {float(selected_snapshot.iloc[0].get('ADX_10')):.0f}"
                if pd.notna(selected_snapshot.iloc[0].get("RSI_14")) and pd.notna(selected_snapshot.iloc[0].get("ADX_10"))
                else "n/a"
            ))

        symbol_history_df = load_symbol_history(selected_symbol)
        if symbol_history_df.empty:
            st.info("No history found for the selected symbol.")
        else:
            chart_df = symbol_history_df.copy()
            chart_df["snapshot_date"] = pd.to_datetime(chart_df["snapshot_date"])
            chart_df = chart_df.set_index("snapshot_date")

            detail_col1, detail_col2 = st.columns(2)
            with detail_col1:
                st.markdown("### Momentum Stack")
                momentum_columns = [
                    column for column in ["RSL", "RSI_14", "ADX_10"] if column in chart_df.columns
                ]
                if momentum_columns:
                    st.line_chart(chart_df[momentum_columns])

            with detail_col2:
                st.markdown("### Price vs Trend Filters")
                price_chart_columns = [
                    column for column in ["close_price", "SMA_50", "SMA_200"] if column in chart_df.columns
                ]
                if price_chart_columns:
                    st.line_chart(chart_df[price_chart_columns])

            with st.expander("Symbol History Table", expanded=False):
                history_display = chart_df.reset_index().rename(
                    columns={
                        "snapshot_date": "Date",
                        "close_price": "Close",
                        "SMA_50": "SMA 50",
                        "SMA_200": "SMA 200",
                    }
                )
                page_display_dataframe(
                    history_display.sort_values(by="Date", ascending=False),
                    symbol_column="symbol",
                )
    else:
        st.info("No symbol history is available yet.")

with st.expander("Strategy Notes", expanded=False):
    st.markdown(
        """
This page uses `TechnicalIndicatorsCalculated` and `TechnicalIndicatorsCalculatedHistoryDaily` without changing anything in the database layer.

- Portfolio selection: RSL ranking with optional SMA 200, ADX and RSI filters.
- Watchlist zone: the next ranked names below the live portfolio.
- Exit reasons: explicit explanation for symbols leaving the prior portfolio.
- Historical model intentionally removed from the main workflow to keep the weekly review simple.
        """
    )
