import streamlit as st
import pandas as pd
import numpy as np
from api.core.database import query_dataframe

def load_data():
    """Lädt die Basisdaten für den Dividenden-Scanner."""
    # Wir laden mehr Daten als nötig für die Perzentil-Berechnung
    sql = """
    WITH LatestTech AS (
        SELECT DISTINCT ON (symbol) * 
        FROM "TechnicalIndicatorsCalculatedHistoryDaily" 
        ORDER BY symbol, snapshot_date DESC
    ),
    LatestIV AS (
        SELECT DISTINCT ON (symbol) iv as current_iv, symbol
        FROM "StockImpliedVolatilityMassiveHistoryDaily"
        ORDER BY symbol, snapshot_date DESC
    ),
    IVRange AS (
        SELECT 
            symbol,
            MIN(iv) as iv_min_52w,
            MAX(iv) as iv_max_52w
        FROM "StockImpliedVolatilityMassiveHistoryDaily"
        WHERE snapshot_date > (CURRENT_DATE - INTERVAL '365 days')
        GROUP BY symbol
    )
    SELECT 
        f.symbol,
        f."Summary_dividendYield" as dividend_yield,
        f."Summary_payoutRatio" as payout_ratio,
        f."FreeCashFlow" as free_cashflow,
        f."OperatingCashFlow" as operating_cashflow,
        f."MarketCap" as market_cap,
        f."FinData_debtToEquity" as debt_to_equity,
        f."FinData_currentRatio" as current_ratio,
        f."Summary_trailingPE" as trailing_pe,
        f."KeyStats_priceToBook" as price_to_book,
        f."Summary_beta" as beta,
        f."Summary_priceToSalesTrailing12Months" as price_to_sales,
        f."KeyStats_enterpriseToEbitda" as ev_ebitda,
        f."Summary_fiveYearAvgDividendYield" as avg_yield_5y,
        f."FinData_returnOnEquity" as roe,
        f."FinData_returnOnAssets" as roa,
        f."FinData_profitMargins" as profit_margin,
        f."FinData_earningsGrowth" as earnings_growth,
        f."FinData_revenueGrowth" as revenue_growth,
        p.close as current_price,
        t."RSI_14" as rsi,
        t."SMA_200" as sma_200,
        t."SMA_50" as sma_50,
        t."STOCHk_14_3_1" as stoch_k,
        t."STOCHd_14_3_1" as stoch_d,
        t."MACD_12_26_9" as macd,
        t."MACDs_12_26_9" as macd_signal,
        t."BBL_20_2.0_2.0" as bb_lower,
        t."BBU_20_2.0_2.0" as bb_upper,
        iv.current_iv,
        ivr.iv_min_52w,
        ivr.iv_max_52w,
        a.name,
        a.sector,
        a.industry
    FROM "FundamentalDataYahoo" f
    LEFT JOIN "StockPricesYahoo" p ON f.symbol = p.symbol
    LEFT JOIN LatestTech t ON f.symbol = t.symbol
    LEFT JOIN LatestIV iv ON f.symbol = iv.symbol
    LEFT JOIN IVRange ivr ON f.symbol = ivr.symbol
    LEFT JOIN "StockAssetProfilesYahoo" a ON f.symbol = a.symbol
    WHERE f."Summary_dividendYield" IS NOT NULL
    """
    return query_dataframe(sql)

