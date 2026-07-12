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
from src.roll_support_calc import position_status, roll_candidate, roll_candidate_explained
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
    strike_table = exp_df[["strike_price", "premium_option_price", "days_to_expiration",
                           "stock_close"]].rename(columns={
        "strike_price": "Strike",
        "premium_option_price": "Prämie ($)",
        "days_to_expiration": "DTE",
        "stock_close": "Aktienkurs",
    })
    event = st.dataframe(
        strike_table,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="roll_put_pick",
    )
    rows = event.selection.rows if hasattr(event, "selection") else []
    if not rows:
        st.info("Klicke oben die Zeile deines Strikes an.")
        return
    put = exp_df.iloc[rows[0]]

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
def _load_screener(dte_min, dte_max, min_oi, min_vol, price_min, price_max):
    """StockData ⋈ OptionDataMerged, harte Filter in SQL. Reiner DB-Read -> darf cachen."""
    return select_into_dataframe(
        sql_file_path=PATH_DATABASE_QUERY_FOLDER / "put_screener.sql",
        params={"dte_min": int(dte_min), "dte_max": int(dte_max),
                "min_oi": int(min_oi), "min_vol": int(min_vol),
                "price_min": float(price_min), "price_max": float(price_max)},
    )


@st.cache_data(ttl=300)
def _load_symbol_puts(symbol, dte_min, dte_max):
    """Aktuell verkaufbare Puts eines Symbols. Reiner DB-Read -> darf cachen."""
    return select_into_dataframe(
        sql_file_path=PATH_DATABASE_QUERY_FOLDER / "screener_symbol_puts.sql",
        params={"symbol": symbol, "dte_min": int(dte_min), "dte_max": int(dte_max)},
    )


def render_screener_tab():
    st.subheader("📈 Screener — neuer Cash-Secured-Put-Einstieg")
    st.caption("Qualifizierte Aktien nach Buch-Checkliste (Kap. 4+5) mit dem besten Put am Geld. "
               "Harte Filter: Preis 15–80 $, Options-Liquidität OI/Vol ≥ 100. "
               "Kriterien mit '(aktuell)' sind Momentaufnahmen, kein Mehrjahres-Trend.")

    with st.expander("🔍 Filter", expanded=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        price_min, price_max = c1.slider("Aktienkurs ($)", 1, 500, (15, 80), 1,
                                         help="Buch-Default 15–80 $ (Kapitaleinsatz für 200 Aktien).")
        pe_max = c2.slider("KGV-Obergrenze", 10, 200, int(DEFAULT_PE_MAX), 5,
                           help="Tech-Werte dürfen höher liegen.")
        min_score = c3.slider("Mindest-Score", 0, 9, 5, 1)
        dte_min, dte_max = c4.slider("DTE-Fenster (Tage)", 7, 90, (21, 45), 1)
        min_oi = c5.number_input("Min. Open Interest", min_value=100, value=100, step=50)
        min_vol = c5.number_input("Min. Tagesvolumen", min_value=100, value=100, step=50)

    # Button setzt ein Flag im Session-State. Sonst wäre st.button nur EINEN Rerun lang
    # True — ein Klick auf eine Ergebniszeile (neuer Rerun) würde die Anzeige sonst
    # abbrechen lassen und das Detail-Panel verschwinden.
    if st.button("🔍 Screener starten", type="primary", key="run_screener"):
        st.session_state["screener_ran"] = True
    if not st.session_state.get("screener_ran"):
        st.info("Filter oben einstellen und 'Screener starten' klicken.")
        return

    with st.spinner("Screene Aktien + Puts …"):
        raw = _load_screener(dte_min, dte_max, min_oi, min_vol, price_min, price_max)

    if raw is None or raw.empty:
        st.warning(f"Keine Treffer. Filter lockern (Preis {price_min}–{price_max} $, OI/Vol ≥ 100, DTE-Fenster).")
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
    pc1, _pc2 = st.columns([1, 3])
    p_dte_min, p_dte_max = pc1.slider("DTE-Fenster", 7, 90, (30, 45), 1, key="screener_put_dte")
    puts = _load_symbol_puts(row["symbol"], p_dte_min, p_dte_max)
    if puts is None or puts.empty:
        st.info(f"Keine liquiden Puts für {row['symbol']} im DTE-Fenster {p_dte_min}–{p_dte_max}.")
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
