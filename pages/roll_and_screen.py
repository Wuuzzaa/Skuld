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

from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.streamlit_helpers import render_date_filter
from src.page_display_dataframe import page_display_dataframe
from src.roll_support_calc import position_status, roll_candidate, roll_candidate_explained
from src.put_screener import score_candidates, criterion_labels, DEFAULT_PE_MAX

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
    """DISTINCT-Symbolliste für die Selectbox. Reiner DB-Read -> darf cachen."""
    df = select_into_dataframe(
        sql_file_path=PATH_DATABASE_QUERY_FOLDER / "roll_symbols.sql",
        params={},
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
def _load_roll_candidates(symbol, K, dte_min, dte_max):
    """Aktuelle Put-Kette als Roll-Kandidaten. Reiner DB-Read -> darf cachen."""
    return select_into_dataframe(
        sql_file_path=PATH_DATABASE_QUERY_FOLDER / "roll_candidates.sql",
        params={"symbol": symbol, "K": float(K), "dte_min": int(dte_min), "dte_max": int(dte_max)},
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
            WHERE date <> CURRENT_DATE
            UNION ALL
            SELECT CURRENT_DATE AS date, option_osi, symbol, day_close FROM "OptionDataMassive"
        ) AS a
        WHERE a.option_osi = :osi AND a.symbol = :symbol
          AND a.date <= CURRENT_DATE
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
            SELECT * FROM "StockPricesYahooHistory" WHERE date <> CURRENT_DATE
            UNION ALL
            SELECT CURRENT_DATE AS date, * FROM "StockPricesYahoo"
        ) AS b
        WHERE b.symbol = :symbol
          AND b.date <= CURRENT_DATE
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

    # 1) Symbol (Selectbox mit Autocomplete) + Kontrakte
    symbols = _load_symbols()
    if not symbols:
        st.error("Keine Symbole mit historischen Optionsdaten gefunden.")
        return

    col_sym, col_n = st.columns([2, 1])
    symbol = col_sym.selectbox("Symbol", symbols,
                               index=None, placeholder="Symbol wählen…")
    n_contracts = col_n.number_input("Kontrakte (n)", min_value=1, value=1, step=1)

    if not symbol:
        st.info("Bitte ein Symbol wählen.")
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

    # 2) DTE-Bereich am Einstiegsdatum + verfügbare Puts
    dte_min, dte_max = st.slider(
        "DTE-Bereich am Einstiegsdatum (Tage bis Verfall)",
        min_value=1, max_value=400, value=(30, 60), step=1,
        help="Zeigt alle Puts, deren Restlaufzeit am Einstiegsdatum in diesem Bereich lag.",
    )
    hist_df = _load_put_history(symbol, entry_date, dte_min, dte_max)
    if hist_df is None or hist_df.empty:
        st.warning(f"Keine Puts für {symbol} am {entry_date} im DTE-Bereich {dte_min}–{dte_max} gefunden.")
        return

    st.markdown("**Wähle deinen eröffneten Put:**")
    event = page_display_dataframe(
        hist_df[["expiration_date", "strike_price", "premium_option_price",
                 "days_to_expiration", "stock_close", "option_osi"]],
        symbol_column="option_osi",
        on_select="rerun",
        selection_mode="single-row",
    )
    rows = event.selection.rows if hasattr(event, "selection") else []
    if not rows:
        st.info("Klicke oben die Zeile deines Puts an.")
        return
    put = hist_df.iloc[rows[0]]

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

    # 6) Roll-Kandidaten: alle 3 Stufen gleichzeitig
    st.divider()
    im_verlust = P_heute > P_eroeffnung
    if im_verlust:
        st.error("🔴 Position im Verlust — **Rollen sinnvoll** (Basispreis senken nach Buch-Regel).")
    else:
        st.success("🟢 Position im Gewinn — Rollen **optional** (z. B. um Laufzeit zu verlängern).")
    st.markdown("### 🎯 Roll-Kandidaten (alle 3 Stufen)")
    cand = _load_roll_candidates(symbol, K, 30, 90)
    if cand is None or cand.empty:
        st.warning("Keine aktuellen Put-Kandidaten (DTE 30–90, liquide) gefunden.")
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
    if df is None or df.empty:
        st.caption("Keine passenden Strikes in dieser Stufe.")
        return False

    rows, calc_by_idx = [], {}
    for i, (_, o) in enumerate(df.iterrows()):
        K2 = float(o["strike_price"])
        P_neu = float(o["premium_option_price"]) * 100.0  # $/Kontrakt
        r = roll_candidate(stufe=stufe, K=K, K2=K2, P_eroeffnung=P_eroeffnung,
                           P_heute=P_heute, P_neu=P_neu, n=n)
        calc_by_idx[i] = dict(K2=K2, P_neu=P_neu)
        rows.append({
            "Ampel": r["ampel"],
            "Neuer Strike": K2,
            "Expiry": o["expiration_date"],
            "DTE": int(o["days_to_expiration"]),
            "Prämie neu ($)": float(o["premium_option_price"]),
            "Netto absolut ($)": round(r["netto_abs"], 2),
            "Neue GS": round(r["breakeven_new"], 2),
            "Alte GS": round(breakeven_old, 2),
            "Kapital nötig ($)": round(r["kapital_noetig"], 2),
            "OI": int(o["open_interest"]),
            "Vol": int(o["day_volume"]),
        })
    out = pd.DataFrame(rows)
    event = st.dataframe(out, use_container_width=True, hide_index=True,
                         on_select="rerun", selection_mode="single-row",
                         key=f"stufe_{stufe}")
    sel = event.selection.rows if hasattr(event, "selection") else []
    if sel:
        c = calc_by_idx[sel[0]]
        exp = roll_candidate_explained(stufe=stufe, K=K, K2=c["K2"],
                                       P_eroeffnung=P_eroeffnung, P_heute=P_heute,
                                       P_neu=c["P_neu"], n=n)
        with st.container(border=True):
            st.markdown(f"**Herleitung — Strike {c['K2']:.2f}** ({exp['ampel']})")
            for s in exp["steps"]:
                st.write(f"- **{s['label']}:** {s['formel']} = **{s['wert']:.2f}**")
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
def _load_screener(dte_min, dte_max, min_oi, min_vol):
    """StockData ⋈ OptionDataMerged, harte Filter in SQL. Reiner DB-Read -> darf cachen."""
    return select_into_dataframe(
        sql_file_path=PATH_DATABASE_QUERY_FOLDER / "put_screener.sql",
        params={"dte_min": int(dte_min), "dte_max": int(dte_max),
                "min_oi": int(min_oi), "min_vol": int(min_vol)},
    )


