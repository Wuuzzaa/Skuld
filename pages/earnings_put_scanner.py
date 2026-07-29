"""Earnings Put Scanner — IV-Crush Strategie"""

import logging
import os

import pandas as pd
import streamlit as st

from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.logger_config import setup_logging
from src.llm_client import LLMClient, LLMProviderError

setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(os.path.basename(__file__))
logger.debug(f"Start Page: {os.path.basename(__file__)}")

# ── AI-Assistent ──────────────────────────────────────────────────────────────
_EPS_AI_SYSTEM_PROMPT = (
    "Du bist ein erfahrener Optionshändler spezialisiert auf die Earnings IV-Crush-Strategie "
    "(Cash-Secured Puts vor Earnings verkaufen). Du bewertest konkret ob der beschriebene Put "
    "eine gute oder schlechte Idee ist — basierend ausschließlich auf den gegebenen Zahlen. "
    "Keine allgemeinen Floskeln. Nenne konkrete Stärken und Risiken mit Bezug auf die Daten. "
    "Antworte auf Deutsch, präzise und strukturiert."
)

_EPS_AI_FORMAT_INSTRUCTION = (
    "Bewerte diesen Earnings-Put-Trade in folgender Struktur:\n\n"
    "**Urteil:** [🟢 Gute Idee / 🟡 Akzeptabel mit Vorbehalt / 🔴 Schlechte Idee] — 1 Satz warum.\n\n"
    "**Stärken** (max 3 Stichpunkte)\n\n"
    "**Risiken** (max 3 Stichpunkte)\n\n"
    "**Fazit:** 1–2 Sätze Empfehlung."
)


def _provider_picker_eps(chat_key: str):
    pc1, pc2 = st.columns([2, 2])
    with pc1:
        choice = st.radio(
            "KI-Modell",
            options=["DeepSeek", "Kimi (K3)"],
            horizontal=True,
            key=f"{chat_key}_provider",
            help="DeepSeek = schnell & günstig. Kimi K3 = 1M-Kontext, kann Web-Recherche.",
        )
    provider = "kimi" if choice.startswith("Kimi") else "deepseek"
    web_search = False
    with pc2:
        if provider == "kimi":
            web_search = st.checkbox(
                "🌐 Web-Recherche (Kimi sucht live im Netz)",
                key=f"{chat_key}_web",
                help="Kimi sucht aktuelle News und Earnings-Daten.",
            )
        else:
            st.caption("Web-Recherche nur mit Kimi verfügbar.")
    return provider, web_search


