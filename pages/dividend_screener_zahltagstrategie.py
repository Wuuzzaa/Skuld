"""Zahltagstrategie Dividend Screener - 11-Punkte-Matrix nach Nils Gajovi.

Scoring: 5 Fundamental + 5 Dividend + 1 Technik = max 33 Punkte.
- >= 23: KAUFEN
- 12-22: BEOBACHTEN
- < 12: PAPIERKORB
"""

import streamlit as st
import pandas as pd
import os
import urllib.parse

from src.database import select_into_dataframe_pg
from src.dividend_screener import calculate_dividend_scores, filter_dividend_screener

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_FILE = os.path.join(BASE_DIR, "db", "SQL", "query", "dividend_screener.sql")
ZAHLTAG_PROMPT_FILE = os.path.join(BASE_DIR, "src", "prompts", "prompt_zahltagstrategie.txt")


@st.cache_data(ttl=600)
def load_and_score():
    """Load dividend data and apply 11-point scoring matrix."""
    df = select_into_dataframe_pg(sql_file_path=SQL_FILE)
    if df is None or df.empty:
        return pd.DataFrame()
    return calculate_dividend_scores(df)


@st.cache_data(ttl=600)
def get_sectors(df):
    """Get unique sectors for filter dropdown."""
    if df.empty:
        return []
    return sorted(df['sector'].dropna().unique().tolist())


def score_badge(score):
    """Format score with color."""
    if score >= 23:
        return f"🟢 {score}/33"
    elif score >= 12:
        return f"🟡 {score}/33"
    return f"🔴 {score}/33"


def _create_zahltag_claude_url(symbol, row):
    """Erstellt einen Claude Deep-Link mit dem Zahltagstrategie-Prompt + DB-Daten fuer ein Symbol."""
    try:
        if not os.path.exists(ZAHLTAG_PROMPT_FILE):
            return None
        with open(ZAHLTAG_PROMPT_FILE, "r", encoding="utf-8") as f:
            prompt = f.read()
        prompt = prompt.replace("[ZZZ]", symbol)

        # Kennzahlen aus der DB in den Prompt einbetten
        def fmt(val, decimals=2, suffix=""):
            if pd.isna(val):
                return "N/A"
            return f"{val:.{decimals}f}{suffix}"

        data_block = f"""

BEREITS VORLIEGENDE DATEN AUS UNSERER DATENBANK (Stand: heute, nutze diese als Ausgangsbasis):

Kurs: ${fmt(row.get('price'))} | 52W-Tief: ${fmt(row.get('week_52_low'))} | 52W-Hoch: ${fmt(row.get('week_52_high'))}
Sektor: {row.get('sector', 'N/A')} | Industrie: {row.get('industry', 'N/A')} | Land: {row.get('country', 'N/A')}

BEWERTUNG:
- Trailing P/E: {fmt(row.get('trailing_pe'), 1)}
- Forward P/E: {fmt(row.get('forward_pe'), 1)}
- Price/Book: {fmt(row.get('price_to_book'), 1)}
- Market Cap: ${fmt(row.get('market_cap_b'), 1)} Mrd.
- Beta: {fmt(row.get('beta'), 2)}

DIVIDENDE:
- Dividend Yield: {fmt(row.get('dividend_yield_pct'))}%
- Annual Dividend Rate: ${fmt(row.get('annual_dividend_rate'), 4)}
- Payout Ratio: {fmt(row.get('payout_ratio_pct'), 1)}%
- Dividenden-Wachstumsjahre: {int(row.get('dividend_growth_years', 0)) if not pd.isna(row.get('dividend_growth_years')) else 'N/A'}
- Klassifikation: {row.get('dividend_classification', 'N/A')}
- 5-Jahres-Durchschnitts-Yield: {fmt(row.get('five_year_avg_yield'))}%
- Zahlungen pro Jahr: {int(row.get('dividend_payments_per_year', 0)) if not pd.isna(row.get('dividend_payments_per_year')) else 'N/A'}

PROFITABILITAET & BILANZ:
- Profit Margin: {fmt(row.get('profit_margin_pct'), 1)}%
- Operating Margin: {fmt(row.get('operating_margin_pct'), 1)}%
- ROE: {fmt(row.get('roe_pct'), 1)}%
- Debt/Equity: {fmt(row.get('debt_to_equity'), 0)}
- Current Ratio: {fmt(row.get('current_ratio'), 2)}

WACHSTUM:
- EPS (trailing): ${fmt(row.get('trailing_eps'))}
- EPS (forward): ${fmt(row.get('forward_eps'))}
- Forward EPS Growth: {fmt(row.get('eps_growth_pct'), 1)}%

TECHNIK:
- RSI (14): {fmt(row.get('rsi_14'), 1)}
- SMA 50: ${fmt(row.get('sma_50'))}
- SMA 200: ${fmt(row.get('sma_200'))}
- % von SMA200: {fmt(row.get('pct_from_sma200'), 1)}%
- % vom 52W-Hoch: {fmt(row.get('pct_from_52w_high'), 1)}%
- MACD Histogram: {fmt(row.get('macd_histogram'), 4)}

ANALYSTEN:
- Recommendation (1=Strong Buy, 5=Sell): {fmt(row.get('analyst_recommendation'), 1)}
- Anzahl Analysten: {int(row.get('analyst_count', 0)) if not pd.isna(row.get('analyst_count')) else 'N/A'}
- Short % Float: {fmt(row.get('short_pct_float'), 1)}%

ZAHLTAGSTRATEGIE-SCORE: {int(row.get('score_total', 0))}/33 (F:{int(row.get('score_fundamental', 0))}/15 D:{int(row.get('score_dividend', 0))}/15 T:{int(row.get('score_technical', 0))}/3)
Signal: {row.get('recommendation', 'N/A')}

Anlagehorizont: 5-10 Jahre (Dividenden-Einkommensstrategie)
"""
        prompt += data_block
        encoded_prompt = urllib.parse.quote(prompt.strip())
        return f"https://claude.ai/new?q={encoded_prompt}"
    except Exception:
        pass
    return None


