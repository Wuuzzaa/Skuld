"""
Roll & Screen — Wheel-Ablauf für Cash-Secured Puts.

Zwei Tabs:
  * Screener (Neuer Einstieg): qualifizierte Aktie + bester Put  [Task Schritt 5]
  * Roller  (Rollen):         historischen Put -> G/V -> 3 Roll-Stufen mit Ampel

Grundlage: "Optionen unschlagbar handeln", Kap. 3 (Rollen), 4+5 (Screener).
Roll-Rechenlogik: src/roll_support_calc.py (buchverifiziert, unit-getestet).

Persistenz: keine (session-only). Kernberechnungen werden bewusst NICHT gecacht;
nur reine DB-Reads nutzen @st.cache_data (Muster spreads_backtesting.py).
"""
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date

import pandas as pd
import streamlit as st

from config import PATH_DATABASE_QUERY_FOLDER, RISK_FREE_RATE
from src.database import select_into_dataframe
from src.streamlit_helpers import render_date_filter
from src.page_display_dataframe import page_display_dataframe
from src.ui_utils import filter_by_expiration_type
from src.utils.option_utils import get_expiration_type
from src.black_scholes import PutValue
from src.roll_support_calc import (position_status, roll_candidate, roll_candidate_explained,
                                    roll_trigger_score, time_value_percentage)
from src.put_screener import score_candidates, score_breakdown, put_metrics, DEFAULT_PE_MAX

logger = logging.getLogger(os.path.basename(__file__))


# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------
def _parse_date(value):
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


@st.cache_data(ttl=300)
def _load_symbols():
    """Symbol-Werthilfe aus der aktuellen Kette (OptionDataMerged) — schlank & schnell,
    wie symbolpage/watchlist. Reiner DB-Read -> darf cachen."""
    df = select_into_dataframe(
        query='SELECT DISTINCT symbol FROM "OptionDataMerged" ORDER BY symbol ASC',
    )
    if df is None or df.empty:
        return []
    return df["symbol"].dropna().astype(str).tolist()


@st.cache_data(ttl=300)
def _load_put_history(symbol, entry_date, dte_min, dte_max):
    """Puts eines Symbols am Einstiegsdatum im DTE-Bereich. Reiner DB-Read -> darf cachen."""
    return select_into_dataframe(
        sql_file_path=PATH_DATABASE_QUERY_FOLDER / "roll_put_history.sql",
        params={"symbol": symbol, "entry_date": str(entry_date),
                "dte_min": int(dte_min), "dte_max": int(dte_max)},
    )


@st.cache_data(ttl=300)
def _load_roll_candidates(symbol, K, dte_min, dte_max, min_oi, min_vol, delta_min, delta_max):
    """Aktuelle Put-Kette als Roll-Kandidaten. Reiner DB-Read -> darf cachen."""
    return select_into_dataframe(
        sql_file_path=PATH_DATABASE_QUERY_FOLDER / "roll_candidates.sql",
        params={
            "symbol": symbol,
            "K": float(K),
            "dte_min": int(dte_min),
            "dte_max": int(dte_max),
            "min_oi": int(min_oi),
            "min_vol": int(min_vol),
            "delta_min": float(delta_min),
            "delta_max": float(delta_max),
        },
    )


# NICHT gecacht: immer frisch (User-Wunsch), aber kein externer Call.
def _current_put_price(option_osi, symbol):
    """Heutiger Wert des bestehenden Puts = letzter verfügbarer day_close aus der DB.

    Kein Live-YahooQuery (User-Wunsch). Nimmt den jüngsten day_close bis heute.
    Rückgabe: (preis_je_aktie, quelle_str) oder (None, grund).
    """
    sql = """
        SELECT a.day_close AS premium_option_price, a.date
        FROM (
            SELECT date, option_osi, symbol, day_close FROM "OptionDataMassiveHistory"
            WHERE option_osi = :osi AND symbol = :symbol AND date <= CURRENT_DATE
            UNION ALL
            SELECT CURRENT_DATE AS date, option_osi, symbol, day_close FROM "OptionDataMassive"
            WHERE option_osi = :osi AND symbol = :symbol
        ) AS a
        WHERE a.date <= CURRENT_DATE
        ORDER BY a.date DESC
        LIMIT 1
    """
    df = select_into_dataframe(query=sql, params={"osi": option_osi, "symbol": symbol})
    if df is not None and not df.empty:
        d = df.iloc[0]["date"]
        return float(df.iloc[0]["premium_option_price"]), f"DB day_close ({d})"
    return None, "kein Preis in DB"


def _current_stock_price(symbol):
    """Aktueller Aktienkurs: letzter Close aus der Historie (1-Wochen-Fenster). NICHT gecacht."""
    sql = """
        SELECT b.close, b.date
        FROM (
                        SELECT close, date, symbol FROM "StockPricesYahooHistory"
                        WHERE symbol = :symbol
                            AND date <= CURRENT_DATE
                            AND date >= CURRENT_DATE - INTERVAL '1 week'
            UNION ALL
                        SELECT close, CURRENT_DATE AS date, symbol FROM "StockPricesYahoo"
                        WHERE symbol = :symbol
        ) AS b
                WHERE b.date <= CURRENT_DATE
          AND b.date >= CURRENT_DATE - INTERVAL '1 week'
        ORDER BY b.date DESC
        LIMIT 1
    """
    df = select_into_dataframe(query=sql, params={"symbol": symbol})
    if df is not None and not df.empty:
        return float(df.iloc[0]["close"])
    return None