def _render_eps_ai_chat(
    symbol: str,
    stock_price: float,
    strike: float,
    premium: float,
    dte: int,
    delta: float | None,
    iv_rank: float | None,
    hv: float | None,
    exp_move: float | None,
    exp_move_pct: float | None,
    safety_threshold: float | None,
    earnings_date: str,
    sector: str,
    is_safe: bool,
    breakeven: float,
    max_gain: float,
    prob_assign: float | None,
):
    st.divider()
    st.markdown("### 🤖 KI-Analyse")
    st.caption("Die KI bewertet ob dieser Put-Verkauf eine gute Idee ist. Danach kannst du frei nachfragen.")

    chat_key = f"eps_ai_{symbol}_{strike:.1f}_{dte}"
    msgs_key = f"{chat_key}_messages"
    ctx_key  = f"{chat_key}_context"
    prov_key = f"{chat_key}_provider_used"
    started  = bool(st.session_state.get(msgs_key))

    if not started:
        _provider, _web = _provider_picker_eps(chat_key)
        if st.button("🤖 Analyse anfordern", type="primary", key=f"{chat_key}_btn"):
            safe_str   = "✅ Safe Zone (unter Expected Move)" if is_safe else "⚠️ Innerhalb Expected Move"
            iv_str     = f"{iv_rank:.0f}%" if iv_rank is not None else "n/a"
            hv_str     = f"{hv:.1f}%" if hv is not None else "n/a"
            delta_str  = f"{delta:.3f}" if delta is not None else "n/a"
            em_str     = f"±{exp_move:.2f} ({exp_move_pct:.1f}%)" if exp_move else "n/a"
            prob_str   = f"{prob_assign:.1f}%" if prob_assign is not None else "n/a"
            thresh_str = f"{safety_threshold:.2f}" if safety_threshold else "n/a"

            context = (
                f"Symbol: {symbol} | Sektor: {sector}\n"
                f"Aktienkurs: {stock_price:.2f} | Earnings: {earnings_date}\n"
                f"Strike: {strike:.2f} | DTE: {dte} | {safe_str}\n"
                f"Prämie: {premium:.2f} | Breakeven: {breakeven:.2f} | Max Gewinn: {max_gain:.2f}/Kontrakt\n"
                f"Delta: {delta_str} | Zuweisungswahrscheinlichkeit: {prob_str}\n"
                f"IV Rank: {iv_str} | HV 30d: {hv_str}\n"
                f"Expected Move: {em_str} | Safe-Strike-Schwelle: {thresh_str}\n"
            )
            _prov_label = "Kimi" if _provider == "kimi" else "DeepSeek"
            with st.spinner(f"{_prov_label} analysiert den Trade…"):
                try:
                    response = LLMClient().chat_completion_messages(
                        _provider,
                        messages=[
                            {"role": "system", "content": f"{_EPS_AI_SYSTEM_PROMPT}\n\nTrade-Daten:\n{context}"},
                            {"role": "user",   "content": _EPS_AI_FORMAT_INSTRUCTION},
                        ],
                        temperature=0.2,
                        max_tokens=900,
                        web_search=_web,
                    )
                    st.session_state[ctx_key]  = context
                    st.session_state[msgs_key] = [
                        {"role": "user",      "content": _EPS_AI_FORMAT_INSTRUCTION},
                        {"role": "assistant", "content": response.text},
                    ]
                    st.session_state[f"{chat_key}_model"] = response.model
                    st.session_state[prov_key] = {"provider": _provider, "web_search": _web}
                    st.rerun()
                except LLMProviderError as e:
                    st.error(f"{_prov_label}-Fehler: {e}")
                except Exception as e:
                    st.error(f"Fehler: {e}")
        return

    # ── Phase 2: Chat läuft ───────────────────────────────────────────────────
    _prov_state = st.session_state.get(prov_key, {"provider": "deepseek", "web_search": False})
    _provider   = _prov_state["provider"]
    _web        = _prov_state["web_search"]
    _prov_label = "Kimi" if _provider == "kimi" else "DeepSeek"
    model       = st.session_state.get(f"{chat_key}_model", "?")
    st.caption(f"Modell: {model} · Kontext: {symbol} Put {strike:.1f}")

    for m in st.session_state[msgs_key]:
        if m["role"] == "user" and m["content"] == _EPS_AI_FORMAT_INSTRUCTION:
            continue
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if user_msg := st.chat_input(f"Rückfrage an {_prov_label}…", key=f"{chat_key}_input"):
        with st.chat_message("user"):
            st.markdown(user_msg)
        context  = st.session_state.get(ctx_key, "")
        history  = st.session_state[msgs_key]
        api_msgs = (
            [{"role": "system", "content": f"{_EPS_AI_SYSTEM_PROMPT}\n\nTrade-Daten:\n{context}"}]
            + history
            + [{"role": "user", "content": user_msg}]
        )
        with st.chat_message("assistant"):
            with st.spinner(f"{_prov_label} denkt nach…"):
                try:
                    response = LLMClient().chat_completion_messages(
                        _provider, messages=api_msgs, temperature=0.3, max_tokens=900, web_search=_web,
                    )
                    st.markdown(response.text)
                    history.append({"role": "user",      "content": user_msg})
                    history.append({"role": "assistant", "content": response.text})
                    st.session_state[msgs_key] = history
                except LLMProviderError as e:
                    st.error(f"{_prov_label}-Fehler: {e} — Frage nicht gespeichert.")
                except Exception as e:
                    st.error(f"Fehler: {e} — Frage nicht gespeichert.")

    if st.button("🗑️ Chat zurücksetzen", key=f"{chat_key}_reset"):
        for k in (msgs_key, ctx_key, f"{chat_key}_model", prov_key):
            st.session_state.pop(k, None)
        st.rerun()

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

# ── Scanner Filter ────────────────────────────────────────────────────────────
st.subheader("Scanner Filter")

col1, col2, col3 = st.columns(3)
with col1:
    days_ahead = st.selectbox("Earnings binnen", options=[3, 5, 7, 10, 14, 21, 30, 45, 60],
                               index=2, format_func=lambda x: f"{x} Tagen", key="eps_days_ahead")
with col2:
    require_dividend = st.selectbox("Dividenden-Filter", options=["Alle", "Nur Dividendenzahler"],
                                    index=0, key="eps_div_filter")
with col3:
    max_pe = st.number_input("Max P/E Ratio", min_value=1, max_value=500, value=100, step=5, key="eps_max_pe")