def main():
    st.title("📊 Zahltagstrategie - Dividend Screener")
    st.caption("11-Punkte-Matrix (5 Fundamental + 5 Dividend + 1 Technik) | Max 33 Punkte")

    # Load data
    df_scored = load_and_score()

    if df_scored.empty:
        st.error("Keine Daten verfügbar. Prüfe die Datenbankverbindung.")
        return

    sectors = get_sectors(df_scored)

    # --- Filters ---
    with st.expander("🔍 Filter", expanded=True):
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            min_score = st.slider("Min Score", 0, 33, 12)
            min_yield = st.slider("Min Dividend Yield %", 0.0, 15.0, 3.0, 0.5)
            min_dividend_years = st.number_input("Min Div. Growth Years", 0, 60, 5)

        with col2:
            min_price = st.number_input("Min Preis $", 0.0, 1000.0, 10.0)
            min_market_cap_b = st.number_input("Min Market Cap (Mrd $)", 0.0, 500.0, 2.0)
            min_avg_volume = st.number_input("Min Avg Volume", 0, 10000000, 200000, step=50000)

        with col3:
            max_debt_to_equity = st.number_input("Max Debt/Equity (0=kein Filter)", 0.0, 500.0, 0.0)
            sector = st.selectbox("Sektor", [""] + sectors)
            exclude_reits = st.checkbox("REITs ausschließen", value=False)

        with col4:
            below_sma200 = st.checkbox("Unter SMA200", value=False)
            above_52w_low = st.checkbox("Über 52W-Tief (+10%)", value=False)
            only_champions = st.checkbox("Nur Champions (25+ Jahre)", value=False)
            only_contenders_plus = st.checkbox("Contenders+ (10+ Jahre)", value=False)

    # Apply filters
    df_filtered = filter_dividend_screener(
        df_scored,
        min_yield=min_yield,
        min_price=min_price,
        min_market_cap_b=min_market_cap_b,
        min_avg_volume=min_avg_volume,
        max_debt_to_equity=max_debt_to_equity,
        min_dividend_years=min_dividend_years,
        min_score=min_score,
        sector=sector,
        below_sma200=below_sma200,
        above_52w_low=above_52w_low,
        only_champions=only_champions,
        only_contenders_plus=only_contenders_plus,
        exclude_reits=exclude_reits,
    )

    # --- Summary Stats ---
    total = len(df_scored)
    filtered = len(df_filtered)
    buy_count = len(df_filtered[df_filtered['recommendation'] == 'BUY']) if not df_filtered.empty else 0
    watch_count = len(df_filtered[df_filtered['recommendation'] == 'WATCH']) if not df_filtered.empty else 0

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Gesamt Dividend Stocks", total)
    col2.metric("Nach Filter", filtered)
    col3.metric("🟢 KAUFEN (≥23)", buy_count)
    col4.metric("🟡 BEOBACHTEN (12-22)", watch_count)
    if not df_filtered.empty:
        col5.metric("Ø Score", f"{df_filtered['score_total'].mean():.1f}/33")

    st.divider()

    if df_filtered.empty:
        st.warning("Keine Aktien entsprechen den Filtern. Versuche niedrigere Schwellwerte.")
        return

    # --- Results Table ---
    display_cols = [
        'symbol', 'company_name', 'sector', 'price',
        'score_total', 'recommendation',
        'score_fundamental', 'score_dividend', 'score_technical',
        'dividend_yield_pct', 'dividend_growth_years', 'dividend_classification',
        'trailing_pe', 'profit_margin_pct', 'roe_pct', 'debt_to_equity',
        'payout_ratio_pct', 'rsi_14', 'pct_from_sma200', 'market_cap_b',
    ]
    # Only include columns that exist
    display_cols = [c for c in display_cols if c in df_filtered.columns]

    df_display = df_filtered[display_cols].copy()
    df_display.index = range(1, len(df_display) + 1)

    # Rename for display
    col_rename = {
        'symbol': 'Symbol',
        'company_name': 'Unternehmen',
        'sector': 'Sektor',
        'price': 'Kurs $',
        'score_total': 'Score',
        'recommendation': 'Signal',
        'score_fundamental': 'Fund.',
        'score_dividend': 'Div.',
        'score_technical': 'Tech.',
        'dividend_yield_pct': 'Yield %',
        'dividend_growth_years': 'Div Years',
        'dividend_classification': 'Klasse',
        'trailing_pe': 'P/E',
        'profit_margin_pct': 'Margin %',
        'roe_pct': 'ROE %',
        'debt_to_equity': 'D/E',
        'payout_ratio_pct': 'Payout %',
        'rsi_14': 'RSI',
        'pct_from_sma200': '% SMA200',
        'market_cap_b': 'MCap B$',
    }
    df_display = df_display.rename(columns=col_rename)

    # Format
    format_dict = {}
    if 'Kurs $' in df_display.columns:
        format_dict['Kurs $'] = '{:.2f}'
    if 'Yield %' in df_display.columns:
        format_dict['Yield %'] = '{:.2f}'
    if 'P/E' in df_display.columns:
        format_dict['P/E'] = '{:.1f}'
    if 'Margin %' in df_display.columns:
        format_dict['Margin %'] = '{:.1f}'
    if 'ROE %' in df_display.columns:
        format_dict['ROE %'] = '{:.1f}'
    if 'D/E' in df_display.columns:
        format_dict['D/E'] = '{:.0f}'
    if 'Payout %' in df_display.columns:
        format_dict['Payout %'] = '{:.1f}'
    if 'RSI' in df_display.columns:
        format_dict['RSI'] = '{:.1f}'
    if '% SMA200' in df_display.columns:
        format_dict['% SMA200'] = '{:.1f}'
    if 'MCap B$' in df_display.columns:
        format_dict['MCap B$'] = '{:.1f}'

    # Color by recommendation
    def highlight_recommendation(row):
        colors = []
        for col in row.index:
            if col == 'Signal':
                if row[col] == 'BUY':
                    colors.append('background-color: #1a472a; color: #4ade80')
                elif row[col] == 'WATCH':
                    colors.append('background-color: #422006; color: #fbbf24')
                else:
                    colors.append('background-color: #450a0a; color: #f87171')
            elif col == 'Score':
                val = row[col]
                if val >= 23:
                    colors.append('background-color: #1a472a; color: #4ade80')
                elif val >= 12:
                    colors.append('background-color: #422006; color: #fbbf24')
                else:
                    colors.append('background-color: #450a0a; color: #f87171')
            else:
                colors.append('')
        return colors

    selection_event = st.dataframe(
        df_display.style.apply(highlight_recommendation, axis=1).format(format_dict),
        use_container_width=True,
        height=500,
        on_select="rerun",
        selection_mode="single-row",
    )

    # --- Detail View ---
    selected_symbol = None
    if selection_event and hasattr(selection_event, 'selection') and selection_event.selection.rows:
        selected_idx = selection_event.selection.rows[0]
        selected_symbol = df_filtered.iloc[selected_idx]['symbol']

    if selected_symbol:
        row = df_filtered[df_filtered['symbol'] == selected_symbol].iloc[0]

        st.divider()
        st.subheader(f"📋 {row['company_name']} ({selected_symbol})")
        st.write(f"**Sektor:** {row['sector']} | **Industrie:** {row.get('industry', '-')} | **Land:** {row.get('country', '-')}")

        # External Links
        st.markdown(
            f"[📈 TradingView Chart](https://www.tradingview.com/chart/?symbol={selected_symbol}) | "
            f"[Finviz](https://finviz.com/quote.ashx?t={selected_symbol}) | "
            f"[Yahoo Finance](https://finance.yahoo.com/quote/{selected_symbol}) | "
            f"[Seeking Alpha Dividends](https://seekingalpha.com/symbol/{selected_symbol}/dividends)"
        )

        # Claude KI Analyse (Zahltagstrategie-Stil)
        claude_url = _create_zahltag_claude_url(selected_symbol, row)
        if claude_url:
            st.link_button(f"🤖 Zahltag-Analyse in Claude öffnen ({selected_symbol})", claude_url, use_container_width=True)

        # Score breakdown
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("### 🏛️ Fundamental (5 Kriterien)")
            with st.container(border=True):
                st.write(f"**P/E Ratio:** {row['trailing_pe']:.1f} → Punkte: **{row['score_pe']}/3**")
                st.write(f"**Profit Margin:** {row['profit_margin_pct']:.1f}% → Punkte: **{row['score_margin']}/3**")
                st.write(f"**EPS Growth:** {row['eps_growth_pct']:.1f}% → Punkte: **{row['score_eps_growth']}/3**" if not pd.isna(row['eps_growth_pct']) else "**EPS Growth:** N/A → Punkte: **1/3**")
                st.write(f"**Debt/Equity:** {row['debt_to_equity']:.0f} → Punkte: **{row['score_debt']}/3**" if not pd.isna(row['debt_to_equity']) else "**Debt/Equity:** N/A → Punkte: **1/3**")
                st.write(f"**ROE:** {row['roe_pct']:.1f}% → Punkte: **{row['score_roe']}/3**" if not pd.isna(row['roe_pct']) else "**ROE:** N/A → Punkte: **1/3**")
                st.metric("Fundamental-Score", f"{row['score_fundamental']}/15")

        with col2:
            st.markdown("### 💰 Dividend (5 Kriterien)")
            with st.container(border=True):
                st.write(f"**Yield:** {row['dividend_yield_pct']:.2f}% → Punkte: **{row['score_yield']}/3**")
                st.write(f"**Growth Years:** {int(row['dividend_growth_years']) if not pd.isna(row['dividend_growth_years']) else 'N/A'} → Punkte: **{row['score_div_years']}/3**")
                st.write(f"**Payout Ratio:** {row['payout_ratio_pct']:.1f}% → Punkte: **{row['score_payout']}/3**" if not pd.isna(row['payout_ratio_pct']) else "**Payout Ratio:** N/A → Punkte: **1/3**")
                st.write(f"**Div Growth (5Y vs Now):** → Punkte: **{row['score_div_growth']}/3**")
                st.write(f"**Klassifikation:** {row['dividend_classification'] or 'None'} → Punkte: **{row['score_classification']}/3**")
                st.metric("Dividend-Score", f"{row['score_dividend']}/15")

        with col3:
            st.markdown("### 📈 Technik (1 Kriterium)")
            with st.container(border=True):
                sma_txt = f"{row['pct_from_sma200']:.1f}%" if not pd.isna(row['pct_from_sma200']) else "N/A"
                rsi_txt = f"{row['rsi_14']:.1f}" if not pd.isna(row['rsi_14']) else "N/A"
                macd_txt = f"{row['macd_histogram']:.4f}" if not pd.isna(row['macd_histogram']) else "N/A"
                st.write(f"**% von SMA200:** {sma_txt}")
                st.write(f"**RSI (14):** {rsi_txt}")
                st.write(f"**MACD Histogram:** {macd_txt}")
                st.metric("Technik-Score", f"{row['score_technical']}/3")

            st.markdown("### 🎯 Gesamt")
            with st.container(border=True):
                total_score = row['score_total']
                rec = row['recommendation']
                emoji = '🟢' if rec == 'BUY' else ('🟡' if rec == 'WATCH' else '🔴')
                st.metric("Total Score", f"{total_score}/33")
                st.write(f"**Signal:** {emoji} **{rec}**")

                if rec == 'BUY':
                    st.success("Kaufen / Aufstocken - Starkes Gesamtbild")
                elif rec == 'WATCH':
                    st.warning("Beobachten - Gute Grundlage, wartet auf besseren Einstieg")
                else:
                    st.error("Papierkorb - Aktuell nicht geeignet")

    # Documentation
    with st.expander("ℹ️ Scoring-System (Nils Zahltagstrategie)"):
        st.markdown("""
        ### 11-Punkte-Matrix (Max 33 Punkte)

        **5 Fundamental-Kriterien (je 1-3 Punkte, max 15):**
        | Kriterium | 3 Punkte | 2 Punkte | 1 Punkt |
        |-----------|----------|----------|---------|
        | P/E | ≤ 15 | ≤ 25 | > 25 |
        | Profit Margin | ≥ 20% | ≥ 10% | < 10% |
        | EPS Growth | ≥ 15% | ≥ 5% | < 5% |
        | Debt/Equity | ≤ 50 | ≤ 150 | > 150 |
        | ROE | ≥ 20% | ≥ 10% | < 10% |

        **5 Dividend-Kriterien (je 1-3 Punkte, max 15):**
        | Kriterium | 3 Punkte | 2 Punkte | 1 Punkt |
        |-----------|----------|----------|---------|
        | Yield | 3-8% | 2-3% oder 8-10% | Rest |
        | Growth Years | ≥ 25 (Champion) | ≥ 10 (Contender) | < 10 |
        | Payout Ratio | 20-60% | 60-80% | Rest |
        | Div Growth Rate | Ratio ≥ 1.3 | Ratio ≥ 1.0 | < 1.0 |
        | Klassifikation | Champion | Contender/Challenger | None |

        **1 Technik-Kriterium (1-3 Punkte, max 3):**
        - Kombiniert: Kurs vs SMA200, RSI, MACD Histogram

        **Empfehlung:**
        - 🟢 ≥ 23 Punkte: **KAUFEN** (Aufstocken)
        - 🟡 12-22 Punkte: **BEOBACHTEN**
        - 🔴 < 12 Punkte: **PAPIERKORB**
        """)


if __name__ == "__main__":
    main()