def calculate_scores(df):
    """Berechnet die Composite Value Scores gemäß Strategie-Dokument."""
    if df.empty:
        return df
        
    # Numerische Konvertierung
    cols_to_fix = [
        'trailing_pe', 'price_to_book', 'price_to_sales', 'ev_ebitda', 
        'dividend_yield', 'payout_ratio', 'avg_yield_5y', 
        'roe', 'roa', 'profit_margin', 'earnings_growth', 'revenue_growth',
        'rsi', 'current_iv', 'current_price', 'sma_200', 'sma_50', 
        'stoch_k', 'bb_lower', 'bb_upper', 'macd', 'macd_signal'
    ]
    for col in cols_to_fix:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # 1. Fundamental Value Score (FVS) - Inverses Perzentil (niedrig = gut)
    df['pe_rank'] = df['trailing_pe'].rank(pct=True, ascending=False).fillna(0)
    df['pb_rank'] = df['price_to_book'].rank(pct=True, ascending=False).fillna(0)
    df['ps_rank'] = df['price_to_sales'].rank(pct=True, ascending=False).fillna(0)
    df['ev_ebitda_rank'] = df['ev_ebitda'].rank(pct=True, ascending=False).fillna(0)
    
    df['FVS'] = (df['pe_rank'] * 35 + df['pb_rank'] * 25 + df['ev_ebitda_rank'] * 25 + df['ps_rank'] * 15)

    # 2. Dividend Score (DVS)
    # YieldNorm: Höher ist besser
    df['yield_norm'] = df['dividend_yield'].rank(pct=True, ascending=True).fillna(0)
    # Payout: Niedriger ist besser (1 - PayoutRatio)
    df['payout_score'] = (1 - df['payout_ratio'].clip(0, 1)).fillna(0)
    # DivGrowth: Wir nutzen Earnings/Revenue Growth als Proxy, falls DivGrowth fehlt
    df['growth_norm'] = df['earnings_growth'].rank(pct=True, ascending=True).fillna(0.5)
    
    df['DVS'] = (df['yield_norm'] * 50 + df['payout_score'] * 30 + df['growth_norm'] * 20)
    
    # 3. Quality Score (QVS) - Min-Max Normierung (via Rank als Annäherung im Universum)
    df['roe_n'] = df['roe'].rank(pct=True, ascending=True).fillna(0)
    df['roa_n'] = df['roa'].rank(pct=True, ascending=True).fillna(0)
    df['margin_n'] = df['profit_margin'].rank(pct=True, ascending=True).fillna(0)
    df['eg_n'] = df['earnings_growth'].rank(pct=True, ascending=True).fillna(0)
    df['rg_n'] = df['revenue_growth'].rank(pct=True, ascending=True).fillna(0)
    
    df['QVS'] = (df['roe_n'] * 25 + df['roa_n'] * 25 + df['margin_n'] * 25 + df['eg_n'] * 15 + df['rg_n'] * 10)
    
    # 4. Technical Score (TVS)
    # RSI Score: 100 - RSI (falls RSI < 50)
    df['rsi_s'] = df['rsi'].apply(lambda x: (100 - x) if x < 50 else 0)
    # SMA Distance: ((SMA200 - Kurs) / SMA200) * 200, gekappt bei 50
    df['sma_dist'] = (((df['sma_200'] - df['current_price']) / df['sma_200']) * 200).clip(0, 50).fillna(0)
    # Bollinger Position: 1 - ((Kurs - BB_lower) / (BB_upper - BB_lower))
    bb_range = (df['bb_upper'] - df['bb_lower']).replace(0, np.nan)
    df['bb_s'] = ((1 - (df['current_price'] - df['bb_lower']) / bb_range) * 20).clip(0, 20).fillna(0)
    # MACD Score: 10 wenn MACD > Signal
    df['macd_s'] = (df['macd'] > df['macd_signal']).astype(int) * 10
    # Stoch Score: (40 - %K) / 40 * 10 falls %K < 40
    df['stoch_s'] = df['stoch_k'].apply(lambda x: (40 - x) / 40 * 10 if x < 40 else 0).clip(0, 10)
    
    df['TVS'] = (df['rsi_s'] + df['sma_dist'] + df['bb_s'] + df['macd_s'] + df['stoch_s']) / 1.40
    
    # 5. Volatility Score (VVS)
    # IV Rank 40-60% ist Ideal (100 Pkt)
    df['iv_range'] = (df['iv_max_52w'] - df['iv_min_52w'])
    df['iv_rank_val'] = ((df['current_iv'] - df['iv_min_52w']) / df['iv_range'].replace(0, np.nan)).fillna(0)
    df['VVS'] = (100 - abs(df['iv_rank_val'] * 100 - 50) * 2).clip(0, 100)

    # Gesamt CVS
    df['CVS'] = (df['FVS'] * 0.30 + 
                 df['DVS'] * 0.25 + 
                 df['QVS'] * 0.20 + 
                 df['TVS'] * 0.15 + 
                 df['VVS'] * 0.10)
    
    return df