col4, col5, col6 = st.columns(3)
with col4:
    min_iv_rank = st.number_input("Min IV Rank %", min_value=0, max_value=100, value=40, step=5, key="eps_min_iv_rank")
with col5:
    max_iv_rank = st.number_input("Max IV Rank %", min_value=0, max_value=100, value=100, step=5, key="eps_max_iv_rank")
with col6:
    price_min, price_max = st.slider(
        "Kursbereich ($)",
        min_value=0, max_value=1000,
        value=(0, 200), step=5,
        key="eps_price_range",
        help="Nur Aktien in diesem Kursbereich. Max 1000 = keine Obergrenze.",
    )

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
                if price_min > 0:
                    df = df[df["live_stock_price"].isna() | (df["live_stock_price"] >= price_min)]
                if price_max < 1000:
                    df = df[df["live_stock_price"].isna() | (df["live_stock_price"] <= price_max)]

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

    # Berechne safe_threshold pro Zeile und markiere ob safe puts existieren
    # (client-seitig aus den SQL-Daten: prüft ob ATM-Put-Strike < safe_threshold)
    # Wir nutzen die earnings_put_candidates SQL nicht hier — stattdessen prüfen wir
    # ob der Scanner selbst einen "atm_strike" hat der unter der Schwelle liegt,
    # UND ob das Symbol überhaupt Puts unter der Schwelle haben KÖNNTE.
    # Da wir keine Put-Daten pro Symbol im Kandidaten-Scan haben, laden wir sie
    # einmalig beim ersten Toggle-Aufruf aus der DB.

    # Berechne safe_threshold aus den bereits vorhandenen Spalten
    if "live_stock_price" in df.columns and "expected_move" in df.columns:
        df["_safe_threshold"] = df["live_stock_price"] - df["expected_move"]

    st.divider()

    # Filter-Zeile: Sektor-Multiselect + Safe-Put-Toggle
    available_sectors = sorted(df["company_sector"].dropna().unique().tolist()) if "company_sector" in df.columns else []
    filter_col1, filter_col2 = st.columns([3, 1])
    with filter_col1:
        if available_sectors:
            selected_sectors = st.multiselect("Sektor-Filter", options=available_sectors,
                                               default=[], placeholder="Alle Sektoren", key="eps_sector_filter")
            if selected_sectors:
                df = df[df["company_sector"].isin(selected_sectors)]
    with filter_col2:
        safe_puts_only = st.toggle(
            "✅ Nur mit Safe-Put",
            value=False,
            key="eps_safe_puts_only",
            help="Nur Symbole für die ein Put UNTER dem Expected Move in der DB existiert",
        )

    # Safe-Put-Filter: lade puts_check einmalig wenn Toggle aktiviert
    if safe_puts_only:
        check_min_oi  = st.session_state.get("eps_min_oi", 50)
        check_min_prem = st.session_state.get("eps_min_premium_pct", 1.0)
        cache_key = f"{check_min_oi}_{check_min_prem}"

        if ("eps_safe_put_symbols" not in st.session_state or
                st.session_state.get("eps_safe_put_filter_key") != cache_key):
            safe_symbols = set()
            progress = st.progress(0, text="Prüfe Safe-Puts...")
            total = len(df)
            for i, (_, row) in enumerate(df.iterrows()):
                thresh = row.get("_safe_threshold")
                sym = row["symbol"]
                if pd.isna(thresh) or thresh is None:
                    continue
                try:
                    check_sql = PATH_DATABASE_QUERY_FOLDER / "earnings_put_candidates.sql"
                    puts = select_into_dataframe(sql_file_path=check_sql,
                                                 params={"symbol": sym, "min_oi": check_min_oi})
                    if not puts.empty:
                        puts["strike_price"] = pd.to_numeric(puts["strike_price"], errors="coerce")
                        puts["premium_pct"]  = pd.to_numeric(puts["premium_pct"],  errors="coerce")
                        if ((puts["strike_price"] < float(thresh)) &
                                (puts["premium_pct"] >= check_min_prem)).any():
                            safe_symbols.add(sym)
                except Exception:
                    pass
                progress.progress((i + 1) / total, text=f"Prüfe {sym}...")
            progress.empty()
            st.session_state["eps_safe_put_symbols"] = safe_symbols
            st.session_state["eps_safe_put_filter_key"] = cache_key

        safe_symbols = st.session_state.get("eps_safe_put_symbols", set())
        df = df[df["symbol"].isin(safe_symbols)]
    else:
        # Toggle aus → Cache löschen damit beim nächsten Ein-Klicken frisch geladen wird
        if "eps_safe_put_symbols" in st.session_state:
            del st.session_state["eps_safe_put_symbols"]
            st.session_state.pop("eps_safe_put_filter_key", None)

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
        "Symbol":         df["symbol"],
        "Name":           df.get("company_name", pd.Series("—", index=df.index)).fillna("—").astype(str).str.slice(0, 28),
        "Sektor":         df.get("company_sector", pd.Series("—", index=df.index)).fillna("—"),
        "Earnings":       df["earnings_date"].astype(str),
        "Tage":           df["days_to_earnings"].astype("Int64"),
        "Kurs ($)":       df["live_stock_price"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
        "ATM Strike":     df.get("atm_strike", pd.Series(None, index=df.index)).apply(lambda v: f"${v:.1f}" if pd.notna(v) else "—"),
        "Straddle Verf.": df.get("straddle_expiry", pd.Series("—", index=df.index)).astype(str),
        "ATM Call+Put":   df.apply(lambda r: f"${r['expected_move']:.2f}" if pd.notna(r.get("expected_move")) else "—", axis=1),
        "Exp. Move":      df.apply(lambda r: f"±${r['expected_move']:.2f} ({r['expected_move_pct']:.1f}%)"
                                   if pd.notna(r.get("expected_move")) else "—", axis=1),
        "IV Rank":        df.apply(_iv_rank_badge, axis=1),
        "Mkt Cap":        df["market_cap"].apply(_fmt_market_cap),
        "P/E":            df["trailing_pe"].apply(lambda v: f"{v:.1f}" if pd.notna(v) else "—"),
        "Dividende":      df["dividend_classification"].fillna("—"),
    })

    event = st.dataframe(display_df, use_container_width=True,
                         height=min(600, 40 + 35 * len(display_df)),
                         selection_mode="single-row", on_select="rerun", key="eps_candidate_table")

    selected_rows = event.selection.rows if hasattr(event, "selection") else []
    if selected_rows:
        selected_idx = selected_rows[0]
        selected_symbol = df.iloc[selected_idx]["symbol"]
        row = df.iloc[selected_idx]

        price           = float(row["live_stock_price"])        if pd.notna(row.get("live_stock_price"))        else None
        exp_move        = float(row["expected_move"])           if pd.notna(row.get("expected_move"))           else None
        exp_pct         = float(row["expected_move_pct"])       if pd.notna(row.get("expected_move_pct"))       else None
        iv_rank         = float(row["iv_rank"])                 if pd.notna(row.get("iv_rank"))                 else None
        hv              = float(row["historical_volatility_30d"]) if pd.notna(row.get("historical_volatility_30d")) else None
        atm_strike      = float(row["atm_strike"])              if pd.notna(row.get("atm_strike"))              else None
        straddle_expiry = str(row.get("straddle_expiry", ""))

        st.divider()
        st.subheader(f"Analyse — {selected_symbol}")

        if price and exp_move:
            safe_threshold = price - exp_move
            upper_range    = price + exp_move

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
Expected Move = Preis ATM Call + Preis ATM Put  =  ATM Straddle-Preis
```

Konkret für **{selected_symbol}**: Strike **${atm_strike:.1f}**, Verfall **{straddle_expiry}**

> Der Markt selbst sagt damit: *"Wir erwarten eine Bewegung von ±${exp_move:.2f}."*
> Das ist die genaueste Methode — keine Schätzung, sondern implizite Marktmeinung.

---

**Was bedeutet die Prozentzahl ({exp_pct:.1f}%)?**

```
{exp_pct:.1f}% = Expected Move / Aktueller Kurs  =  ${exp_move:.2f} / ${price:.2f}
```

| Zone | Kurs | Bedeutung |
|---|---|---|
| Obergrenze | ${upper_range:.2f} (+{exp_pct:.1f}%) | Erwartete Aufwärtsbewegung |
| Aktuell | ${price:.2f} | — |
| Safe-Strike-Schwelle | ${safe_threshold:.2f} (−{exp_pct:.1f}%) | Puts MIT Strike darunter = Safe Zone |

Puts unter **${safe_threshold:.2f}** werden nur ausgeübt wenn die Aktie **mehr fällt als der Markt erwartet** (< 16% Wahrscheinlichkeit).
""")
                if hv is not None and exp_pct is not None:
                    hv_pct = hv * 100
                    if exp_pct > hv_pct:
                        st.info(f"📊 Implizierte Bewegung ({exp_pct:.1f}%) > historische Volatilität ({hv_pct:.1f}%) — Optionen teuer. Guter Zeitpunkt zum Verkaufen.")
                    else:
                        st.warning(f"📊 Implizierte Bewegung ({exp_pct:.1f}%) ≈ historische Volatilität ({hv_pct:.1f}%) — IV-Crush-Effekt könnte geringer ausfallen.")

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
    iv_rank       = float(symbol_row["iv_rank"]) if pd.notna(symbol_row.get("iv_rank")) else None

    safety_threshold = (float(live_price) - float(expected_move)
                        if pd.notna(live_price) and pd.notna(expected_move) else None)

    st.divider()
    st.subheader(f"Put-Kandidaten — {symbol}")

    p_col1, p_col2, p_col3 = st.columns(3)
    with p_col1:
        min_oi = st.number_input("Min Open Interest", min_value=0, value=50, step=25, key="eps_min_oi")
    with p_col2:
        min_premium_pct = st.number_input("Min Prämie % vom Strike", min_value=0.0, max_value=10.0,
                                          value=1.0, step=0.1, format="%.1f", key="eps_min_premium_pct")
    with p_col3:
        safe_only = st.checkbox("Nur Safe Zone", value=True, key="eps_safe_only",
                                help="Nur Puts anzeigen deren Strike unterhalb des Expected Move liegt")

    if st.session_state["eps_puts_df"] is None:
        with st.spinner(f"Lade Puts für {symbol}..."):
            try:
                sql_path = PATH_DATABASE_QUERY_FOLDER / "earnings_put_candidates.sql"
                puts_df  = select_into_dataframe(sql_file_path=sql_path,
                                                 params={"symbol": symbol, "min_oi": min_oi})
                st.session_state["eps_puts_df"] = puts_df
            except Exception as e:
                st.error(f"Fehler: {e}")
                logger.error(e, exc_info=True)

    puts_df = st.session_state.get("eps_puts_df")

    if puts_df is not None and not puts_df.empty:
        df_puts = puts_df.copy()
        for col in ["strike_price", "premium_option_price", "premium_pct",
                    "open_interest", "implied_volatility", "greeks_delta"]:
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

            live_px = float(live_price) if pd.notna(live_price) else None
            disp = pd.DataFrame({
                "Zone":         df_puts["is_safe"].apply(lambda v: "✅ Safe" if v else "⚠️ Inside"),
                "Verfall":      df_puts["expiration_date"].astype(str),
                "DTE":          df_puts["days_to_expiration"].astype("Int64"),
                "Strike ($)":   df_puts["strike_price"].apply(lambda v: f"{v:.1f}"),
                "Puffer %":     df_puts["strike_price"].apply(
                                    lambda v: f"{(live_px - v) / live_px * 100:.1f}%" if live_px and pd.notna(v) else "—"),
                "Prämie ($)":   df_puts["premium_option_price"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
                "Prämie %":     df_puts["premium_pct"].apply(lambda v: f"{v:.2f}%" if pd.notna(v) else "—"),
                "Ziel 90%":     df_puts["close_at_90pct"].apply(lambda v: f"${v:.2f}"),
                "OI":           df_puts["open_interest"].apply(lambda v: f"{int(v):,}" if pd.notna(v) else "—"),
                "Delta":        df_puts["greeks_delta"].apply(lambda v: f"{v:.3f}" if pd.notna(v) else "—"),
                "IV":           df_puts["implied_volatility"].apply(lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
            })

            st.caption(f"{len(disp)} Puts — ✅ Safe Zone = Strike unter ${safety_threshold:.2f}")

            put_event = st.dataframe(disp, use_container_width=True,
                                     height=min(600, 40 + 35 * len(disp)),
                                     selection_mode="single-row", on_select="rerun", key="eps_put_table")

            put_selected = put_event.selection.rows if hasattr(put_event, "selection") else []
            if put_selected:
                pr          = df_puts.iloc[put_selected[0]]
                p_strike    = float(pr["strike_price"])
                p_premium   = float(pr["premium_option_price"])
                p_dte       = int(pr["days_to_expiration"])
                p_delta     = float(pr["greeks_delta"]) if pd.notna(pr.get("greeks_delta")) else None
                p_below     = bool(pr["is_safe"])
                p_close90   = round(p_premium * 0.10, 2)
                p_max_gain  = round(p_premium * 100, 2)
                p_breakeven = round(p_strike - p_premium, 2)
                p_profit90  = round((p_premium - p_close90) * 100, 2)
                price       = float(live_price) if pd.notna(live_price) else None
                distance    = round(price - p_strike, 2)       if price else None
                dist_pct    = round(distance / price * 100, 1) if price else None
                assign_prob = round(abs(p_delta) * 100, 0)     if p_delta else None

                st.divider()
                st.subheader(f"{symbol} — ${p_strike:.1f} Put ({p_dte} DTE)")

                if p_below:
                    st.success("✅ Safe Zone — Strike liegt unterhalb des Expected Move.")
                else:
                    st.warning("⚠️ Innerhalb des Expected Move — realistisches Zuweisungsrisiko.")

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Prämie / Aktie",    f"${p_premium:.2f}")
                c2.metric("Prämie / Kontrakt", f"${p_max_gain:.2f}")
                c3.metric("Breakeven",         f"${p_breakeven:.2f}")
                c4.metric("Abstand zum Kurs",  f"${distance:.2f} ({dist_pct:.1f}%)" if distance else "—")

                c5, c6, c7, c8 = st.columns(4)
                c5.metric("Zielkurs (90%)",    f"${p_close90:.2f}")
                c6.metric("Gewinn bei 90%",    f"${p_profit90:.2f} / Kontrakt")
                c7.metric("Zuweisung ~",       f"{assign_prob:.0f}%" if assign_prob else "—")
                c8.metric("Prämie % Strike",   f"{float(pr['premium_pct']):.2f}%")

                # ── Grafiken ─────────────────────────────────────────────────
                if price:
                    import plotly.graph_objects as go
                    import numpy as np

                    exp_move_val = float(expected_move) if pd.notna(expected_move) else price * 0.05
                    x_min = p_strike * 0.80
                    x_max = price * 1.10
                    xs = np.linspace(x_min, x_max, 300)
                    ys_pnl = np.where(xs >= p_strike, p_premium, p_premium - (p_strike - xs)) * 100

                    # ── Chart 1: Payoff bei Verfall ──────────────────────────
                    st.markdown("**📊 Payoff bei Verfall**")
                    fig_payoff = go.Figure()

                    # Gewinn/Verlust-Flächen
                    fig_payoff.add_trace(go.Scatter(
                        x=xs, y=np.maximum(ys_pnl, 0),
                        fill="tozeroy", fillcolor="rgba(16,185,129,0.12)",
                        line=dict(width=0), showlegend=False, hoverinfo="skip",
                    ))
                    fig_payoff.add_trace(go.Scatter(
                        x=xs, y=np.minimum(ys_pnl, 0),
                        fill="tozeroy", fillcolor="rgba(239,68,68,0.12)",
                        line=dict(width=0), showlegend=False, hoverinfo="skip",
                    ))
                    fig_payoff.add_trace(go.Scatter(
                        x=xs, y=ys_pnl, mode="lines",
                        line=dict(color="#10b981", width=2.5),
                        hovertemplate="Kurs: $%{x:.2f}<br>P&L: $%{y:.0f}<extra></extra>",
                        name="P&L",
                    ))

                    for x_val, color, label, pos in [
                        (price,       "#60a5fa", f"Kurs ${price:.0f}",       "top right"),
                        (p_breakeven, "#f59e0b", f"BE ${p_breakeven:.0f}",   "top left"),
                        (p_strike,    "#ef4444", f"Strike ${p_strike:.0f}",  "bottom right"),
                    ]:
                        fig_payoff.add_vline(x=x_val, line=dict(color=color, width=1.5, dash="dot"),
                                             annotation_text=label, annotation_position=pos,
                                             annotation_font_size=10)
                    fig_payoff.add_hline(y=0, line=dict(color="#6b7280", width=1, dash="dash"))
                    fig_payoff.add_hline(y=p_profit90,
                                         line=dict(color="#a78bfa", width=1, dash="dot"),
                                         annotation_text=f"90%-Ziel ${p_profit90:.0f}",
                                         annotation_position="right", annotation_font_size=10)

                    fig_payoff.update_layout(
                        height=280, margin=dict(l=0, r=60, t=8, b=0),
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#9ca3af", size=10), showlegend=False,
                        xaxis=dict(title="Aktienkurs bei Verfall ($)",
                                   gridcolor="rgba(255,255,255,0.05)", tickformat="$.0f"),
                        yaxis=dict(title="P&L pro Kontrakt ($)",
                                   gridcolor="rgba(255,255,255,0.05)", tickformat="$,.0f", zeroline=False),
                        hovermode="x unified",
                    )
                    st.plotly_chart(fig_payoff, use_container_width=True, config={"displayModeBar": False})

                    # ── Chart 2: Wahrscheinlichkeitsverteilung ───────────────
                    st.markdown("**🎯 Wahrscheinlichkeitsverteilung am Verfall**")

                    # Breiteres x-Fenster für die Verteilung (±2.5σ)
                    sigma = exp_move_val
                    xs_prob = np.linspace(price - 2.5 * sigma, price + 2.5 * sigma, 400)
                    ys_prob = (1 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((xs_prob - price) / sigma) ** 2)

                    fig_prob = go.Figure()

                    # Gesamte Kurve
                    fig_prob.add_trace(go.Scatter(
                        x=xs_prob, y=ys_prob, mode="lines",
                        line=dict(color="#6b7280", width=2),
                        hovertemplate="Kurs: $%{x:.2f}<extra></extra>",
                        showlegend=False,
                    ))

                    # Safe Zone (< safety_threshold) grün
                    if safety_threshold:
                        sx = xs_prob[xs_prob <= safety_threshold]
                        sy = ys_prob[xs_prob <= safety_threshold]
                        if len(sx):
                            fig_prob.add_trace(go.Scatter(
                                x=np.concatenate([[sx[0]], sx, [sx[-1]]]),
                                y=np.concatenate([[0], sy, [0]]),
                                fill="toself", fillcolor="rgba(16,185,129,0.25)",
                                line=dict(color="#10b981", width=1),
                                name="Safe Zone", showlegend=True,
                                hoverinfo="skip",
                            ))

                    # ±1σ (Expected Move) Bereich grau markieren
                    em_x = xs_prob[(xs_prob >= price - sigma) & (xs_prob <= price + sigma)]
                    em_y = ys_prob[(xs_prob >= price - sigma) & (xs_prob <= price + sigma)]
                    fig_prob.add_trace(go.Scatter(
                        x=np.concatenate([[em_x[0]], em_x, [em_x[-1]]]),
                        y=np.concatenate([[0], em_y, [0]]),
                        fill="toself", fillcolor="rgba(255,255,255,0.04)",
                        line=dict(width=0), showlegend=False, hoverinfo="skip",
                    ))

                    for x_val, color, label, pos in [
                        (price,          "#60a5fa", f"Kurs ${price:.0f}",           "top right"),
                        (price - sigma,  "#9ca3af", f"−EM ${price - sigma:.0f}",    "top left"),
                        (price + sigma,  "#9ca3af", f"+EM ${price + sigma:.0f}",    "top right"),
                    ]:
                        fig_prob.add_vline(x=x_val, line=dict(color=color, width=1.5, dash="dot"),
                                           annotation_text=label, annotation_position=pos,
                                           annotation_font_size=10, annotation_font_color=color)
                    if safety_threshold:
                        fig_prob.add_vline(x=safety_threshold,
                                           line=dict(color="#10b981", width=2, dash="dash"),
                                           annotation_text=f"Safe-Grenze ${safety_threshold:.0f}",
                                           annotation_position="top left",
                                           annotation_font_size=11, annotation_font_color="#10b981")

                    # Wahrscheinlichkeit < safety_threshold berechnen (math.erf = kein scipy nötig)
                    if safety_threshold:
                        import math
                        prob_below = (1 + math.erf((safety_threshold - price) / (sigma * math.sqrt(2)))) / 2 * 100
                        fig_prob.add_annotation(
                            x=safety_threshold - sigma * 0.3,
                            y=ys_prob.max() * 0.6,
                            text=f"P(Zuweisung)<br>≈ {prob_below:.1f}%",
                            showarrow=False,
                            font=dict(size=13, color="#10b981"),
                            bgcolor="rgba(16,185,129,0.12)",
                            bordercolor="#10b981", borderwidth=1,
                        )

                    fig_prob.update_layout(
                        height=300, margin=dict(l=0, r=60, t=8, b=0),
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#9ca3af", size=10),
                        legend=dict(orientation="h", y=1.08, x=0, font_size=10),
                        xaxis=dict(title="Aktienkurs bei Verfall ($)",
                                   gridcolor="rgba(255,255,255,0.05)", tickformat="$.0f"),
                        yaxis=dict(title="Wahrscheinlichkeitsdichte",
                                   gridcolor="rgba(255,255,255,0.05)",
                                   showticklabels=False, zeroline=False),
                        hovermode="x unified",
                    )
                    st.plotly_chart(fig_prob, use_container_width=True, config={"displayModeBar": False})

                    # ── IV Rank Gauge ────────────────────────────────────────
                    if iv_rank is not None:
                        gauge_fig = go.Figure(go.Indicator(
                            mode="gauge+number",
                            value=iv_rank,
                            number=dict(suffix="%", font=dict(size=20, color="#e5e7eb")),
                            title=dict(text="IV Rank", font=dict(size=13, color="#9ca3af")),
                            gauge=dict(
                                axis=dict(range=[0, 100], tickwidth=1, tickcolor="#6b7280",
                                          tickfont=dict(color="#9ca3af", size=10)),
                                bar=dict(color="#10b981" if iv_rank >= 60 else "#f59e0b" if iv_rank >= 40 else "#6b7280",
                                         thickness=0.3),
                                bgcolor="rgba(0,0,0,0)",
                                borderwidth=0,
                                steps=[
                                    dict(range=[0, 40],  color="rgba(107,114,128,0.15)"),
                                    dict(range=[40, 60], color="rgba(245,158,11,0.15)"),
                                    dict(range=[60, 100],color="rgba(16,185,129,0.15)"),
                                ],
                                threshold=dict(line=dict(color="#ef4444", width=2), value=50),
                            ),
                        ))
                        gauge_fig.update_layout(
                            height=200, margin=dict(l=20, r=20, t=30, b=10),
                            paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ca3af"),
                        )
                        gc1, gc2, gc3 = st.columns([1, 1, 2])
                        with gc1:
                            st.plotly_chart(gauge_fig, use_container_width=True)
                        with gc2:
                            st.markdown(
                                f"**IV Rank {iv_rank:.0f}%**\n\n"
                                f"{'🟢 Hoch — Optionen teuer, gut zum Verkaufen' if iv_rank >= 60 else '🟡 Mittel — Optionen fair bewertet' if iv_rank >= 40 else '⚪ Niedrig — IV-Crush-Effekt könnte gering sein'}"
                            )

                st.markdown("**Exit-Plan**")
                st.markdown(
                    f"1. **Morgens nach Earnings:** Buy-to-Close bei **${p_close90:.2f}** (90% Ziel)  \n"
                    f"2. **60 min nach Marktöffnung:** Falls nicht gefüllt → zum Marktpreis schließen  \n"
                    f"3. **Bei Zuweisung:** 100 Aktien zu ${p_strike:.2f} → Covered Call verkaufen"
                )

                with st.expander("Was bedeuten diese Kennzahlen?"):
                    st.markdown(f"""
**Prämie / Aktie** — Betrag den du kassierst. 1 Kontrakt = 100 Aktien = ${p_max_gain:.2f} gesamt.

**Breakeven (${p_breakeven:.2f})** — Strike minus Prämie. Erst darunter machst du Verlust.

**Zielkurs (${p_close90:.2f})** — Buy-to-Close Zielpreis. Du kaufst die Option für 10% zurück = 90% Gewinn.

**Zuweisungswahrscheinlichkeit (~{assign_prob:.0f}%)** — aus Delta {p_delta:.3f} abgeleitet. Delta −0.20 = ~20% Chance auf Zuweisung.

**Delta** — Je näher an 0, desto weiter OTM und sicherer. −0.10 bis −0.25 ist typisch für diese Strategie.
""")

                # ── KI-Analyse ────────────────────────────────────────────────
                _hv_for_ai = float(symbol_row["historical_volatility_30d"]) if pd.notna(symbol_row.get("historical_volatility_30d")) else None
                _sector_for_ai = str(symbol_row.get("company_sector", "—"))
                _prob_for_ai = round(abs(p_delta) * 100, 1) if p_delta else None
                _thresh_for_ai = safety_threshold

                _render_eps_ai_chat(
                    symbol=symbol,
                    stock_price=float(live_price) if pd.notna(live_price) else 0.0,
                    strike=p_strike,
                    premium=p_premium,
                    dte=p_dte,
                    delta=p_delta,
                    iv_rank=iv_rank,
                    hv=_hv_for_ai,
                    exp_move=float(expected_move) if pd.notna(expected_move) else None,
                    exp_move_pct=float(symbol_row["expected_move_pct"]) if pd.notna(symbol_row.get("expected_move_pct")) else None,
                    safety_threshold=_thresh_for_ai,
                    earnings_date=str(earnings_date),
                    sector=_sector_for_ai,
                    is_safe=p_below,
                    breakeven=p_breakeven,
                    max_gain=p_max_gain,
                    prob_assign=_prob_for_ai,
                )
            else:
                st.caption("Zeile anklicken für detaillierte Analyse.")

    elif puts_df is not None:
        st.info(f"Keine Puts für {symbol} mit den aktuellen Filtern.")

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("Earnings Put Scanner — IV Crush Strategie | Daten: OptionDataMerged")