# ---------------------------------------------------------------------------
# Tab 2 — Roller (Kern-Feature)
# ---------------------------------------------------------------------------
def render_roller_tab():
    st.subheader("🔄 Roller — bestehenden Cash-Secured Put rollen")
    st.caption("Wähle deinen historisch eröffneten Put, sieh Gewinn/Verlust und alle 3 Roll-Stufen "
               "(Buch Kap. 3). Ampel: ✅ Basispreis gesenkt · ⚠️ Prämie positiv, GS nicht besser · ❌ Roll kostet drauf.")

    # 1) Symbol (Werthilfe aus aktueller Kette — schnell, wie symbolpage/watchlist) + Kontrakte
    symbols = _load_symbols()
    if not symbols:
        st.error("Keine Symbole in der aktuellen Optionskette gefunden.")
        return

    col_sym, col_n = st.columns([2, 1])
    symbol = col_sym.selectbox("Symbol", symbols, index=None,
                               placeholder="Symbol wählen…", key="roll_symbol")
    n_contracts = col_n.number_input("Kontrakte (n)", min_value=1, value=1, step=1)

    if not symbol:
        st.info("Symbol wählen — erst dann werden Historie und Kurse geladen.")
        return

    entry_date = render_date_filter(
        date_query=f"""select date from (
            select date from "DatesHistory" union select current_date
        ) as sub order by date desc""",
        date_label="Einstiegsdatum (Eröffnung des Puts):",
        date_session_key="roll_entry_date",
        date_list_session_key="roll_date_list",
        date_index=0,
    )
    if not entry_date:
        return

    # 2) DTE-Bereich am Einstiegsdatum + Verfallstyp-Filter + verfügbare Puts
    sc1, sc2 = st.columns([3, 2])
    dte_min, dte_max = sc1.slider(
        "DTE-Bereich am Einstiegsdatum (Tage bis Verfall)",
        min_value=1, max_value=400, value=(30, 60), step=1,
        help="Zeigt alle Puts, deren Restlaufzeit am Einstiegsdatum in diesem Bereich lag.",
    )
    with sc2:
        st.caption("Verfallstyp")
        f1, f2, f3 = st.columns(3)
        show_monthly = f1.checkbox("Monthly", value=True, key="roll_monthly")
        show_weekly = f2.checkbox("Weekly", value=True, key="roll_weekly")
        show_daily = f3.checkbox("Daily", value=False, key="roll_daily")

    hist_df = _load_put_history(symbol, entry_date, dte_min, dte_max)
    if hist_df is None or hist_df.empty:
        st.warning(f"Keine Puts für {symbol} am {entry_date} im DTE-Bereich {dte_min}–{dte_max} gefunden.")
        return

    hist_df = filter_by_expiration_type(hist_df, "expiration_date",
                                        show_monthly, show_weekly, show_daily)
    if hist_df.empty:
        st.warning("Keine Puts für die gewählten Verfallstypen (Monthly/Weekly/Daily).")
        return
    # Nach Verfallsdatum, darin nach Strike (absteigend) ordnen — dann Index zurücksetzen,
    # damit die Zeilenauswahl (hist_df.iloc[rows[0]]) exakt zur angezeigten Reihenfolge passt.
    hist_df = (hist_df
               .sort_values(["expiration_date", "strike_price"], ascending=[True, False])
               .reset_index(drop=True))

    # Schritt A: Verfallsdatum wählen (Dropdown mit sprechendem Label) — schneller Überblick,
    # statt aller Strikes über alle Verfälle in einer langen Liste.
    exp_options = (hist_df[["expiration_date", "days_to_expiration"]]
                   .drop_duplicates()
                   .sort_values("expiration_date"))
    exp_labels = {}
    for _, e in exp_options.iterrows():
        exp = e["expiration_date"]
        dte = int(e["days_to_expiration"])
        typ = get_expiration_type(exp)
        exp_labels[f"{pd.to_datetime(exp).strftime('%d.%m.%Y')} · {dte} DTE · {typ}"] = exp

    st.markdown("**1. Verfallsdatum wählen:**")
    chosen_label = st.selectbox("Verfallsdatum", list(exp_labels.keys()),
                                index=None, placeholder="Verfall wählen…",
                                key="roll_expiry_pick", label_visibility="collapsed")
    if not chosen_label:
        st.info("Verfallsdatum wählen — dann erscheinen die Strikes.")
        return
    chosen_exp = exp_labels[chosen_label]

    # Schritt B: nur die Strikes DIESES Verfalls, aufsteigend, ohne OSI-Ballast.
    exp_df = (hist_df[hist_df["expiration_date"] == chosen_exp]
              .sort_values("strike_price", ascending=True)
              .reset_index(drop=True))

    st.markdown("**2. Deinen Strike anklicken:**")
    
    # Initialisiere Session-State für Strike-Auswahl
    if "roll_strike_selected_idx" not in st.session_state:
        st.session_state.roll_strike_selected_idx = None
    
    # Kachel-Grid: 4 Kacheln pro Zeile
    cols_per_row = 4
    num_strikes = len(exp_df)
    num_rows = (num_strikes + cols_per_row - 1) // cols_per_row
    
    selected_idx = None
    for row_idx in range(num_rows):
        cols = st.columns(cols_per_row, gap="small")
        for col_idx, col in enumerate(cols):
            strike_idx = row_idx * cols_per_row + col_idx
            if strike_idx >= num_strikes:
                break
            
            strike_row = exp_df.iloc[strike_idx]
            strike = float(strike_row["strike_price"])
            premium = float(strike_row["premium_option_price"])
            dte = int(strike_row["days_to_expiration"])
            
            # Prüfe ob diese Kachel ausgewählt ist
            is_selected = strike_idx == st.session_state.roll_strike_selected_idx
            
            with col:
                # Conditional Styling für ausgewählte Kachel
                if is_selected:
                    # Grüne Hervorhebung für ausgewählte Kachel
                    st.markdown(f"""
                    <div style="
                        background: linear-gradient(135deg, #00AA00 0%, #00DD00 100%);
                        border: 3px solid #00FF00;
                        border-radius: 10px;
                        padding: 15px;
                        text-align: center;
                        box-shadow: 0 0 10px rgba(0, 255, 0, 0.5);
                    ">
                        <div style="font-size: 20px; font-weight: bold; color: white;">
                            ${strike:.2f}
                        </div>
                        <div style="font-size: 12px; color: #e0e0e0; margin-top: 8px;">
                            Prämie: ${premium:.2f}
                        </div>
                        <div style="font-size: 12px; color: #e0e0e0;">
                            DTE: {dte}d
                        </div>
                        <div style="font-size: 11px; color: #ffff99; margin-top: 5px; font-weight: bold;">
                            ✓ AUSGEWÄHLT
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    # Normale graue Kachel (clickbar)
                    if st.button(
                        f"${strike:.2f}\n\n"
                        f"${premium:.2f}\n"
                        f"{dte}d",
                        key=f"roll_strike_{strike_idx}",
                        use_container_width=True,
                    ):
                        st.session_state.roll_strike_selected_idx = strike_idx
                        selected_idx = strike_idx
                        st.rerun()
    
    # Wenn bereits eine Auswahl existiert, nutze sie
    if selected_idx is None and st.session_state.roll_strike_selected_idx is not None:
        selected_idx = st.session_state.roll_strike_selected_idx
    
    if selected_idx is None:
        st.info("👆 Klicke eine Strike-Kachel an.")
        return
    
    put = exp_df.iloc[selected_idx]

    K = float(put["strike_price"])
    option_osi = put["option_osi"]
    expiration_date = put["expiration_date"]

    # 3) Eröffnungsprämie (Vorschlag + Override) — Muster spreads_backtesting.py
    p_open_suggest = float(put["premium_option_price"])  # $ je Aktie
    st.markdown("### 🛠️ Echte Ausführungskurse (Optional)")
    override = st.checkbox("Tatsächlichen Eröffnungs-Fill manuell eintragen", value=False,
                           help="Ersetzt den historischen day_close durch deinen realen Verkaufspreis.")
    if override:
        p_open_suggest = st.number_input("Eröffnungsprämie je Aktie ($)", min_value=0.0,
                                         value=p_open_suggest, step=0.01, format="%.2f")
    P_eroeffnung = p_open_suggest * 100.0  # absolut $/Kontrakt für die Rechenlogik

    # 4) Heutiger Wert desselben Puts + aktueller Aktienkurs (immer frisch)
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_price = ex.submit(_current_put_price, option_osi, symbol)
        f_stock = ex.submit(_current_stock_price, symbol)
        p_today_share, price_src = f_price.result()
        S = f_stock.result()

    if p_today_share is None:
        st.error("Aktueller Put-Preis nicht ermittelbar (weder Live noch DB).")
        return
    if S is None:
        st.error("Aktueller Aktienkurs nicht ermittelbar.")
        return
    P_heute = p_today_share * 100.0

    # 5) Block "Aktuelle Position"
    st.divider()
    st.markdown("### 📊 Aktuelle Position")
    pos = position_status(K=K, S=S, P_eroeffnung=P_eroeffnung, P_heute=P_heute, n=int(n_contracts))
    dte_rest = (_parse_date(expiration_date) - date.today()).days

    m = st.columns(4)
    m[0].metric("Aktienkurs S", f"${S:.2f}")
    m[1].metric("Strike K", f"${K:.2f}")
    m[2].metric("Put heute", f"${p_today_share:.2f}", help=f"Quelle: {price_src}")
    m[3].metric("DTE (Rest)", f"{dte_rest} T")
    m2 = st.columns(4)
    m2[0].metric("G/V %", f"{pos['pnl_pct']:+.1f}%")
    m2[1].metric("G/V absolut", f"${pos['pnl_abs']:+.2f}")
    m2[2].metric("Innerer Wert", f"${pos['inner_value']:.2f}")
    m2[3].metric("Restzeitwert", f"${pos['time_value']:.2f}")
    st.caption(f"Alte Gewinnschwelle: **${pos['breakeven_old']:.2f}** (= K − Eröffnungsprämie).")

    # 5a) LUDWIG-SCHWELLEN: Oben definieren, damit sie für Roll-Logik verfügbar sind
    st.divider()
    st.markdown("### ⚙️ Deine Ludwig-Schwellen konfigurieren")
    
    with st.expander("📋 Schwellen-Konfiguration", expanded=False):
        c1, c2, c3 = st.columns(3)
        tv_threshold = c1.slider(
            "TV%-Schwelle zum Rollen",
            min_value=5,
            max_value=50,
            value=15,
            step=1,
            key="roll_tv_threshold",
            help="Ludwig-Default: 15%. Bei TV% ≤ dieser Schwelle: Roll empfohlen.\n"
                 "Aggressive Trader: 10% | Conservative: 20–25%",
        )
        roll_score_threshold = c2.slider(
            "Roll-Score Trigger",
            min_value=0.5,
            max_value=1.0,
            value=0.7,
            step=0.05,
            key="roll_score_threshold",
            help="Score ≥ dieser Wert: Roll empfohlen (70% = Ludwig-Default)",
        )
        c3.metric("Deine TV%-Schwelle", f"{tv_threshold}%", help="Wird für alle Roll-Empfehlungen genutzt")

    # 5b) Eric Ludwig Roll-Trigger-Score (Zeitwert + DTE-Fenster)
    st.divider()
    
    im_verlust = P_heute > P_eroeffnung
    
    if im_verlust:
        # ❌ IM VERLUST: Roll-Logik ist relevant
        st.markdown("### 🎯 Eric Ludwig Roll-Trigger-Score (VERLUST-SZENARIO)")
        st.error("🔴 **Position im Verlust** — Rollen ist relevant (Basispreis senken nach Buch-Regel).")
        
        with st.expander("❓ Wie funktioniert dieser Score?", expanded=False):
            st.markdown("""
            **Eric Ludwigs Roll-Logik basiert auf 2 Faktoren:**
            
            1. **Restzeitwert-Prozentsatz (70% Gewicht):**
               - Zeigt: Wie viel deiner ursprünglichen Prämie ist noch übrig?
               - **Formel:** `(Put heute / Eröffnung) × 100`
               - **Ludwigs Regel (im Verlust!):**
                 - **≤ 10 %** → 🟢 **JETZT ROLLEN** (optimale Zeit)
                 - **≤ 15 %** → 🟡 **Roll sinnvoll** (gute Zeit)
                 - **> 15 %** → ⏳ **Noch warten** (zu teuer zum Rückkauf)
            
            2. **DTE-Fenster (30% Gewicht):**
               - Optimales Roll-Zeitfenster nach Theta-Gamma-Balance:
               - **7–14 Tage** → ✅ **Optimal** (Theta maximal, Gamma moderat)
               - **≥ 14 Tage** → ⚠️ **Noch zu früh** (Theta-Verfall zu langsam)
               - **< 3 Tage** → 🔴 **Zu spät** (Gamma-Explosion)
            
            **Kombinierter Score = 70% × TV-Score + 30% × DTE-Score**
            - **≥ 70%** → 🚀 **ROLL TRIGGERN** (TV ≤ 15% UND gutes DTE-Fenster)
            - **< 70%** → ⏳ **Noch warten** (TV noch zu hoch oder falsches DTE)
            """)
        
        trigger = roll_trigger_score(P_heute=P_heute, P_eroeffnung=P_eroeffnung, dte=dte_rest)
        tv_pct = time_value_percentage(P_heute, P_eroeffnung)
        
        t1, t2, t3, t4 = st.columns(4)
        t1.metric(
            "Restzeitwert %",
            f"{tv_pct:.1f}%",
            help="Aktueller Put-Preis als % der Eröffnungsprämie.\nLudwig-Regel (Verlust): < 10% = JETZT ROLLEN | < 15% = Roll sinnvoll",
            delta=f"Trigger bei ≤ 10–15%" if tv_pct <= 15 else None,
        )
        t2.metric("DTE Restlaufzeit", f"{dte_rest}d", help=trigger["dte_label"])
        t3.metric("Roll-Score", f"{trigger['score']:.0%}", help="70% Zeitwert + 30% DTE-Fenster")
        
        # Ampel basierend auf Trigger
        if trigger['trigger']:
            t4.metric("⚠️ Empfehlung", "🚀 ROLLEN", help=trigger['empfehlung'])
            st.success(f"**{trigger['tv_label']}** · {trigger['dte_label']}")
        else:
            t4.metric("Status", "Warten", help=trigger['empfehlung'])
            st.info(trigger['empfehlung'])
    
    else:
        # ✅ IM GEWINN: Nicht rollen, sondern schließen!
        st.markdown("### 🎯 Handlungs-Empfehlung (GEWINN-SZENARIO)")
        st.success("🟢 **Position im Gewinn** — SCHLIESSE den Trade statt zu rollen!")
        
        with st.expander("❓ Warum nicht rollen?", expanded=False):
            st.markdown(f"""
            **Du bist im Gewinn (+{pos['pnl_pct']:.1f}%)** — Die beste Aktion ist:
            
            ✅ **HANDEL SCHLIESSEN:**
            1. Rückkaufe den Put heute
            2. Realisiere deinen Gewinn: **${pos['pnl_abs']:+.2f}**
            3. Freie Kapital für neuen Trade
            
            **Warum ist das besser als rollen?**
            - ❌ Rollen = höhere Kommissionen, mehr Komplexität
            - ✅ Schließen = klare Gewinne, schneller zur nächsten Opportunity
            - ✅ Weniger Kapital gebunden
            - ✅ Bessere ROI durch häufigere Zyklen
            
            **Falls du noch rollen möchtest:** (selten sinnvoll)
            - Nur wenn noch lange bis Verfall (z.B. > 21 DTE)
            - Und du willst noch mehr Prämie verdienen
            - Dann nutze die Roll-Kandidaten unten (Stufe 1–3)
            """)
        
        # Zeige trotzdem optional die Roll-Kandidaten an (falls User will)
        with st.expander("📊 Optional: Roll-Kandidaten (falls du dennoch rollen willst)", expanded=False):
            trigger = roll_trigger_score(P_heute=P_heute, P_eroeffnung=P_eroeffnung, dte=dte_rest)
            tv_pct = time_value_percentage(P_heute, P_eroeffnung)
            
            t1, t2, t3, t4 = st.columns(4)
            t1.metric("Restzeitwert %", f"{tv_pct:.1f}%", help="Für Gewinn-Rollen: Egal, da du ohnehin gewinnen wirst")
            t2.metric("DTE Restlaufzeit", f"{dte_rest}d", help=trigger["dte_label"])
            t3.metric("Roll-Score", f"{trigger['score']:.0%}", help="Nur informatisch")
            t4.metric("Status", "Optional")
    
    # 5c) Detaillierte Erklärung der aktuellen Kennzahlen
    with st.expander("📐 Berechnung der Positionen-Kennzahlen", expanded=False):
        st.markdown(f"""
        **Innerer Wert** (Intrinsic Value)
        - Formel: `max(0, Strike − Aktienkurs) × 100`
        - = `max(0, ${K:.2f} − ${S:.2f}) × 100`
        - = `${pos['inner_value']:.2f}`
        - **Bedeutung:** Gewinn, wenn Option sofort ausgeübt würde (bei ITM, sonst 0)
        
        **Restzeitwert** (Time Value)
        - Formel: `Put-Preis heute − Innerer Wert` (min. 0)
        - = `${p_today_share*100:.2f} − ${pos['inner_value']:.2f}`
        - = `${pos['time_value']:.2f}`
        - **Bedeutung:** Überschuss durch Zeitwertverfall (Theta); sinkt täglich
        
        **Zeitwert-Prozentsatz**
        - Formel: `(Put heute / Eröffnung) × 100`
        - = `(${p_today_share:.2f} / ${P_eroeffnung/100:.2f}) × 100`
        - = `{tv_pct:.1f}%`
        - **Bedeutung:** Wie viel Prämie hast du noch zurückzuzahlen? (Ludwigs KPI!)
        """)
    
    # 6) Roll-Kandidaten: alle 3 Stufen gleichzeitig
    st.divider()
    st.markdown("### 🎯 Roll-Kandidaten (alle 3 Stufen)")
    
    if not im_verlust:
        st.info("💡 **Erinnerung:** Du bist im Gewinn! Die Roll-Kandidaten unten sind optional. "
                "Empfehlung: Einfach schließen und Gewinn realisieren.")
    
    with st.expander("❓ Was sind Roll-Stufen?", expanded=False):
        st.markdown("""
        **Buch-Konzept (Kap. 3): 3 verbindliche Stufen zum Rollen**
        
        🟢 **Stufe 1 — Niedrigerer Basispreis, gleiche Kontrakte**
        - Neuer Strike < alter Strike
        - Kontrakte: 1 bleibt 1
        - **Ziel:** Gewinnschwelle senken, Kapital sparen
        
        🟡 **Stufe 2 — Gleicher Basispreis, gleiche Kontrakte**
        - Neuer Strike = alter Strike
        - Kontrakte: 1 bleibt 1
        - **Ziel:** Laufzeit verlängern, Prämie aufladen
        
        🔴 **Stufe 3 — Niedrigerer Basispreis, Kontrakte verdoppelt**
        - Neuer Strike < alter Strike
        - Kontrakte: 1 wird 2
        - **Ziel:** Aggressive Gewinnschwellensenkung, höheres Kapital
        
        **Oberstes Ziel:** Immer die Gewinnschwelle (Breakeven) senken! 📉
        """)
    
    with st.expander("Kandidaten-Filter", expanded=True):
        st.subheader("Liquiditäts-Filter")
        
        rf1, rf2, rf3, rf4 = st.columns(4)
        roll_dte_min, roll_dte_max = rf1.slider(
            "DTE (Roll-Kandidaten)",
            min_value=7,
            max_value=120,
            value=(30, 45),
            step=1,
            key="roll_candidates_dte",
            help="Filter: Neue Puts müssen in diesem DTE-Fenster liegen.",
        )
        roll_min_oi = rf2.number_input(
            "Min OI",
            min_value=0,
            value=100,
            step=50,
            key="roll_candidates_min_oi",
            help="Liquidität: OI = wie viele Kontrakte sind offen? Höher = liquider.",
        )
        roll_min_vol = rf3.number_input(
            "Min Vol",
            min_value=0,
            value=100,
            step=10,
            key="roll_candidates_min_vol",
            help="Volumen: Tagesumsatz in Kontrakten. Höher = leichter tradebar.",
        )
        roll_delta_min, roll_delta_max = rf4.slider(
            "Delta-Bereich (Put)",
            min_value=-1.0,
            max_value=0.0,
            value=(-0.35, -0.10),
            step=0.01,
            key="roll_candidates_delta",
            help="Typischer CSP-Bereich: etwa -0.35 bis -0.10.",
        )

    cand = _load_roll_candidates(
        symbol,
        K,
        roll_dte_min,
        roll_dte_max,
        roll_min_oi,
        roll_min_vol,
        roll_delta_min,
        roll_delta_max,
    )
    if cand is None or cand.empty:
        st.warning(
            "Keine Roll-Kandidaten gefunden. "
            f"Filter: DTE {roll_dte_min}–{roll_dte_max}, OI ≥ {roll_min_oi}, "
            f"Vol ≥ {roll_min_vol}, Delta {roll_delta_min:.2f} bis {roll_delta_max:.2f}."
        )
        _render_endgame_hint()
        return

    cand = cand.copy()
    cand["premium_option_price"] = pd.to_numeric(cand["premium_option_price"], errors="coerce")
    cand["strike_price"] = pd.to_numeric(cand["strike_price"], errors="coerce")

    any_green = False
    breakeven_old = pos["breakeven_old"]

    # Stufe 1: niedrigerer Strike (< K), n Kontrakte
    st1 = cand[cand["strike_price"] < K]
    any_green |= _render_stufe(1, st1, K, P_eroeffnung, P_heute, int(n_contracts), breakeven_old,
                               "Stufe 1 — niedrigerer Basispreis, gleiche Kontrakte")

    # Stufe 2: gleicher Strike (= K), n Kontrakte
    st2 = cand[cand["strike_price"] == K]
    any_green |= _render_stufe(2, st2, K, P_eroeffnung, P_heute, int(n_contracts), breakeven_old,
                               "Stufe 2 — gleicher Basispreis, gleiche Kontrakte")

    # Stufe 3: niedrigerer Strike (< K), 2n Kontrakte
    st3 = cand[cand["strike_price"] < K]
    any_green |= _render_stufe(3, st3, K, P_eroeffnung, P_heute, 2 * int(n_contracts), breakeven_old,
                               "Stufe 3 — niedrigerer Basispreis, Kontrakte verdoppelt")

    # 7) Endspiel-Hinweis wenn keine ✅
    if not any_green:
        _render_endgame_hint()


def _render_stufe(stufe, df, K, P_eroeffnung, P_heute, n, breakeven_old, title):
    """Rendert eine Stufen-Tabelle mit Klick-Herleitung. True wenn mind. ein ✅ existiert."""
    st.markdown(f"#### {title}")
    
    # Spalten-Erklärung (Expander, pro Stufe einmal)
    with st.expander("❓ Spalten-Erklärung", expanded=False):
        st.markdown("""
        | Spalte | Bedeutung |
        |--------|-----------|
        | **Ampel** | ✅ = GS sinkt + netto Credit | ⚠️ = netto Credit, aber GS nicht besser | ❌ = kostet drauf |
        | **Neuer Strike** | Der neue Basispreis (neuer Put zum Verkaufen) |
        | **Expiry** | Verfallsdatum des neuen Puts |
        | **DTE** | Days to Expiration (Restlaufzeit bis Verfall) |
        | **Prämie neu** | Was du für den neuen Put erhältst (je Aktie, $) |
        | **Delta** | Wahrscheinlichkeit, dass Put ITM verfällt. -0.30 = 30% ITM-Chance |
        | **Netto absolut** | Eröffnung + (n × Neu) − Rückkauf = dein Gesamtkredit ($) |
        | **Neue GS** | Neue Gewinnschwelle nach dem Roll (je Aktie, $) |
        | **Alte GS** | Deine ursprüngliche Gewinnschwelle (zum Vergleich) |
        | **Kapital nötig** | Wie viel Cash-Reserve brauchst du? (K2 × n × 100) |
        | **OI / Vol** | Open Interest / Tagesvolumen = Liquidität |
        | **TV% nach Roll** | Zeitwert des neuen Puts als % der urspr. Prämie |
        | **DTE-Score** | Wie gut ist das DTE-Fenster für Roll? (7–14d optimal) |
        """)
    
    if df is None or df.empty:
        st.caption("Keine passenden Strikes in dieser Stufe.")
        return False

    # Nach Verfallsdatum, darin nach Strike (absteigend) ordnen. reset_index hält die
    # calc_by_idx-Zuordnung (unten) synchron mit der angezeigten Reihenfolge.
    df = df.sort_values(["expiration_date", "strike_price"],
                        ascending=[True, False]).reset_index(drop=True)

    rows, calc_by_idx = [], {}
    for i, (_, o) in enumerate(df.iterrows()):
        K2 = float(o["strike_price"])
        P_neu = float(o["premium_option_price"]) * 100.0  # $/Kontrakt
        r = roll_candidate(stufe=stufe, K=K, K2=K2, P_eroeffnung=P_eroeffnung,
                           P_heute=P_heute, P_neu=P_neu, n=n)
        
        # Eric Ludwig Roll-Trigger-Score für DIESEN Kandidaten
        dte_new = int(o["days_to_expiration"])
        trigger_new = roll_trigger_score(P_heute=P_neu, P_eroeffnung=P_eroeffnung, dte=dte_new)
        tv_pct_new = time_value_percentage(P_neu, P_eroeffnung)
        
        calc_by_idx[i] = dict(K2=K2, P_neu=P_neu, dte_new=dte_new, trigger_new=trigger_new)
        rows.append({
            "Ampel": r["ampel"],
            "Neuer Strike": K2,
            "Expiry": o["expiration_date"],
            "DTE": int(o["days_to_expiration"]),
            "Prämie neu ($)": float(o["premium_option_price"]),
            "Delta": round(float(o["greeks_delta"]), 3) if pd.notna(o["greeks_delta"]) else None,
            "Netto absolut ($)": round(r["netto_abs"], 2),
            "Neue GS": round(r["breakeven_new"], 2),
            "Alte GS": round(breakeven_old, 2),
            "Kapital nötig ($)": round(r["kapital_noetig"], 2),
            "OI": int(o["open_interest"]),
            "Vol": int(o["day_volume"]),
            "TV% nach Roll": f"{tv_pct_new:.0f}%",
            "DTE-Score": f"{trigger_new['dte_score']:.0%}",
        })
    out = pd.DataFrame(rows)
    
    # Sortierung: erst Ampel (✅ zuerst), dann nach Roll-Quality (TV% niedrig ist besser)
    # Das hilft, die besten Kandidaten oben zu finden
    ampel_order = {"✅": 0, "⚠️": 1, "❌": 2}
    out["ampel_sort"] = out["Ampel"].map(ampel_order)
    out["tv_sort"] = out["TV% nach Roll"].str.rstrip("%").astype(int)
    out = out.sort_values(["ampel_sort", "tv_sort"], ascending=[True, True]).drop(
        columns=["ampel_sort", "tv_sort"]
    ).reset_index(drop=True)
    
    event = st.dataframe(out, use_container_width=True, hide_index=True,
                         on_select="rerun", selection_mode="single-row",
                         key=f"stufe_{stufe}")
    sel = event.selection.rows if hasattr(event, "selection") else []
    if sel:
        # row_number bezieht sich auf die sortierte Tabelle, nicht auf original df/calc_by_idx
        # Daher müssen wir neu mappen
        sorted_indices = (
            pd.DataFrame(rows)
            .assign(idx=range(len(rows)))
            .assign(ampel_sort=pd.DataFrame(rows)["Ampel"].map(ampel_order))
            .assign(tv_sort=pd.DataFrame(rows)["TV% nach Roll"].str.rstrip("%").astype(int))
            .sort_values(["ampel_sort", "tv_sort"], ascending=[True, True])
            .reset_index(drop=True)
            ["idx"]
            .tolist()
        )
        original_idx = sorted_indices[sel[0]] if sel[0] < len(sorted_indices) else 0
        c = calc_by_idx[original_idx]
        exp = roll_candidate_explained(stufe=stufe, K=K, K2=c["K2"],
                                       P_eroeffnung=P_eroeffnung, P_heute=P_heute,
                                       P_neu=c["P_neu"], n=n)
        with st.container(border=True):
            st.markdown(f"**Herleitung — Strike {c['K2']:.2f}** ({exp['ampel']})")
            for s in exp["steps"]:
                st.write(f"- **{s['label']}:** {s['formel']} = **{s['wert']:.2f}**")
            
            # Zusätzliche Eric Ludwig Insights
            st.divider()
            st.markdown("**Eric Ludwig Roll-Qualität (nach Roll):**")
            trigger_info = c["trigger_new"]
            st.write(f"- **Restzeitwert %:** {trigger_info['tv_pct']:.1f}% {trigger_info['tv_label']}")
            st.write(f"- **DTE-Fenster:** {trigger_info['dte']}d → {trigger_info['dte_label']}")
            st.write(f"- **Roll-Score:** {trigger_info['score']:.0%} → {trigger_info['empfehlung']}")
            
            st.caption("🔶 Prämien = day_close (Näherung; echter Bid/Ask im Broker prüfen).")
    return (out["Ampel"] == "✅").any()


def _render_endgame_hint():
    st.info(
        "**Kein sinnvoller Put-Roll gefunden.** Nach Buchkonzept folgt jetzt das **Endspiel**: "
        "Aktien andienen lassen und Covered Calls schreiben (asymmetrische Technik: 1 Call auf 200 Aktien, "
        "Einstiegskurs über CC-Prämien bis zur Gewinnschwelle senken).\n\n"
        "→ Nutze dafür den **ITM Covered Call Scanner** (Seite in der Navigation)."
    )


# ---------------------------------------------------------------------------
# Tab 1 — Screener (Buch Kap. 4+5)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def _load_screener(dte_min, dte_max, min_oi, min_vol, price_min, price_max, min_premium_share, min_market_cap_usd):
    """StockData ⋈ OptionDataMerged, harte Filter in SQL. Reiner DB-Read -> darf cachen."""
    return select_into_dataframe(
        sql_file_path=PATH_DATABASE_QUERY_FOLDER / "put_screener.sql",
        params={"dte_min": int(dte_min), "dte_max": int(dte_max),
                "min_oi": int(min_oi), "min_vol": int(min_vol),
                "price_min": float(price_min), "price_max": float(price_max),
                "min_premium_share": float(min_premium_share),
                "min_market_cap": float(min_market_cap_usd)},
    )


@st.cache_data(ttl=300)
def _load_symbol_puts(symbol, dte_min, dte_max, min_oi, min_vol, min_premium_share):
    """Aktuell verkaufbare Puts eines Symbols. Reiner DB-Read -> darf cachen."""
    return select_into_dataframe(
        sql_file_path=PATH_DATABASE_QUERY_FOLDER / "screener_symbol_puts.sql",
        params={
            "symbol": symbol,
            "dte_min": int(dte_min),
            "dte_max": int(dte_max),
            "min_oi": int(min_oi),
            "min_vol": int(min_vol),
            "min_premium_share": float(min_premium_share),
        },
    )


def render_screener_tab():
    st.subheader("📈 Screener — neuer Cash-Secured-Put-Einstieg")
    st.caption("Qualifizierte Aktien nach Buch-Checkliste (Kap. 4+5) mit dem besten Put am Geld. "
               "Harte Filter: Preis 15–80 $, OI/Vol und Mindestprämie konfigurierbar. "
               "Kriterien mit '(aktuell)' sind Momentaufnahmen, kein Mehrjahres-Trend.")

    with st.expander("🔍 Filter", expanded=True):
        # Reihe 1: Hauptfilter
        c1, c2, c3, c4, c5 = st.columns(5)
        price_min, price_max = c1.slider("Aktienkurs ($)", 1, 500, (15, 80), 1,
                                         help="Buch-Default 15–80 $ (Kapitaleinsatz für 200 Aktien).")
        pe_max = c2.slider("KGV-Obergrenze", 10, 200, int(DEFAULT_PE_MAX), 5,
                           help="Tech-Werte dürfen höher liegen.")
        min_score = c3.slider("Mindest-Score", 0, 9, 5, 1)
        dte_min, dte_max = c4.slider("DTE-Fenster (Tage)", 7, 90, (21, 45), 1)
        min_market_cap_b = c5.slider("Min. Market Cap (Mrd. $)", 0.0, 50.0, 2.0, 0.5,
                                     help="Buch-Default: 2 Mrd. (keine Micro-Caps). 0 = kein Filter.")
        min_market_cap_usd = min_market_cap_b * 1e9 if min_market_cap_b > 0 else 0
        
        # Reihe 2: Liquiditätsfilter
        c6, c7, c8 = st.columns(3)
        min_oi = c6.number_input("Min. Open Interest", min_value=100, value=100, step=50)
        min_vol = c7.number_input("Min. Tagesvolumen", min_value=0, value=20, step=10,
                                  help="Default wie Spreads.")
        min_premium_abs = c8.number_input(
            "Min. Prämie ($/Kontrakt)",
            min_value=0.0,
            value=50.0,
            step=5.0,
            format="%.2f",
            help="50 entspricht 0.50 Prämie je Aktie.",
        )
        min_premium_share = float(min_premium_abs) / 100.0

    # Button setzt ein Flag im Session-State. Sonst wäre st.button nur EINEN Rerun lang
    # True — ein Klick auf eine Ergebniszeile (neuer Rerun) würde die Anzeige sonst
    # abbrechen lassen und das Detail-Panel verschwinden.
    if st.button("🔍 Screener starten", type="primary", key="run_screener"):
        st.session_state["screener_ran"] = True
    if not st.session_state.get("screener_ran"):
        st.info("Filter oben einstellen und 'Screener starten' klicken.")
        return

    with st.spinner("Screene Aktien + Puts …"):
        raw = _load_screener(
            dte_min,
            dte_max,
            min_oi,
            min_vol,
            price_min,
            price_max,
            min_premium_share,
            min_market_cap_usd,
        )

    if raw is None or raw.empty:
        st.warning(
            f"Keine Treffer. Filter lockern (Preis {price_min}–{price_max} $, "
            f"OI ≥ {min_oi}, Vol ≥ {min_vol}, Min-Prämie ≥ ${min_premium_abs:.0f}/Kontrakt)."
        )
        return

    scored = score_candidates(raw, pe_max=pe_max)
    scored = scored[scored["score"] >= min_score]
    if scored.empty:
        st.warning(f"Keine Aktie erreicht Score ≥ {min_score}. Schwelle senken.")
        return

    display_cols = [
        "symbol", "price", "score",
        "put_strike", "put_expiry", "put_dte", "put_premium",
        "premium_pct", "annualized_pct", "breakeven", "capital_required",
        "sector",
    ]
    display_cols = [c for c in display_cols if c in scored.columns]
    st.success(f"{len(scored)} qualifizierte Aktien (Score ≥ {min_score}, max {scored.iloc[0]['score_max']}).")
    event = page_display_dataframe(
        scored[display_cols],
        symbol_column="symbol",
        on_select="rerun",
        selection_mode="single-row",
    )
    sel = event.selection.rows if hasattr(event, "selection") else []
    if not sel:
        st.info("Klicke eine Aktie an, um die Score-Herleitung zu sehen.")
        return

    row = scored.iloc[sel[0]]
    st.divider()
    st.markdown(f"### 🔬 Score-Herleitung — {row['symbol']}  ({int(row['score'])}/{int(row['score_max'])})")

    bd = score_breakdown(row, pe_max=pe_max)
    ann_map = {"aktuell": "🔶 (aktuell)", "Näherung": "🔶 (Näherung)", "day_close": "🔶 (day_close)", "": ""}
    detail = pd.DataFrame([{
        "Kriterium": i["label"],
        "Erreicht": "✅" if i["erreicht"] else "❌",
        "Möglich": i["moeglich"],
        "Ist-Wert": i["ist_wert"],
        "Annahme": ann_map.get(i["annahme"], ""),
    } for i in bd])
    st.dataframe(detail, use_container_width=True, hide_index=True)

    getroffene = sorted({i["annahme"] for i in bd if i["annahme"]})
    if getroffene:
        with st.expander("⚠️ Getroffene Annahmen", expanded=False):
            texte = {
                "aktuell": "**(aktuell):** Momentaufnahme statt Mehrjahres-Trend — Yahoo liefert nur den jüngsten Abschluss, kein 10-Jahres-Verlauf.",
                "Näherung": "**(Näherung):** Ersatzgröße statt echtem Wert (z. B. Support ≈ 52W-Tief + SMA200).",
                "day_close": "**(day_close):** Prämie = Tagesschluss statt echtem Bid/Ask.",
            }
            for a in getroffene:
                st.markdown("- " + texte.get(a, a))

    # Verkaufbare Puts für die gewählte Aktie (DTE 30-45, verstellbar)
    st.divider()
    st.markdown("### Verkaufbare Puts — jetzt")
    pc1, pc2, pc3, pc4 = st.columns(4)
    p_dte_min, p_dte_max = pc1.slider("DTE-Fenster", 7, 90, (30, 45), 1, key="screener_put_dte")
    p_min_oi = pc2.number_input("Min OI (Puts)", min_value=0, value=int(min_oi), step=50,
                                key="screener_put_min_oi")
    p_min_vol = pc3.number_input("Min Vol (Puts)", min_value=0, value=int(min_vol), step=10,
                                 key="screener_put_min_vol")
    p_min_premium_abs = pc4.number_input(
        "Min Prämie ($/Kontrakt)",
        min_value=0.0,
        value=float(min_premium_abs),
        step=5.0,
        format="%.2f",
        key="screener_put_min_premium_abs",
    )
    puts = _load_symbol_puts(
        row["symbol"],
        p_dte_min,
        p_dte_max,
        p_min_oi,
        p_min_vol,
        float(p_min_premium_abs) / 100.0,
    )
    if puts is None or puts.empty:
        st.info(
            f"Keine Puts für {row['symbol']} im DTE-Fenster {p_dte_min}–{p_dte_max} "
            f"mit OI ≥ {p_min_oi}, Vol ≥ {p_min_vol}, Min-Prämie ≥ ${p_min_premium_abs:.0f}/Kontrakt."
        )
    else:
        def _num(v):
            return float(v) if v is not None and pd.notna(v) else None

        def _bs_put(S, K, iv, dte):
            """Black-Scholes-Put-Preis; None wenn Eingaben unbrauchbar."""
            S, K, iv = _num(S), _num(K), _num(iv)
            dte = int(dte) if dte is not None and pd.notna(dte) else 0
            if not S or not K or not iv or iv <= 0 or dte <= 0:
                return None
            try:
                return round(PutValue(S, K, iv, dte, RISK_FREE_RATE), 2)
            except (ValueError, ZeroDivisionError):
                return None

        put_rows = []
        for _, o in puts.iterrows():
            m = put_metrics(o["strike_price"], o["premium_option_price"], o["days_to_expiration"])
            iv = _num(o["implied_volatility"])
            bs = _bs_put(o["live_stock_price"], o["strike_price"], iv, o["days_to_expiration"])
            delta, theta = _num(o["greeks_delta"]), _num(o["greeks_theta"])
            exp_move = _num(o.get("expected_move"))
            put_rows.append({
                "Expiry": o["expiration_date"],
                "Strike": round(float(o["strike_price"]), 2),
                "DTE": int(o["days_to_expiration"]),
                "Prämie ($)": round(float(o["premium_option_price"]), 2),
                "BS-Preis ($)": bs,
                "Rendite %": round(m["premium_pct"], 2),
                "Annualisiert %": round(m["annualized_pct"], 1),
                "Gewinnschwelle": round(m["breakeven"], 2),
                "Kapital ($)": round(m["capital_required"], 0),
                "Delta": round(delta, 3) if delta is not None else None,
                "Theta": round(theta, 4) if theta is not None else None,
                "IV %": round(iv * 100, 1) if iv is not None else None,
                "Exp. Move": round(exp_move, 2) if exp_move is not None else None,
                "OI": int(o["open_interest"]),
                "Vol": int(o["day_volume"]),
            })
        put_df = (pd.DataFrame(put_rows)
                  .sort_values(["Expiry", "Strike"], ascending=[True, True])
                  .reset_index(drop=True))

        # BS-Vergleich einfärben: grün wenn Markt-Prämie > BS-Preis (überteuert -> gut für Verkäufer).
        def _highlight_bs(r):
            styles = [""] * len(r)
            bs_v, pr_v = r.get("BS-Preis ($)"), r.get("Prämie ($)")
            if bs_v is not None and pd.notna(bs_v) and pr_v is not None and pd.notna(pr_v):
                col = "#90EE90" if float(pr_v) > float(bs_v) else "#FFB6B6"
                idx = put_df.columns.get_loc("BS-Preis ($)")
                styles[idx] = f"background-color: {col}; color: #000000; font-weight: bold"
            return styles

        put_event = st.dataframe(put_df.style.apply(_highlight_bs, axis=1),
                                 use_container_width=True, hide_index=True,
                                 on_select="rerun", selection_mode="single-row",
                                 key="screener_put_pick")
        st.caption("🔶 Prämie = day_close (Näherung; echter Bid/Ask im Broker prüfen). "
                   "BS-Preis grün = Markt teurer als Black-Scholes (gut für Verkäufer). "
                   "Sortiert nach Verfallsdatum, darin nach Strike (aufsteigend). "
                   "**Klicke einen Put für Details.**")

        psel = put_event.selection.rows if hasattr(put_event, "selection") else []
        if psel:
            p = put_df.iloc[psel[0]]
            st.markdown(f"#### 🔍 Put-Detail — {row['symbol']} {p['Strike']:.2f} · {p['Expiry']}")
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Prämie", f"${p['Prämie ($)']:.2f}")
            bs_txt = f"${p['BS-Preis ($)']:.2f}" if pd.notna(p["BS-Preis ($)"]) else "—"
            fair = ""
            if pd.notna(p["BS-Preis ($)"]):
                fair = "über BS (gut für Verkäufer)" if p["Prämie ($)"] > p["BS-Preis ($)"] else "unter BS"
            d1.metric("BS-Preis", bs_txt, help=fair)
            d2.metric("Rendite", f"{p['Rendite %']:.2f}%")
            d2.metric("Annualisiert", f"{p['Annualisiert %']:.1f}%")
            d3.metric("Gewinnschwelle", f"${p['Gewinnschwelle']:.2f}")
            d3.metric("Kapital (CSP)", f"${p['Kapital ($)']:.0f}")
            d4.metric("DTE", f"{int(p['DTE'])} T")
            d4.metric("Delta", f"{p['Delta']:.3f}" if pd.notna(p["Delta"]) else "—")
            g1, g2, g3, g4 = st.columns(4)
            g1.metric("Theta", f"{p['Theta']:.4f}" if pd.notna(p["Theta"]) else "—")
            g2.metric("IV", f"{p['IV %']:.1f}%" if pd.notna(p["IV %"]) else "—")
            g3.metric("Exp. Move", f"±{p['Exp. Move']:.2f}" if pd.notna(p["Exp. Move"]) else "—")
            g4.metric("OI / Vol", f"{int(p['OI'])} / {int(p['Vol'])}")
            if fair:
                st.caption(f"Bewertung: Markt-Prämie **{fair}**.")


# ---------------------------------------------------------------------------
# Seite
# ---------------------------------------------------------------------------
tab_screener, tab_roller = st.tabs(["📈 Screener (Neuer Einstieg)", "🔄 Roller (Rollen)"])
with tab_screener:
    render_screener_tab()
with tab_roller:
    render_roller_tab()
