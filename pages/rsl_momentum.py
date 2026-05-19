import streamlit as st
import pandas as pd

from src.database import select_into_dataframe_pg
from src.sp500_constituents import SP500_SYMBOLS
from src.rsl_momentum_strategy import calculate_rsl_momentum_ranking

RSL_QUERY = """
SELECT DISTINCT
    symbol,
    company_name,
    company_sector AS sector,
    company_industry AS industry,
    ROUND("RSL"::numeric, 4) AS rsl,
    live_stock_price AS price
FROM
    "OptionDataMerged"
WHERE
    symbol = ANY(:symbols)
    AND "RSL" IS NOT NULL
"""


@st.cache_data(ttl=300)
def load_rsl_data():
    """Load RSL data for S&P 500 symbols from database."""
    df = select_into_dataframe_pg(
        query=RSL_QUERY,
        params={"symbols": list(SP500_SYMBOLS)},
    )
    return df


def main():
    st.title("RSL Momentum Rotation")

    # Parameters
    col1, col2, col3 = st.columns(3)
    with col1:
        top_n = st.number_input("Top N", min_value=1, max_value=50, value=5, step=1,
                                help="Anzahl Positionen im Portfolio")
    with col2:
        max_per_sector = st.number_input("Max / Sektor", min_value=1, max_value=10, value=2, step=1,
                                         help="Maximale Aktien aus demselben Sektor")
    with col3:
        exit_percentile = st.number_input("Exit below Top %", min_value=1.0, max_value=90.0, value=50.0, step=5.0,
                                          help="Unter diesem Percentil wird verkauft")

    # Load data
    df = load_rsl_data()

    if df is None or df.empty:
        st.error("Keine RSL-Daten verfügbar. Bitte prüfe die Datenbankverbindung.")
        return

    # Calculate ranking
    result = calculate_rsl_momentum_ranking(
        df,
        top_n=int(top_n),
        max_per_sector=int(max_per_sector),
        exit_percentile=float(exit_percentile),
    )

    ranking = pd.DataFrame(result["ranking"])
    top_picks = pd.DataFrame(result["top_picks"])
    summary = result["summary"]

    # --- Top Picks Cards ---
    if not top_picks.empty:
        st.subheader(f"Top {top_n} Picks (max {max_per_sector} pro Sektor)")
        pick_cols = st.columns(min(len(top_picks), 5))
        for i, (_, pick) in enumerate(top_picks.iterrows()):
            with pick_cols[i % len(pick_cols)]:
                st.metric(
                    label=f"#{pick['rank']} {pick['symbol']}",
                    value=f"RSL {pick['rsl']:.4f}",
                    delta=f"${pick['price']:.2f}",
                )
                st.caption(f"{pick['company_name']}\n{pick['sector']}")

    # --- Summary Stats ---
    if summary:
        st.divider()
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("S&P 500 Ranked", summary["total_stocks"])
        s2.metric("Above Threshold", summary["above_threshold"])
        s3.metric("Avg RSL (Top Picks)", f"{summary['avg_rsl_top_picks']:.4f}" if summary['avg_rsl_top_picks'] else "N/A")
        s4.metric("RSL Range", f"{summary['min_rsl']:.3f} – {summary['max_rsl']:.3f}")

    # --- Full Ranking Table ---
    st.divider()
    st.subheader("Vollständiges Ranking")

    if not ranking.empty:
        # Prepare display dataframe
        display_df = ranking[["rank", "symbol", "company_name", "sector", "rsl", "price", "percentile", "above_threshold", "is_top_pick"]].copy()
        display_df["Signal"] = display_df["above_threshold"].map({True: "HOLD", False: "EXIT"})
        display_df["Top Pick"] = display_df["is_top_pick"].map({True: "\u2605", False: ""})
        display_df = display_df.drop(columns=["above_threshold", "is_top_pick"])
        display_df = display_df.rename(columns={
            "rank": "#",
            "symbol": "Symbol",
            "company_name": "Company",
            "sector": "Sector",
            "rsl": "RSL",
            "price": "Price",
            "percentile": "Percentile",
        })
        display_df["RSL"] = display_df["RSL"].round(4)
        display_df["Price"] = display_df["Price"].round(2)
        display_df["Percentile"] = display_df["Percentile"].round(1)

        # Color coding
        def style_ranking(df):
            def row_color(row):
                if row["Top Pick"] == "\u2605":
                    return ["background-color: #1e4620; color: white"] * len(row)
                elif row["Signal"] == "EXIT":
                    return ["background-color: #5c1a1a; color: white"] * len(row)
                return [""] * len(row)
            return df.style.apply(row_color, axis=1)

        st.dataframe(style_ranking(display_df), width="stretch", hide_index=True, height=600)

    # --- Detail: Click a row ---
    st.divider()
    with st.expander("Aktie im Detail analysieren"):
        if not ranking.empty:
            symbols = ranking["symbol"].tolist()
            selected_symbol = st.selectbox("Symbol auswählen", symbols, index=0)
            row = ranking[ranking["symbol"] == selected_symbol].iloc[0]

            d1, d2, d3, d4, d5 = st.columns(5)
            d1.metric("Rank", f"#{int(row['rank'])}")
            d2.metric("RSL", f"{row['rsl']:.4f}")
            d3.metric("Price", f"${row['price']:.2f}")
            d4.metric("Percentile", f"{row['percentile']:.1f}%")
            d5.metric("Signal", "HOLD" if row["above_threshold"] else "EXIT")

            st.markdown(f"""
            **Sektor:** {row['sector']} | **Industrie:** {row.get('industry', 'N/A')}

            **Interpretation:**
            - RSL = Kurs / SMA200 = {row['rsl']:.4f} → Aktie notiert **{abs(row['rsl'] - 1) * 100:.1f}%** {'über' if row['rsl'] >= 1 else 'unter'} dem 200-Tage-Durchschnitt
            - SMA200 ca. **${row['price'] / row['rsl']:.2f}**
            - Percentile {row['percentile']:.1f}% → {row['percentile']:.0f}% aller S&P 500 Aktien haben einen niedrigeren RSL
            """)

            # External Links
            st.markdown(
                f"[TradingView](https://www.tradingview.com/chart/?symbol={row['symbol']}) | "
                f"[Finviz](https://finviz.com/quote.ashx?t={row['symbol']}) | "
                f"[Yahoo Finance](https://finance.yahoo.com/quote/{row['symbol']})"
            )

    # --- Strategy Guide ---
    with st.expander("📖 Strategie-Anleitung (Schritt für Schritt)"):
        st.markdown("""
        ### RSL Momentum Rotation — Wochenroutine

        **Grundidee:** Du hältst immer die stärksten Aktien aus dem S&P 500 (gemessen am RSL = Kurs/SMA200).
        Jeden Montag prüfst du das Ranking und tauschst schwache Positionen gegen starke aus.

        ---

        #### Montag-Routine (5-10 Minuten):

        **1. Ranking öffnen & prüfen**
        - Öffne diese Seite und schaue auf deine aktuellen Positionen
        - Frage: Sind alle meine Positionen noch im grünen Bereich (HOLD)?

        **2. EXIT-Signale umsetzen**
        - Steht bei einer Position "EXIT" → **Verkaufen** (Market Order, Montag Vormittag)
        - EXIT bedeutet: Die Aktie ist unter deinen Exit-Threshold gefallen (z.B. raus aus Top 5%)

        **3. Neue Top Picks kaufen**
        - Die frei gewordenen Plätze werden mit den neuen Top Picks aufgefüllt
        - Immer gleichgewichtet: Bei 5 Positionen = je 20% des Portfolios
        - Nur kaufen was ein ⭐ (Top Pick) hat

        **4. Nichts tun wenn alles HOLD ist**
        - Kein Signal = Keine Aktion. Das ist der Normalfall!

        ---

        #### Parameter-Einstellungen:

        | Parameter | Empfehlung | Bedeutung |
        |-----------|-----------|-----------|
        | **Top N** | 5 | Anzahl Positionen im Portfolio |
        | **Max/Sektor** | 2 | Verhindert Klumpenrisiko in einem Sektor |
        | **Exit below Top %** | 5% (aggressiv) bis 50% (konservativ) | Wann wird verkauft? |

        **Exit-Threshold erklärt:**
        - **5%** = Aktie muss aus den Top 25 (von 500) rausfallen bevor verkauft wird → wenige Trades, hohe Trefferquote
        - **10%** = Aktie muss aus Top 50 rausfallen → guter Mittelweg
        - **50%** = Aktie muss unter den Median fallen → viele Trades, schnellere Reaktion

        ---

        #### Was ist RSL?
        **RSL** (Relative Strength Line) = Aktueller Kurs / 200-Tage-Durchschnitt (SMA200)

        - RSL = 1.5 → Aktie notiert 50% über ihrem SMA200 (sehr stark)
        - RSL = 1.0 → Aktie genau auf dem SMA200 (neutral)
        - RSL = 0.8 → Aktie 20% unter SMA200 (schwach)

        Die Strategie kauft systematisch die relativ stärksten Aktien und verkauft sie erst,
        wenn ihre relative Stärke deutlich nachlässt.

        ---

        #### Positionsgröße:
        Gleichgewichtet — bei Top 5 = je 20%. Beim Einstieg alle Top-Picks gleichzeitig kaufen.
        Rebalancing der Gewichte nur bei Tausch (nicht wöchentlich neu gewichten).

        #### Universum:
        S&P 500 Konstituenten. Daten: Live-Kurse aus OptionDataMerged (Polygon.io).
        """)


if __name__ == "__main__":
    main()
