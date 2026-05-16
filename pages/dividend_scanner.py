import streamlit as st
import pandas as pd
import numpy as np
from api.core.database import query_dataframe
from datetime import datetime, timedelta

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
        p.close as current_price,
        t."RSI_14" as rsi,
        t."SMA_200" as sma_200,
        t."SMA_50" as sma_50,
        t."STOCHk_14_3_1" as stoch_k,
        t."STOCHd_14_3_1" as stoch_d,
        iv.current_iv,
        ivr.iv_min_52w,
        ivr.iv_max_52w,
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
    """Berechnet die Composite Value Scores."""
    if df.empty:
        return df
        
    # Perzentile berechnen (0 bis 1)
    # Fundamental Value: Niedriger ist besser für PE, PB, PS, EV/EBITDA
    # Wir verwenden dropna() für das Ranking oder füllen mit Median
    for col in ['trailing_pe', 'price_to_book', 'price_to_sales', 'ev_ebitda', 'dividend_yield', 'payout_ratio', 'avg_yield_5y', 'roe', 'roa', 'profit_margin', 'rsi', 'current_iv']:
        if col not in df.columns: continue
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df['pe_rank'] = df['trailing_pe'].rank(pct=True, ascending=False).fillna(0)
    df['pb_rank'] = df['price_to_book'].rank(pct=True, ascending=False).fillna(0)
    df['ps_rank'] = df['price_to_sales'].rank(pct=True, ascending=False).fillna(0)
    df['ev_ebitda_rank'] = df['ev_ebitda'].rank(pct=True, ascending=False).fillna(0)
    
    # Dividend: Höher ist besser für Yield, niedriger besser für Payout
    df['yield_rank'] = df['dividend_yield'].rank(pct=True, ascending=True).fillna(0)
    df['payout_rank'] = df['payout_ratio'].rank(pct=True, ascending=False).fillna(0)
    # 5Y Avg Yield Vergleich: Aktuell > 5Y Avg ist gut
    df['yield_vs_avg'] = (df['dividend_yield'] / df['avg_yield_5y']).replace([np.inf, -np.inf], np.nan)
    df['yield_vs_avg_rank'] = df['yield_vs_avg'].rank(pct=True, ascending=True).fillna(0)
    
    # Quality: Höher ist besser für ROE, ROA, Margin
    df['roe_rank'] = df['roe'].rank(pct=True, ascending=True).fillna(0)
    df['roa_rank'] = df['roa'].rank(pct=True, ascending=True).fillna(0)
    df['margin_rank'] = df['profit_margin'].rank(pct=True, ascending=True).fillna(0)
    
    # Technical: Niedriger RSI ist besser (Oversold)
    df['rsi_rank'] = df['rsi'].rank(pct=True, ascending=False).fillna(0)
    # Distance to SMA200 (Pullback is good)
    df['dist_sma200'] = (df['current_price'] / df['sma_200']).replace([np.inf, -np.inf], np.nan)
    df['sma200_rank'] = df['dist_sma200'].rank(pct=True, ascending=False).fillna(0)
    
    # Volatility: IV Rank
    df['iv_range'] = (df['iv_max_52w'] - df['iv_min_52w'])
    df['iv_rank'] = ((df['current_iv'] - df['iv_min_52w']) / df['iv_range'].replace(0, np.nan)).fillna(0)
    # VVS Peak bei 40-60%. Wir mappen 0.5 auf 1.0, 0 und 1 auf 0.
    df['vvs_score'] = 1.0 - abs(df['iv_rank'] - 0.5) * 2
    df['vvs_score'] = df['vvs_score'].clip(0, 1)

    # Composite Scores (0-100)
    df['FVS'] = df[['pe_rank', 'pb_rank', 'ps_rank', 'ev_ebitda_rank']].mean(axis=1) * 100
    df['DVS'] = df[['yield_rank', 'payout_rank', 'yield_vs_avg_rank']].mean(axis=1) * 100
    df['QVS'] = df[['roe_rank', 'roa_rank', 'margin_rank']].mean(axis=1) * 100
    df['TVS'] = df[['rsi_rank', 'sma200_rank']].mean(axis=1) * 100
    df['VVS'] = df['vvs_score'] * 100
    
    # CVS: 30% FVS, 25% DVS, 20% QVS, 15% TVS, 10% VVS
    df['CVS'] = (df['FVS'].fillna(0) * 0.30 + 
                 df['DVS'].fillna(0) * 0.25 + 
                 df['QVS'].fillna(0) * 0.20 + 
                 df['TVS'].fillna(0) * 0.15 + 
                 df['VVS'].fillna(0) * 0.10)
    
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
    
    with st.sidebar:
        st.header("Filter-Einstellungen")
        min_yield = st.slider("Min. Dividend Yield (%)", 0.0, 10.0, 2.5) / 100.0
        max_payout = st.slider("Max. Payout Ratio (%)", 0, 150, 75) / 100.0
        min_mcap = st.number_input("Min. Market Cap (Mrd. $)", 0.0, 500.0, 2.0) * 1e9
        max_pe = st.slider("Max. Trailing P/E", 0, 100, 40)
        max_pb = st.slider("Max. Price/Book", 0.0, 20.0, 10.0)
        
        st.divider()
        st.subheader("Gewichtung (CVS)")
        w_fvs = st.slider("Fundamental Value (FVS)", 0, 100, 30)
        w_dvs = st.slider("Dividend Score (DVS)", 0, 100, 25)
        w_qvs = st.slider("Quality Score (QVS)", 0, 100, 20)
        w_tvs = st.slider("Technical Score (TVS)", 0, 100, 15)
        w_vvs = st.slider("Volatility Score (VVS)", 0, 100, 10)
        
        # Normierung der Gewichte
        total_w = w_fvs + w_dvs + w_qvs + w_tvs + w_vvs
        
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
        (df_scored['operating_cashflow'] > 0)
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
        'symbol', 'CVS', 'FVS', 'DVS', 'QVS', 'TVS', 'VVS', 
        'current_price', 'dividend_yield', 'trailing_pe', 'rsi', 'iv_rank'
    ]
    
    # Formatierung
    df_display = df_filtered[display_cols].sort_values('CVS', ascending=False)
    
    st.dataframe(
        df_display.style.background_gradient(subset=['CVS', 'FVS', 'DVS', 'QVS', 'TVS', 'VVS'], cmap='RdYlGn')
        .format({
            'CVS': '{:.1f}', 'FVS': '{:.1f}', 'DVS': '{:.1f}', 'QVS': '{:.1f}', 'TVS': '{:.1f}', 'VVS': '{:.1f}',
            'dividend_yield': '{:.2%}', 'current_price': '{:.2f}', 'trailing_pe': '{:.1f}', 'rsi': '{:.1f}', 'iv_rank': '{:.1%}'
        })
    )
    
    if not df_filtered.empty:
        selected_symbol = st.selectbox("Aktie für Details wählen", df_filtered['symbol'].tolist())
        row = df_filtered[df_filtered['symbol'] == selected_symbol].iloc[0]
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("CVS Score", f"{row['CVS']:.1f}")
            st.write(f"**Sektor:** {row['sector']}")
            st.write(f"**Industrie:** {row['industry']}")
        with col2:
            st.write(f"**Market Cap:** ${row['market_cap']/1e9:.1f}B")
            st.write(f"**Yield:** {row['dividend_yield']:.2%}")
            st.write(f"**Payout:** {row['payout_ratio']:.1%}")
        with col3:
            st.write(f"**P/E:** {row['trailing_pe']:.1f}")
            st.write(f"**RSI:** {row['rsi']:.1f}")
            st.write(f"**IV Rank:** {row['iv_rank']:.1%}")

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