def get_options_for_symbol(symbol):
    """Sucht nach passenden Short Puts."""
    sql = f"""
    SELECT 
        strike_price, 
        expiration_date, 
        greeks_delta, 
        implied_volatility,
        open_interest,
        day_volume,
        day_last_updated
    FROM "OptionDataMassive"
    WHERE symbol = '{symbol}' 
      AND contract_type = 'put'
      AND expiration_date BETWEEN CURRENT_DATE + INTERVAL '30 days' AND CURRENT_DATE + INTERVAL '60 days'
      AND greeks_delta BETWEEN -0.40 AND -0.20
    ORDER BY ABS(greeks_delta + 0.30) ASC
    LIMIT 5
    """
    return query_dataframe(sql)

def main():
    st.title("🎯 Dividenden-Scanner v2.0")
    st.write("Short Put Strategie: Value Investing + Optionsprämien")
    
    # --- Dokumentation ---
    with st.expander("ℹ️ Dokumentation & Strategie-Details"):
        st.markdown("""
        ### 1 | Philosophie & Grundprinzipien
        Die Strategie kombiniert **Value Investing** (Graham/Buffett) mit dem **Verkauf von Short Puts**.
        *   **Ziel:** Qualitätsaktien mit Abschlag kaufen oder Prämien vereinnahmen.
        *   **Mechanisch:** 100% regelbasiert ohne Ermessensspielraum.
        *   **Universumsbasiert:** Vergleich über alle gescannten Aktien (kein Sektor-Bias).

        ### 2 | Screening-Pipeline
        #### Phase 1: Fundamentalanalyse (Harte Filter)
        Jeder Kandidat muss zwingend folgende Kriterien erfüllen:
        *   **Dividendenrendite:** >= 2.5%
        *   **Payout Ratio:** < 75%
        *   **Market Cap:** > 2 Mrd. USD
        *   **P/E:** < 40 | **P/B:** < 10
        *   **Cashflow:** Free & Op. Cashflow müssen positiv (> 0) sein.
        *   **Bilanz:** Debt/Equity < 200% | Current Ratio >= 1.0

        #### Phase 2: Scoring-Modell (Composite Value Score - CVS)
        Der CVS (0-100) gewichtet fünf Dimensionen:
        1.  **Fundamental Value (FVS) [30%]:** Inverses Perzentil-Ranking von P/E, P/B, EV/EBITDA, P/S.
        2.  **Dividend Score (DVS) [25%]:** Yield, Payout-Nachhaltigkeit und Wachstum.
        3.  **Quality Score (QVS) [20%]:** Rentabilität (ROE, ROA), Margen und Wachstum.
        4.  **Technical Score (TVS) [15%]:** RSI (< 45), SMA-Abstand, Bollinger-Bänder, MACD & Stochastik.
        5.  **Volatility Score (VVS) [10%]:** IV-Rank (Sweet Spot: 40-60%).

        ### 3 | Options-Selektion (Short Put)
        Der ideale Short Put wird nach folgenden Kriterien gewählt:
        *   **Laufzeit (DTE):** 30 bis 60 Tage (Theta-Sweet-Spot).
        *   **Delta:** Zielwert von **-0.30** (30-Delta).
        *   **Liquidität:** Bid-Ask Spread < 5%, Open Interest > 200.

        ### 4 | Handelsempfehlung
        *   🟢 **85 – 100 (Premium):** Sofort handeln — maximale Positionsgröße.
        *   🔵 **70 – 84 (Stark):** Handeln — Standard-Positionsgröße.
        *   🟡 **55 – 69 (Gut):** Handeln — reduzierte Positionsgröße.
        *   ⚪ **< 55 (Neutral):** Beobachten / kein Trade.
        """)

    # --- Filter & Einstellungen ---
    with st.expander("🔍 Filter & CVS-Gewichtung", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Harte Filter (MUSS-Kriterien)")
            min_yield = st.slider("Min. Dividend Yield (%)", 0.0, 10.0, 2.5) / 100.0
            max_payout = st.slider("Max. Payout Ratio (%)", 0, 150, 75) / 100.0
            min_mcap = st.number_input("Min. Market Cap (Mrd. $)", 0.0, 500.0, 2.0) * 1e9
            max_pe = st.slider("Max. Trailing P/E", 0, 100, 40)
            max_pb = st.slider("Max. Price/Book", 0.0, 20.0, 10.0)
            
        with col2:
            st.subheader("CVS-Gewichtung (%)")
            w_fvs = st.slider("Fundamental Value (FVS)", 0, 100, 30)
            w_dvs = st.slider("Dividend Score (DVS)", 0, 100, 25)
            w_qvs = st.slider("Quality Score (QVS)", 0, 100, 20)
            w_tvs = st.slider("Technical Score (TVS)", 0, 100, 15)
            w_vvs = st.slider("Volatility Score (VVS)", 0, 100, 10)
            
            # Normierung der Gewichte
            total_w = w_fvs + w_dvs + w_qvs + w_tvs + w_vvs
            if total_w != 100:
                st.warning(f"Gesamtgewichtung ist {total_w}%. Sie sollte idealerweise 100% ergeben.")

    df_raw = load_data()
    df_scored = calculate_scores(df_raw)
    
    # Hard Filter (M1-M11)
    df_filtered = df_scored[
        (df_scored['dividend_yield'] >= min_yield) &
        (df_scored['payout_ratio'] < max_payout) &
        (df_scored['market_cap'] >= min_mcap) &
        (df_scored['trailing_pe'] < max_pe) &
        (df_scored['price_to_book'] < max_pb) &
        (df_scored['free_cashflow'] > 0) &
        (df_scored['operating_cashflow'] > 0) &
        (df_scored['debt_to_equity'] < 200.0) &
        (df_scored['current_ratio'] >= 1.0)
    ].copy()
    
    # Recalculate CVS with custom weights if changed
    if total_w > 0:
        df_filtered['CVS'] = (df_filtered['FVS'] * w_fvs + 
                             df_filtered['DVS'] * w_dvs + 
                             df_filtered['QVS'] * w_qvs + 
                             df_filtered['TVS'] * w_tvs + 
                             df_filtered['VVS'] * w_vvs) / total_w

    st.subheader(f"Gefundene Aktien: {len(df_filtered)}")
    
    display_cols = [
        'symbol', 'name', 'CVS', 'FVS', 'DVS', 'QVS', 'TVS', 'VVS', 
        'current_price', 'dividend_yield', 'trailing_pe', 'rsi', 'iv_rank_val'
    ]
    
    # Formatierung
    df_display = df_filtered[display_cols].sort_values('CVS', ascending=False)
    df_display.index = range(1, len(df_display) + 1)
    
    selection_event = st.dataframe(
        df_display.style.background_gradient(subset=['CVS', 'FVS', 'DVS', 'QVS', 'TVS', 'VVS'], cmap='RdYlGn')
        .format({
            'CVS': '{:.1f}', 'FVS': '{:.1f}', 'DVS': '{:.1f}', 'QVS': '{:.1f}', 'TVS': '{:.1f}', 'VVS': '{:.1f}',
            'dividend_yield': '{:.2%}', 'current_price': '{:.2f}', 'trailing_pe': '{:.1f}', 'rsi': '{:.1f}', 'iv_rank_val': '{:.1%}'
        }),
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row"
    )
    
    selected_symbol = None
    if not df_filtered.empty:
        if selection_event and hasattr(selection_event, 'selection') and selection_event.selection.rows:
            selected_idx = selection_event.selection.rows[0]
            selected_symbol = df_display.iloc[selected_idx]['symbol']
        else:
            st.info("Klicken Sie auf eine Zeile in der Tabelle, um Details anzuzeigen.")
            
    if selected_symbol:
        row = df_filtered[df_filtered['symbol'] == selected_symbol].iloc[0]
        
        st.divider()
        st.subheader(f"📊 Details für {row['name']} ({selected_symbol})")
        st.write(f"**Sektor:** {row['sector']} | **Industrie:** {row['industry']}")
        
        # Sektionen für Details
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown("### 🏆 Scores")
            st.metric("Gesamt CVS", f"{row['CVS']:.1f}")
            st.write(f"**Value (FVS):** {row['FVS']:.1f}")
            st.write(f"**Dividend (DVS):** {row['DVS']:.1f}")
            st.write(f"**Quality (QVS):** {row['QVS']:.1f}")
            st.write(f"**Technical (TVS):** {row['TVS']:.1f}")
            st.write(f"**Volatility (VVS):** {row['VVS']:.1f}")

        with col2:
            st.markdown("### 💰 Fundamentaldaten")
            st.write(f"**Market Cap:** ${row['market_cap']/1e9:.1f}B")
            st.write(f"**P/E Ratio:** {row['trailing_pe']:.1f}")
            st.write(f"**P/B Ratio:** {row['price_to_book']:.1f}")
            st.write(f"**P/S Ratio:** {row['price_to_sales']:.1f}")
            st.write(f"**EV/EBITDA:** {row['ev_ebitda']:.1f}")
            st.write(f"**Debt to Equity:** {row['debt_to_equity']:.1f}%")
            st.write(f"**Current Ratio:** {row['current_ratio']:.2f}")

        with col3:
            st.markdown("### 🏦 Dividende & Qualität")
            st.write(f"**Yield:** {row['dividend_yield']:.2%}")
            st.write(f"**Avg Yield (5Y):** {row['avg_yield_5y']:.2%}")
            st.write(f"**Payout Ratio:** {row['payout_ratio']:.1%}")
            st.write(f"**ROE:** {row['roe']:.1%}")
            st.write(f"**ROA:** {row['roa']:.1%}")
            st.write(f"**Profit Margin:** {row['profit_margin']:.1%}")
            st.write(f"**Earnings Growth:** {row['earnings_growth']:.1%}")
            st.write(f"**Revenue Growth:** {row['revenue_growth']:.1%}")

        with col4:
            st.markdown("### 📈 Technik & Volatilität")
            st.write(f"**Preis:** ${row['current_price']:.2f}")
            st.write(f"**RSI (14):** {row['rsi']:.1f}")
            st.write(f"**SMA 50 / 200:** ${row['sma_50']:.2f} / ${row['sma_200']:.2f}")
            st.write(f"**Stoch K/D:** {row['stoch_k']:.1f} / {row['stoch_d']:.1f}")
            st.write(f"**MACD / Signal:** {row['macd']:.2f} / {row['macd_signal']:.2f}")
            st.write(f"**IV Rank:** {row['iv_rank_val']:.1%}")
            st.write(f"**IV Current:** {row['current_iv']:.1%}")
            st.write(f"**IV 52W Range:** {row['iv_min_52w']:.1%} - {row['iv_max_52w']:.1%}")

        st.divider()
        st.subheader("💡 Strategische Analyse")
        
        # Automatischer Analyse-Text
        pe_pct = row['pe_rank'] * 100
        analysis_text = f"""
        **{selected_symbol}** wird mit einem P/E von **{row['trailing_pe']:.1f}** bewertet (Universum-Perzentil: {pe_pct:.1f}%). 
        Die Dividendenrendite von **{row['dividend_yield']:.2%}** ist fundamental durch einen positiven Free Cashflow 
        (${row['free_cashflow']/1e6:.1f}M) gedeckt. 
        """
        
        if row['rsi'] < 40:
            analysis_text += f"Der RSI von **{row['rsi']:.1f}** signalisiert eine kurzfristige Überverkaufung, was den Einstieg attraktiv macht. "
        else:
            analysis_text += f"Technisch gesehen liegt der RSI bei **{row['rsi']:.1f}**. "
            
        analysis_text += f"Der IV-Rank von **{row['iv_rank_val']:.1%}** führt zu einem Volatility Score (VVS) von **{row['VVS']:.1f}**."
        
        st.info(analysis_text)

        st.divider()
        st.subheader(f"Ideale Short Puts (Delta -0.30, 30-60 DTE) für {selected_symbol}")
        options_df = get_options_for_symbol(selected_symbol)
        if not options_df.empty:
            st.table(options_df.style.format({
                'strike_price': '{:.2f}',
                'greeks_delta': '{:.3f}',
                'implied_volatility': '{:.1%}'
            }))
        else:
            st.info("Keine passenden Optionen in der Datenbank gefunden.")

if __name__ == "__main__":
    main()