def render_screener_tab():
    st.subheader("📈 Screener — neuer Cash-Secured-Put-Einstieg")
    st.caption("Qualifizierte Aktien nach Buch-Checkliste (Kap. 4+5) mit dem besten Put am Geld. "
               "Harte Filter: Preis 15–80 $, Options-Liquidität OI/Vol ≥ 100. "
               "Kriterien mit '(aktuell)' sind Momentaufnahmen, kein Mehrjahres-Trend.")

    with st.sidebar:
        st.markdown("### 📈 Screener-Filter")
        pe_max = st.slider("KGV-Obergrenze", min_value=10, max_value=200,
                           value=int(DEFAULT_PE_MAX), step=5,
                           help="Tech-Werte dürfen höher liegen — Schwelle hier großzügiger stellen.")
        min_score = st.slider("Mindest-Score", min_value=0, max_value=9, value=5, step=1)
        dte_min, dte_max = st.slider("DTE-Fenster (Tage)", min_value=7, max_value=90,
                                     value=(21, 45), step=1)
        min_oi = st.number_input("Min. Open Interest", min_value=100, value=100, step=50)
        min_vol = st.number_input("Min. Tagesvolumen", min_value=100, value=100, step=50)

    if not st.button("🔍 Screener starten", type="primary", key="run_screener"):
        st.info("Filter links einstellen und 'Screener starten' klicken.")
        return

    with st.spinner("Screene Aktien + Puts …"):
        raw = _load_screener(dte_min, dte_max, min_oi, min_vol)

    if raw is None or raw.empty:
        st.warning("Keine Treffer. Filter lockern (Preis 15–80 $, OI/Vol ≥ 100, DTE-Fenster).")
        return

    scored = score_candidates(raw, pe_max=pe_max)
    scored = scored[scored["score"] >= min_score]
    if scored.empty:
        st.warning(f"Keine Aktie erreicht Score ≥ {min_score}. Schwelle senken.")
        return

    labels = criterion_labels()
    display_cols = [
        "symbol", "price", "score",
        "put_strike", "put_expiry", "put_dte", "put_premium",
        "premium_pct", "annualized_pct", "breakeven", "capital_required",
        "sector",
    ]
    display_cols = [c for c in display_cols if c in scored.columns]
    st.success(f"{len(scored)} qualifizierte Aktien (Score ≥ {min_score}, max {scored.iloc[0]['score_max']}).")
    page_display_dataframe(
        scored[display_cols],
        symbol_column="symbol",
        on_select="ignore",
    )

    with st.expander("ℹ️ Score-Details je Kriterium"):
        crit_cols = ["symbol", "score"] + list(labels.keys())
        crit_cols = [c for c in crit_cols if c in scored.columns]
        detail = scored[crit_cols].rename(columns=labels)
        st.dataframe(detail, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Seite
# ---------------------------------------------------------------------------
tab_screener, tab_roller = st.tabs(["📈 Screener (Neuer Einstieg)", "🔄 Roller (Rollen)"])
with tab_screener:
    render_screener_tab()
with tab_roller:
    render_roller_tab()
