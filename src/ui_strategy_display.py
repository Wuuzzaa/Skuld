import streamlit as st
import pandas as pd
import logging
import os
import urllib.parse
from datetime import datetime
from typing import List, Optional
from src.options_utils import OptionLeg, StrategyMetrics

logger = logging.getLogger(os.path.basename(__file__))

def display_strategy_details(
    symbol: str,
    company_name: str,
    legs: List[OptionLeg],
    metrics: StrategyMetrics,
    extra_info: Optional[dict] = None
):
    """
    Displays the details of an options strategy in a standardized way.
    """
    st.markdown(f"### Details für {symbol}")
    
    # 1. Legs Table
    legs_data = []
    for i, leg in enumerate(legs):
        # Format last_updated if it's a timestamp
        updated_str_massive = leg.last_updated_massive
        updated_str_option_data = leg.last_updated_option_data
        updated_str_stock_data = leg.last_updated_stock_data
        if isinstance(updated_str_massive, (pd.Timestamp, datetime)):
            updated_str_massive = updated_str_massive.strftime('%d.%m.%Y %H:%M')      
        elif pd.isna(updated_str_massive):
            updated_str_massive = "N/A"
        if isinstance(updated_str_option_data, (pd.Timestamp, datetime)):
            updated_str_option_data = leg.last_updated_option_data.strftime('%d.%m.%Y %H:%M')
        elif pd.isna(updated_str_option_data):
            updated_str_option_data = "N/A"
        if isinstance(updated_str_stock_data, (pd.Timestamp, datetime)):
            updated_str_stock_data = leg.last_updated_stock_data.strftime('%d.%m.%Y %H:%M')
        elif pd.isna(updated_str_stock_data):
            updated_str_stock_data = "N/A"


        legs_data.append({
            "Leg": f"Leg {i+1}",
            "Type": "Call" if leg.is_call else "Put",
            "Action": "Long" if leg.is_long else "Short",
            "Strike": leg.strike,
            "Price": leg.premium,
            "BS Price": leg.bs_price if leg.bs_price is not None else "—",
            "Delta": leg.delta,
            "IV": leg.iv,
            "Theta": leg.theta,
            "OI": leg.oi,
            "Volume": leg.volume,
            "Exp Move": leg.expected_move,
            "Updated_Massive": updated_str_massive,
            "Updated_OptionData": updated_str_option_data,
            "Updated_StockData": updated_str_stock_data
        })

    details_df = pd.DataFrame(legs_data)

    # Color-code BS Price comparison: green if market > BS (overpriced, good for sellers), red otherwise
    def _highlight_bs(row):
        styles = [''] * len(row)
        bs_idx = details_df.columns.get_loc('BS Price')
        price_idx = details_df.columns.get_loc('Price')
        if row['BS Price'] != '—' and row['BS Price'] is not None and row['Price'] is not None:
            try:
                bs_val = float(row['BS Price'])
                price_val = float(row['Price'])
                if price_val > bs_val:
                    styles[bs_idx] = 'background-color: #90EE90; color: #000000; font-weight: bold'  # light green background with black text
                else:
                    styles[bs_idx] = 'background-color: #FFB6B6; color: #000000; font-weight: bold'  # light red background with black text
            except (ValueError, TypeError):
                pass
        return styles

    styled_df = details_df.style.apply(_highlight_bs, axis=1)
    st.dataframe(styled_df, hide_index=True, use_container_width=True)
    
    # 2. Key Metrics
    st.markdown("#### Kennzahlen & Unternehmensinfos")
    # Wikipedia: erst DE versuchen, Fallback auf EN
    wiki_name = urllib.parse.quote(company_name)
    wiki_url = f"https://de.wikipedia.org/w/index.php?search={wiki_name}&ns0=1"
    st.markdown(f"**Unternehmen:** [{company_name}]({wiki_url})")

    col_info1, col_info2, col_info3, col_info4 = st.columns(4)
    with col_info1:
        st.metric("Max Profit", f"${metrics.max_profit:.2f}")
        st.metric("BPR", f"${metrics.bpr:.2f}")
    with col_info2:
        st.metric("Expected Value", f"${metrics.expected_value:.2f}")
        st.metric("APDI", f"{metrics.apdi:.2f}%")
    with col_info3:
        if extra_info:
            iv_rank = extra_info.get('iv_rank')
            st.metric("IV Rank", f"{iv_rank:.1f}" if pd.notnull(iv_rank) else "N/A")
            iv_percentile = extra_info.get('iv_percentile')
            st.metric("IV Percentile", f"{iv_percentile:.1f}" if pd.notnull(iv_percentile) else "N/A")
    with col_info4:
        # Sell IV (Average) - we can calculate it from legs or pass it
        avg_sell_iv = sum(leg.iv for leg in legs if not leg.is_long) / sum(1 for leg in legs if not leg.is_long) if any(not leg.is_long for leg in legs) else 0
        st.metric("Sell IV (Avg)", f"{avg_sell_iv*100:.1f}%")
        st.metric("Theta", f"{metrics.total_theta:.4f}")

    # IV Correction info
    iv_corr_display = f"{metrics.iv_correction_factor*100:.1f}%"
    st.write(f"**IV Correction Factor:** {iv_corr_display}")
    
    if extra_info:
        st.write(f"**Sektor:** {extra_info.get('company_sector', 'N/A')} | **Branche:** {extra_info.get('company_industry', 'N/A')}")
        if 'analyst_mean_target' in extra_info and pd.notnull(extra_info['analyst_mean_target']):
            st.write(f"**Analyst Kursziel:** ${extra_info['analyst_mean_target']:.2f}$ (Aktuell: ${extra_info.get('close', 0):.2f}$)")

    # Technische Signale
    tech = extra_info.get('tech_indicators') if extra_info else None
    if tech is not None:
        st.markdown("#### Technische Signale")
        tc1, tc2, tc3, tc4 = st.columns(4)

        stoch_k = tech.get('STOCHk_14_3_1')
        stoch_h = tech.get('STOCHh_14_3_1')
        rsi = tech.get('RSI_14')
        ema200 = tech.get('EMA_200')
        close = extra_info.get('close') if extra_info else None

        with tc1:
            val = f"{stoch_k:.1f}" if pd.notnull(stoch_k) else "N/A"
            st.metric("Stoch %K", val, help="< 20 = überverkauft, > 80 = überkauft")
        with tc2:
            val = f"{stoch_h:.2f}" if pd.notnull(stoch_h) else "N/A"
            delta_str = "↑ K über D" if pd.notnull(stoch_h) and stoch_h > 0 else ("↓ K unter D" if pd.notnull(stoch_h) else None)
            st.metric("Stoch Hist", val, delta=delta_str, help="= %K − %D · positiv = Momentum dreht nach oben")
        with tc3:
            val = f"{rsi:.1f}" if pd.notnull(rsi) else "N/A"
            st.metric("RSI 14", val, help="< 40 = Pullback-Zone für Bull Put Spreads")
        with tc4:
            if pd.notnull(ema200) and pd.notnull(close):
                abstand = ((close - ema200) / ema200) * 100
                trend = "✅ über EMA200" if close > ema200 else "⚠️ unter EMA200"
                st.metric("Trend (EMA200)", trend, delta=f"{abstand:+.1f}%")
            else:
                st.metric("Trend (EMA200)", "N/A")

        # Gesamtsignal Bull Put
        if all(pd.notnull(v) for v in [stoch_k, stoch_h, rsi, ema200, close]):
            signals = [
                close > ema200,
                stoch_k < 20,
                stoch_h > 0,
                rsi < 45,
            ]
            score = sum(signals)
            labels = ["Kurs > EMA200", "Stoch < 20", "Stoch dreht hoch", "RSI < 45"]
            met = [l for l, s in zip(labels, signals) if s]
            not_met = [l for l, s in zip(labels, signals) if not s]
            if score == 4:
                st.success(f"**Bull-Put-Signal: {score}/4** — Alle Kriterien erfüllt: {', '.join(met)}")
            elif score >= 2:
                st.info(f"**Bull-Put-Signal: {score}/4** — Erfüllt: {', '.join(met) or '—'}  |  Fehlt: {', '.join(not_met) or '—'}")
            else:
                st.warning(f"**Bull-Put-Signal: {score}/4** — Fehlt: {', '.join(not_met)}")

    # Fundamental-Ampel
    fd = extra_info.get('fundamental') if extra_info else None
    if fd is not None and any(pd.notnull(fd.get(k)) for k in [
        'FinData_currentRatio', 'FinData_debtToEquity', 'FinData_returnOnEquity',
        'FinData_revenueGrowth', 'FinData_recommendationKey', 'KeyStats_shortPercentOfFloat',
        'KeyStats_beta', 'FinData_profitMargins', 'FinData_grossMargins', 'FreeCashFlow',
    ]):
        st.markdown("#### Fundamental-Ampel")

        def _ampel(ok, warn, label, val_str, help_txt):
            icon = "🟢" if ok else ("🟡" if warn else "🔴")
            st.metric(f"{icon} {label}", val_str, help=help_txt)

        fc1, fc2, fc3, fc4 = st.columns(4)
        fund_signals = []

        current_ratio = fd.get('FinData_currentRatio')
        debt_eq       = fd.get('FinData_debtToEquity')
        roe           = fd.get('FinData_returnOnEquity')
        rev_growth    = fd.get('FinData_revenueGrowth')
        rec_key       = fd.get('FinData_recommendationKey')
        short_pct     = fd.get('KeyStats_shortPercentOfFloat')
        beta          = fd.get('KeyStats_beta')
        profit_margin = fd.get('FinData_profitMargins')
        gross_margin  = fd.get('FinData_grossMargins')
        fcf           = fd.get('FreeCashFlow')

        with fc1:
            if pd.notnull(current_ratio):
                ok = current_ratio >= 1.5; warn = current_ratio >= 1.0
                _ampel(ok, warn, "Current Ratio", f"{current_ratio:.2f}",
                       "≥ 1.5 = solide, < 1.0 = kurzfristig unter Druck")
                fund_signals.append(ok or warn)
            if pd.notnull(debt_eq):
                ok = debt_eq < 50; warn = debt_eq < 150
                _ampel(ok, warn, "Debt/Equity", f"{debt_eq:.1f}%",
                       "< 50% = konservativ, > 150% = hohe Verschuldung")
                fund_signals.append(ok or warn)

        with fc2:
            if pd.notnull(roe):
                ok = roe > 0.15; warn = roe > 0
                _ampel(ok, warn, "ROE", f"{roe*100:.1f}%",
                       "> 15% = starke Kapitalrendite, < 0% = Verlust")
                fund_signals.append(ok or warn)
            if pd.notnull(profit_margin):
                ok = profit_margin > 0.10; warn = profit_margin > 0
                _ampel(ok, warn, "Profit Margin", f"{profit_margin*100:.1f}%",
                       "> 10% = profitabel, < 0% = Verlustzone")
                fund_signals.append(ok or warn)

        with fc3:
            if pd.notnull(rev_growth):
                ok = rev_growth > 0.05; warn = rev_growth > -0.05
                _ampel(ok, warn, "Rev. Wachstum", f"{rev_growth*100:.1f}%",
                       "> 5% = wächst, < -5% = schrumpft")
                fund_signals.append(ok or warn)
            if pd.notnull(gross_margin):
                ok = gross_margin > 0.40; warn = gross_margin > 0.20
                _ampel(ok, warn, "Gross Margin", f"{gross_margin*100:.1f}%",
                       "> 40% = hohes Pricing Power, < 20% = commodity-artig")
                fund_signals.append(ok or warn)

        with fc4:
            if pd.notnull(beta):
                ok = beta < 1.5; warn = beta < 2.0
                _ampel(ok, warn, "Beta", f"{beta:.2f}",
                       "< 1.5 = moderat volatil, > 2.0 = sehr volatil")
                fund_signals.append(ok or warn)
            if pd.notnull(short_pct):
                ok = short_pct < 0.05; warn = short_pct < 0.15
                _ampel(ok, warn, "Short Interest", f"{short_pct*100:.1f}%",
                       "< 5% = kein Druck, > 15% = viele wetten gegen die Aktie")
                fund_signals.append(ok or warn)

        # Analystenmeinung + FCF als Text
        info_parts = []
        if pd.notnull(rec_key):
            rec_icons = {"strong_buy": "🟢 Strong Buy", "buy": "🟢 Buy",
                         "hold": "🟡 Hold", "sell": "🔴 Sell", "strong_sell": "🔴 Strong Sell"}
            info_parts.append(f"**Analysten:** {rec_icons.get(rec_key, rec_key)}")
        if pd.notnull(fcf) and fcf != 0:
            fcf_b = fcf / 1e9
            fcf_icon = "🟢" if fcf > 0 else "🔴"
            info_parts.append(f"**Free Cash Flow:** {fcf_icon} {fcf_b:+.1f}B")
        if info_parts:
            st.write("  |  ".join(info_parts))

        # Gesamturteil
        if fund_signals:
            green = sum(fund_signals)
            total = len(fund_signals)
            if green == total:
                st.success(f"**Fundamental: {green}/{total}** — Alle Kennzahlen im grünen Bereich")
            elif green >= total * 0.6:
                st.info(f"**Fundamental: {green}/{total}** — Überwiegend solide")
            else:
                st.warning(f"**Fundamental: {green}/{total}** — Mehrere Warnsignale")

    # 3. External Links
    display_external_links(symbol, extra_info)

def display_external_links(symbol: str, extra_info: Optional[dict] = None):
    """
    Displays external analysis links for a given symbol.
    """
    st.markdown("#### Links")
    link_col1, link_col2, link_col3, link_col4 = st.columns(4)
    with link_col1:
        st.link_button("TradingView", f"https://www.tradingview.com/symbols/{symbol}/", width="stretch")
        st.link_button("Chart", f"https://www.tradingview.com/chart/?symbol={symbol}", width="stretch")
    with link_col2:
        st.link_button("Finviz", f"https://finviz.com/quote.ashx?t={symbol}", width="stretch")
        if extra_info and 'optionstrat_url' in extra_info and extra_info['optionstrat_url']:
            st.link_button("OptionStrat", extra_info['optionstrat_url'], width="stretch")
    with link_col3:
        st.link_button("Seeking Alpha", f"https://seekingalpha.com/symbol/{symbol}", width="stretch")
        if extra_info and 'Claude' in extra_info and extra_info['Claude']:
            st.link_button("Claude AI Analysis", extra_info['Claude'], width="stretch")
    with link_col4:
        st.link_button("Yahoo Finance", f"https://finance.yahoo.com/quote/{symbol}", width="stretch")
