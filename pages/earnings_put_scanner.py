"""
Earnings Put Scanner — IV-Crush Strategie
"""

import logging
import os

import pandas as pd
import streamlit as st

from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.logger_config import setup_logging

setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(os.path.basename(__file__))
logger.debug(f"Start Page: {os.path.basename(__file__)}")

# ── Page header ───────────────────────────────────────────────────────────────
st.title("Earnings Put Scanner")
st.caption("Put unter Expected Move verkaufen — nächsten Morgen bei 90% Gewinn zurückkaufen.")

with st.expander("Wie funktioniert die Strategie?"):
    st.markdown("""
**Idee: IV-Crush nach Earnings**

Vor Earnings sind Optionen teuer — der Markt zahlt einen Aufpreis für die Unsicherheit.
Sobald die Zahlen draußen sind, kollabiert diese Unsicherheitsprämie sofort (IV-Crush).
Du profitierst davon, **ohne die Richtung zu kennen**.

1. Put verkaufen mit Strike **unterhalb des Expected Move** (Safe Zone)
2. Nächsten Morgen nach Earnings: Buy-to-Close bei **10% des Prämienpreises** (= 90% Gewinn einstreichen)
3. Falls Zielorder nicht gefüllt: 60 min nach Marktöffnung zum Marktpreis schließen
4. Bei Zuweisung: Covered Call auf die 100 Aktien verkaufen zur Kostenbasis-Rückgewinnung

**Worst case:** Aktie fällt unter deinen Strike → du kaufst 100 Aktien zu Strike-Preis, abzüglich der kassierten Prämie.
""")

# ── Session state ─────────────────────────────────────────────────────────────
for key, default in [
    ("eps_candidates_df", None),
    ("eps_selected_symbol", None),
    ("eps_puts_df", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── Filter controls ───────────────────────────────────────────────────────────
st.subheader("Scanner Filter")

col1, col2, col3, col4, col5 = st.columns([1.5, 1.5, 1.5, 1, 1])

with col1:
    days_ahead = st.selectbox(
        "Earnings binnen",
        options=[3, 5, 7, 10, 14, 21, 30, 45, 60],
        index=2,
        format_func=lambda x: f"{x} Tagen",
        key="eps_days_ahead",
    )
with col2:
    require_dividend = st.selectbox(
        "Dividenden-Filter",
        options=["Alle", "Nur Dividendenzahler"],
        index=0,
        key="eps_div_filter",
    )
with col3:
    max_pe = st.number_input("Max P/E Ratio", min_value=1, max_value=500, value=100, step=5, key="eps_max_pe")
with col4:
    min_iv_rank = st.number_input("Min IV Rank %", min_value=0, max_value=100, value=40, step=5, key="eps_min_iv_rank")
with col5:
    max_iv_rank = st.number_input("Max IV Rank %", min_value=0, max_value=100, value=100, step=5, key="eps_max_iv_rank")

scan_btn = st.button("Kandidaten suchen", type="primary")

# ── Load candidates ───────────────────────────────────────────────────────────
if scan_btn:
    with st.spinner("Suche nach Earnings-Kandidaten..."):
        try:
            sql_path = PATH_DATABASE_QUERY_FOLDER / "earnings_put_scanner.sql"
            raw_df = select_into_dataframe(sql_file_path=sql_path, params={"days_ahead": days_ahead})

            if raw_df.empty:
                st.warning("Keine Kandidaten gefunden. Earnings-Fenster vergrößern.")
                st.session_state["eps_candidates_df"] = None
            else:
                df = raw_df.copy()
                for col in ["trailing_pe", "iv_rank", "iv_percentile", "live_stock_price",
                            "expected_move", "expected_move_pct", "market_cap", "avg_volume"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")

                if require_dividend == "Nur Dividendenzahler":
                    df = df[df["dividend_classification"].notna() & (df["dividend_classification"] != "")]
                if max_pe < 500:
                    df = df[df["trailing_pe"].isna() | (df["trailing_pe"] <= max_pe)]
                df = df[df["iv_rank"].isna() | ((df["iv_rank"] >= min_iv_rank) & (df["iv_rank"] <= max_iv_rank))]

                if df.empty:
                    st.warning("Alle Kandidaten herausgefiltert. Filter lockern.")
                    st.session_state["eps_candidates_df"] = None
                else:
                    df = df.sort_values(["days_to_earnings", "iv_rank"], ascending=[True, False])
                    st.session_state["eps_candidates_df"] = df
                    st.session_state["eps_selected_symbol"] = None
                    st.session_state["eps_puts_df"] = None
                    st.rerun()

        except Exception as e:
            st.error(f"Fehler beim Laden: {e}")
            logger.error(e, exc_info=True)

# ── Candidate table ───────────────────────────────────────────────────────────
if st.session_state["eps_candidates_df"] is not None:
    df = st.session_state["eps_candidates_df"].copy()

    st.divider()

    # Sektor-Filter (client-seitig, aus geladenen Daten)
    available_sectors = sorted(df["company_sector"].dropna().unique().tolist()) if "company_sector" in df.columns else []

    filter_col1, filter_col2 = st.columns([3, 1])
    with filter_col1:
        if available_sectors:
            selected_sectors = st.multiselect(
                "Sektor-Filter",
                options=available_sectors,
                default=[],
                placeholder="Alle Sektoren anzeigen",
                key="eps_sector_filter",
            )
            if selected_sectors:
                df = df[df["company_sector"].isin(selected_sectors)]
    with filter_col2:
        safe_puts_only = st.toggle(
            "✅ Nur mit Safe-Put",
            value=False,
            key="eps_safe_puts_only",
            help="Nur Symbole anzeigen, für die mindestens ein Put unterhalb des Expected Move existiert",
        )
        if safe_puts_only and "has_safe_put" in df.columns:
            df = df[df["has_safe_put"] == True]

    st.subheader(f"Earnings-Kandidaten — {len(df)} gefunden")
    st.caption("Zeile anklicken um verfügbare Puts für das Symbol zu sehen.")

    def _fmt_market_cap(v):
        if pd.isna(v): return "—"
        if v >= 1e12: return f"${v/1e12:.1f}T"
        if v >= 1e9:  return f"${v/1e9:.1f}B"
        return f"${v/1e6:.0f}M"

    def _iv_rank_badge(row):
        iv = row.get("iv_rank", None)
        if pd.isna(iv): return "—"
        if iv >= 60: return f"🟢 {iv:.0f}%"
        if iv >= 40: return f"🟡 {iv:.0f}%"
        return f"⚪ {iv:.0f}%"

    display_df = pd.DataFrame({
        "Symbol":    df["symbol"],
        "Name":      df.get("company_name", pd.Series("—", index=df.index)).fillna("—").astype(str).str.slice(0, 28),
        "Sektor":    df.get("company_sector", pd.Series("—", index=df.index)).fillna("—"),
        "Safe Put":  df.get("has_safe_put", pd.Series(False, index=df.index)).apply(lambda v: "✅" if v else "—"),
        "Earnings":  df["earnings_date"].astype(str),
        "Tage":      df["days_to_earnings"].astype("Int64"),
        "Kurs ($)":  df["live_stock_price"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
        "Exp. Move": df.apply(
            lambda r: f"±{r['expected_move']:.2f} ({r['expected_move_pct']:.1f}%)"
            if pd.notna(r.get("expected_move")) else "—", axis=1),
        "IV Rank":   df.apply(_iv_rank_badge, axis=1),
        "Mkt Cap":   df["market_cap"].apply(_fmt_market_cap),
        "P/E":       df["trailing_pe"].apply(lambda v: f"{v:.1f}" if pd.notna(v) else "—"),
        "Dividende": df["dividend_classification"].fillna("—"),
    })

    event = st.dataframe(
        display_df,
        use_container_width=True,
        height=min(600, 40 + 35 * len(display_df)),
        selection_mode="single-row",
        on_select="rerun",
        key="eps_candidate_table",
    )

    selected_rows = event.selection.rows if hasattr(event, "selection") else []
    if selected_rows:
        selected_idx = selected_rows[0]
        selected_symbol = df.iloc[selected_idx]["symbol"]
        row = df.iloc[selected_idx]

        price    = float(row["live_stock_price"])    if pd.notna(row.get("live_stock_price"))    else None
        exp_move = float(row["expected_move"])       if pd.notna(row.get("expected_move"))       else None
        exp_pct  = float(row["expected_move_pct"])   if pd.notna(row.get("expected_move_pct"))   else None
        iv_rank  = float(row["iv_rank"])             if pd.notna(row.get("iv_rank"))             else None
        hv       = float(row["historical_volatility_30d"]) if pd.notna(row.get("historical_volatility_30d")) else None
        atm_strike     = float(row["atm_strike"])    if pd.notna(row.get("atm_strike"))          else None
        straddle_expiry = str(row.get("straddle_expiry", ""))

        st.divider()
        st.subheader(f"Analyse — {selected_symbol}")

        if price and exp_move:
            safe_threshold = price - exp_move
            upper_range    = price + exp_move

            # Kennzahlen kompakt
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Kurs", f"${price:.2f}")
            m2.metric("Expected Move", f"±${exp_move:.2f}", f"{exp_pct:.1f}%" if exp_pct else None)
            m3.metric("Safe-Strike-Schwelle", f"< ${safe_threshold:.2f}", "Strike muss darunter liegen")
            m4.metric("IV Rank", f"{iv_rank:.0f}%" if iv_rank is not None else "—")

            with st.expander("ℹ️ Wie wird der Expected Move berechnet? Was bedeutet die Prozentzahl?"):
                st.markdown(f"""
**Berechnung — ATM Straddle**

Der Expected Move wird **nicht** aus einer Formel geschätzt, sondern direkt aus dem Marktpreis abgelesen:

```
Expected Move = Preis ATM Call + Preis ATM Put
              = ATM Straddle-Preis
```

Konkret für {selected_symbol}: Strike **${atm_strike:.1f}**, Verfall **{straddle_expiry}**

> Der Markt selbst sagt damit: *"Wir erwarten eine Bewegung von ±${exp_move:.2f}."*
> Das ist die genaueste Methode — keine Schätzung, sondern implizite Marktmeinung.

---

**Was bedeutet die Prozentzahl ({exp_pct:.1f}%)?**

```
{exp_pct:.1f}% = Expected Move / Aktueller Kurs
             = ${exp_move:.2f} / ${price:.2f}
```

Die Aktie wird sich nach Earnings mit **68% Wahrscheinlichkeit** innerhalb dieser Bandbreite bewegen:

| Zone | Kurs |
|---|---|
| Obergrenze | ${upper_range:.2f} (+{exp_pct:.1f}%) |
| Aktuell | ${price:.2f} |
| Untergrenze / Safe-Strike-Schwelle | ${safe_threshold:.2f} (−{exp_pct:.1f}%) |

Puts mit Strike **unter ${safe_threshold:.2f}** liegen außerhalb dieser Zone — das Risiko einer Zuweisung ist statistisch kleiner als 16%.
""")
                if hv is not None and exp_pct is not None:
                    hv_pct = hv * 100
                    if exp_pct > hv_pct:
                        st.info(f"📊 Implizierte Bewegung ({exp_pct:.1f}%) > historische Volatilität ({hv_pct:.1f}%) — Optionen sind überdurchschnittlich teuer. Guter Zeitpunkt zum Verkaufen.")
                    else:
                        st.warning(f"📊 Implizierte Bewegung ({exp_pct:.1f}%) ≈ historische Volatilität ({hv_pct:.1f}%) — Optionen nicht deutlich überbewertet. IV-Crush-Effekt könnte geringer ausfallen.")

        if selected_symbol != st.session_state.get("eps_selected_symbol"):
            st.session_state["eps_selected_symbol"] = selected_symbol
            st.session_state["eps_puts_df"] = None
            st.rerun()

# ── Put candidates for selected symbol ───────────────────────────────────────
if st.session_state.get("eps_selected_symbol"):
    symbol        = st.session_state["eps_selected_symbol"]
    candidates_df = st.session_state["eps_candidates_df"]
    symbol_row    = candidates_df[candidates_df["symbol"] == symbol].iloc[0]

    live_price    = symbol_row.get("live_stock_price")
    expected_move = symbol_row.get("expected_move")
    earnings_date = symbol_row.get("earnings_date")

    safety_threshold = (
        float(live_price) - float(expected_move)
        if pd.notna(live_price) and pd.notna(expected_move) else None
    )

    st.divider()
    st.subheader(f"Put-Kandidaten — {symbol}")

    # Put filter controls
    p_col1, p_col2, p_col3 = st.columns(3)
    with p_col1:
        min_oi = st.number_input("Min Open Interest", min_value=0, value=50, step=25, key="eps_min_oi")
    with p_col2:
        min_premium_pct = st.number_input("Min Prämie % vom Strike", min_value=0.0, max_value=10.0, value=1.0, step=0.1, format="%.1f", key="eps_min_premium_pct")
    with p_col3:
        safe_only = st.checkbox("Nur Safe Zone", value=False, key="eps_safe_only",
                                help="Nur Puts anzeigen deren Strike unterhalb des Expected Move liegt")

    if st.session_state["eps_puts_df"] is None:
        with st.spinner(f"Lade Puts für {symbol}..."):
            try:
                sql_path = PATH_DATABASE_QUERY_FOLDER / "earnings_put_candidates.sql"
                puts_df  = select_into_dataframe(sql_file_path=sql_path, params={"symbol": symbol, "min_oi": min_oi})
                st.session_state["eps_puts_df"] = puts_df
            except Exception as e:
                st.error(f"Fehler: {e}")
                logger.error(e, exc_info=True)

    puts_df = st.session_state.get("eps_puts_df")

    if puts_df is not None and not puts_df.empty:
        df_puts = puts_df.copy()
        for col in ["strike_price", "premium_option_price", "premium_pct",
                    "open_interest", "implied_volatility", "greeks_delta",
                    "live_stock_price", "expected_move"]:
            if col in df_puts.columns:
                df_puts[col] = pd.to_numeric(df_puts[col], errors="coerce")

        if min_oi > 0:
            df_puts = df_puts[df_puts["open_interest"] >= min_oi]
        df_puts = df_puts[df_puts["premium_pct"] >= min_premium_pct]

        if safety_threshold:
            df_puts["is_safe"] = df_puts["strike_price"] < safety_threshold
        else:
            df_puts["is_safe"] = False

        if safe_only:
            df_puts = df_puts[df_puts["is_safe"]]

        if df_puts.empty:
            st.info("Keine Puts mit den aktuellen Filtern. Min OI oder Min Prämie % senken.")
        else:
            df_puts["close_at_90pct"] = (df_puts["premium_option_price"] * 0.10).round(2)

            disp = pd.DataFrame({
                "Zone":          df_puts["is_safe"].apply(lambda v: "✅ Safe" if v else "⚠️ Inside"),
                "Verfall":       df_puts["expiration_date"].astype(str),
                "DTE":           df_puts["days_to_expiration"].astype("Int64"),
                "Strike ($)":    df_puts["strike_price"].apply(lambda v: f"{v:.1f}"),
                "Prämie ($)":    df_puts["premium_option_price"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
                "Prämie %":      df_puts["premium_pct"].apply(lambda v: f"{v:.2f}%" if pd.notna(v) else "—"),
                "Ziel 90% ($)":  df_puts["close_at_90pct"].apply(lambda v: f"{v:.2f}"),
                "OI":            df_puts["open_interest"].apply(lambda v: f"{int(v):,}" if pd.notna(v) else "—"),
                "Delta":         df_puts["greeks_delta"].apply(lambda v: f"{v:.3f}" if pd.notna(v) else "—"),
                "IV":            df_puts["implied_volatility"].apply(lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
            })

            st.caption(f"{len(disp)} Puts — ✅ Safe Zone = Strike unterhalb des Expected Move")

            put_event = st.dataframe(
                disp,
                use_container_width=True,
                height=min(600, 40 + 35 * len(disp)),
                selection_mode="single-row",
                on_select="rerun",
                key="eps_put_table",
            )

            # ── Put detail panel ──────────────────────────────────────────────
            put_selected = put_event.selection.rows if hasattr(put_event, "selection") else []
            if put_selected:
                pr        = df_puts.iloc[put_selected[0]]
                p_strike  = float(pr["strike_price"])
                p_premium = float(pr["premium_option_price"])
                p_dte     = int(pr["days_to_expiration"])
                p_delta   = float(pr["greeks_delta"])   if pd.notna(pr.get("greeks_delta"))   else None
                p_below   = bool(pr["is_safe"])
                p_close90 = round(p_premium * 0.10, 2)
                p_breakeven = round(p_strike - p_premium, 2)
                p_max_gain  = round(p_premium * 100, 2)
                p_profit90  = round((p_premium - p_close90) * 100, 2)

                price = float(live_price) if pd.notna(live_price) else None
                distance     = round(price - p_strike, 2)        if price else None
                distance_pct = round(distance / price * 100, 1)  if price else None
                assign_prob  = round(abs(p_delta) * 100, 0)      if p_delta else None

                st.divider()
                st.subheader(f"{symbol} — ${p_strike:.1f} Put ({p_dte} DTE)")

                if p_below:
                    st.success("✅ Safe Zone — Strike liegt unterhalb des Expected Move. Nur Zuweisung wenn Aktie mehr fällt als erwartet.")
                else:
                    st.warning("⚠️ Innerhalb des Expected Move — realistisches Zuweisungsrisiko nach Earnings.")

                # Kennzahlen
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Prämie / Aktie",     f"${p_premium:.2f}")
                c2.metric("Prämie / Kontrakt",  f"${p_max_gain:.2f}")
                c3.metric("Breakeven",          f"${p_breakeven:.2f}")
                c4.metric("Abstand zum Kurs",   f"${distance:.2f} ({distance_pct:.1f}%)" if distance else "—")

                c5, c6, c7, c8 = st.columns(4)
                c5.metric("Zielkurs (90%)",     f"${p_close90:.2f}")
                c6.metric("Gewinn bei 90%",     f"${p_profit90:.2f} / Kontrakt")
                c7.metric("Zuweisungswahrsch.", f"~{assign_prob:.0f}%" if assign_prob else "—")
                c8.metric("Prämie % vom Strike", f"{float(pr['premium_pct']):.2f}%")

                # Exit-Plan
                st.markdown("**Exit-Plan**")
                st.markdown(
                    f"1. **Morgens nach Earnings:** Buy-to-Close bei **${p_close90:.2f}** (90% Gewinnziel)  \n"
                    f"2. **60 min nach Marktöffnung:** Falls nicht gefüllt → zum Marktpreis schließen  \n"
                    f"3. **Bei Zuweisung:** 100 Aktien zu ${p_strike:.2f} → Covered Call verkaufen"
                )

                with st.expander("Was bedeuten diese Kennzahlen?"):
                    st.markdown(f"""
**Prämie / Aktie** — Betrag den du kassierst. 1 Kontrakt = 100 Aktien = ${p_max_gain:.2f} gesamt.

**Breakeven (${p_breakeven:.2f})** — Strike minus Prämie. Erst darunter machst du Verlust.
Bei Zuweisung kaufst du die Aktie effektiv zu diesem Preis.

**Zielkurs (${p_close90:.2f})** — Zielpreis für deine Buy-to-Close Order am nächsten Morgen.
Du hast die Option zu 10% des ursprünglichen Wertes zurückgekauft = 90% Gewinn einbehalten.

**Zuweisungswahrscheinlichkeit (~{assign_prob:.0f}%)** — abgeleitet aus Delta {p_delta:.3f}.
Delta −0.23 bedeutet ~23% Chance, dass der Put im Geld verfällt.

**Delta** — Je näher an 0, desto weiter OTM (out of the money) und sicherer.
−0.10 bis −0.25 ist typisch für diese Strategie.
""")
            else:
                st.caption("Zeile in der Put-Tabelle anklicken für detaillierte Analyse.")

    elif puts_df is not None:
        st.info(f"Keine wöchentlichen Puts für {symbol} mit den aktuellen Filtern.")

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("Earnings Put Scanner — IV Crush Strategie | Daten: OptionDataMerged")
