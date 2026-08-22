"""
Portfolio Hedge Calculator
==========================
Lädt dein Optionsportfolio, ermittelt das echte Max-Risiko (Summe Brettweiten × 100)
und schlägt KONKRETE Absicherungen vor — nach der Methodik von Eichhorn Coaching.

Kernidee (dein Wunsch):
  "Ich habe 20 Put-Spreads offen, Max-Risiko $14.350. Ich will 50% davon absichern.
   Sag mir: kaufe DIESEN Kontrakt, er kostet DIESE Prämie (dein einziger, fixer Verlust),
   und im Crash ist dein Portfolio zu X% abgesichert."

Eichhorn-Methodik (aus YouTube-Transkripten Eichhorn Coaching):
  - Instrument: reiner Long Put OTM (Delta ~5) auf Index-ETF (SPY/QQQ) — kein Spread,
    weil ein Spread genau im Crash den Gewinn deckelt.
  - Alternativ VIX Long Call (je mehr man Optionen verkauft, desto mehr VIX).
  - Laufzeit: >100 DTE (niedriger Theta-Verlust) oder ~30 DTE wenn Crash erwartet.
  - Timing: NUR bei niedrigem VIX kaufen (~12-20). Bei VIX >30 ist Versicherung teuer.
  - Kosten = feste Versicherungssumme (Betrag), im Optimalfall (kein Crash) verloren.
  - "Bunter Blumenstrauß": Hedge-Budget über mehrere Strikes/Laufzeiten streuen.
  - Max-Verlust des Hedges = die Prämie. Risikofrei nach oben (asymmetrisch).

Alle Daten live aus DB (OptionDataMerged, StockPricesYahoo).
"""

import csv
import io
import logging
import os
import re
from collections import defaultdict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.database import select_into_dataframe

logger = logging.getLogger(os.path.basename(__file__))

_HEDGE_ETFS = {"SPY": "S&P 500", "QQQ": "Nasdaq 100"}

# Crash-Szenarien: Index-Einbruch in %
_SCENARIOS = [
    ("-10% Korrektur",  -0.10),
    ("-20% Bärenmarkt", -0.20),
    ("-35% Crash",      -0.35),
    ("-50% Krise",      -0.50),
]

# VIX-Bewertung fürs Hedge-Timing (Eichhorn: nur bei niedrigem VIX kaufen)
def _vix_verdict(vix: float) -> tuple[str, str]:
    if vix < 16:
        return ("günstig", "success")
    if vix < 22:
        return ("normal", "info")
    if vix < 30:
        return ("erhöht", "warning")
    return ("teuer – Hedge lohnt kaum noch", "error")


# ═══════════════════════════════════════════════════════════════════════════════
# CSV-Parser — liefert offene Spreads MIT Brettweite (für echtes Max-Risiko)
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_symbol(raw: str) -> str | None:
    raw = raw.strip()
    m = re.match(r"^([A-Z0-9]{1,6})\s+\d{6}[CP]\d+", raw)
    if m:
        return m.group(1)
    if re.match(r"^[A-Z]{1,5}$", raw):
        return raw
    return None


def _parse_trades_report(content: str) -> list[dict]:
    """
    Trades_Report: gruppiert nach Symbol+Expiry+P/C, erkennt Spreads (short+long Leg)
    und liefert je Spread die Brettweite → echtes Max-Risiko = Breite × 100.
    """
    try:
        trades = list(csv.DictReader(io.StringIO(content)))
    except Exception:
        return []
    grp = defaultdict(list)
    for t in trades:
        sym = t.get('Symbol', '').strip().split()[0]
        grp[(sym, t.get('Expiry', ''), t.get('Put/Call', ''))].append(t)

    spreads = []
    for (sym, exp, pc), legs in grp.items():
        shorts = [l for l in legs if l.get('Open/CloseIndicator') == 'O' and _f(l.get('Quantity')) < 0]
        longs = [l for l in legs if l.get('Open/CloseIndicator') == 'O' and _f(l.get('Quantity')) > 0]
        if shorts and longs:
            ss = _f(shorts[0].get('Strike'))
            ls = _f(longs[0].get('Strike'))
            if ss and ls:
                width = abs(ss - ls)
                spreads.append({
                    "symbol": sym, "put_call": pc,
                    "short_strike": ss, "long_strike": ls,
                    "width": width, "max_risk": width * 100,
                    "kind": "spread",
                })
        elif shorts and not longs:
            # nackter Short Put: Risiko = Strike × 100 (bis 0)
            ss = _f(shorts[0].get('Strike'))
            if ss:
                spreads.append({
                    "symbol": sym, "put_call": pc,
                    "short_strike": ss, "long_strike": 0.0,
                    "width": ss, "max_risk": ss * 100,
                    "kind": "naked_short",
                })
    return spreads


def _parse_position_report(content: str) -> list[dict]:
    """
    Flex Query Position Report: Optionen einzeln → paart short+long je Symbol/Expiry/PC
    zu Spreads. Ohne Expiry-Spalte fällt es auf reine Notional-Schätzung zurück.
    """
    reader = csv.reader(io.StringIO(content))
    header = []
    legs = []
    for row in reader:
        if not row:
            continue
        if not header:
            header = [c.strip().strip('"') for c in row]
            continue
        data = dict(zip(header, [c.strip().strip('"') for c in row]))
        if data.get("AssetClass", "").strip() != "OPT":
            continue
        qty = _f(data.get("Quantity"))
        if qty == 0:
            continue
        sym = _extract_symbol(data.get("Symbol", "").strip())
        if not sym:
            continue
        legs.append({
            "symbol": sym, "qty": qty,
            "strike": _f(data.get("Strike")),
            "expiry": data.get("Expiry", "") or data.get("LastTradingDay", ""),
            "put_call": (data.get("Put/Call", "") or "").strip().upper(),
        })

    grp = defaultdict(list)
    for l in legs:
        grp[(l["symbol"], l["expiry"], l["put_call"])].append(l)

    spreads = []
    for (sym, exp, pc), grp_legs in grp.items():
        shorts = [l for l in grp_legs if l["qty"] < 0]
        longs = [l for l in grp_legs if l["qty"] > 0]
        if shorts and longs:
            ss = shorts[0]["strike"]
            ls = longs[0]["strike"]
            if ss and ls:
                width = abs(ss - ls)
                spreads.append({"symbol": sym, "put_call": pc, "short_strike": ss,
                               "long_strike": ls, "width": width, "max_risk": width * 100,
                               "kind": "spread"})
        elif shorts:
            ss = shorts[0]["strike"]
            if ss:
                spreads.append({"symbol": sym, "put_call": pc, "short_strike": ss,
                               "long_strike": 0.0, "width": ss, "max_risk": ss * 100,
                               "kind": "naked_short"})
    return spreads


def _f(x) -> float:
    try:
        return float(x)
    except (ValueError, TypeError):
        return 0.0


def _parse_csv(content: str) -> list[dict]:
    first = content.lstrip()
    if first.startswith('"ClientAccountID"') or first.startswith('ClientAccountID'):
        first_line = content.split('\n')[0]
        if 'Open/CloseIndicator' in first_line or 'FifoPnlRealized' in first_line:
            return _parse_trades_report(content)
        return _parse_position_report(content)
    return []


# ═══════════════════════════════════════════════════════════════════════════════
# DB-Abfragen
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def _fetch_price(symbol: str, fallback: float) -> float:
    try:
        df = select_into_dataframe(
            'SELECT close FROM "StockPricesYahoo" WHERE symbol = :sym ORDER BY date DESC LIMIT 1',
            params={"sym": symbol})
        if df is not None and not df.empty and pd.notnull(df.iloc[0, 0]):
            return float(df.iloc[0, 0])
    except Exception:
        pass
    return fallback


@st.cache_data(ttl=300)
def _fetch_put_chain(symbol: str, dte_min: int, dte_max: int) -> pd.DataFrame:
    """Volle Put-Kette eines Hedge-ETFs — Basis für Long-Put-Auswahl."""
    try:
        df = select_into_dataframe(
            """
            SELECT strike_price, day_close AS premium, days_to_expiration AS dte,
                   expiration_date, live_stock_price AS stock_price,
                   abs(greeks_delta) AS delta, implied_volatility AS iv, open_interest AS oi
            FROM "OptionDataMerged"
            WHERE symbol = :sym AND contract_type = 'put'
              AND days_to_expiration BETWEEN :dte_min AND :dte_max
              AND day_close > 0 AND open_interest >= 20
            ORDER BY expiration_date ASC, strike_price DESC
            """,
            params={"sym": symbol, "dte_min": dte_min, "dte_max": dte_max})
        return df if df is not None else pd.DataFrame()
    except Exception as e:
        logger.warning(f"put chain query failed for {symbol}: {e}")
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════════════════════════
# Hedge-Logik — Long Put (Eichhorn: reiner OTM Long Put als Versicherung)
# ═══════════════════════════════════════════════════════════════════════════════

def _long_put_value_at_drop(strike: float, entry_iv: float, dte: int,
                            index_price: float, drop: float) -> float:
    """
    Grober Wert eines Long Puts NACH einem Crash (nicht bei Verfall, sondern kurz danach).
    Zwei Komponenten:
      1) Intrinsischer Wert: max(strike - price_at_drop, 0)
      2) Vola-Aufschlag: im Crash explodiert die IV → Restwert steigt zusätzlich.
    Bewusst konservativ/vereinfacht (keine volle BS-Neupreisung, da IV-Pfad unbekannt).
    """
    price_at_drop = index_price * (1 + drop)
    intrinsic = max(strike - price_at_drop, 0.0)
    # Vola-Bonus: je tiefer der Crash, desto höher der IV-Spike; wirkt v.a. auf Zeitwert.
    # Näherung: OTM-Put gewinnt zusätzlich einen Bruchteil der Fallhöhe als Zeitwert.
    vola_bonus = index_price * abs(drop) * 0.10 if intrinsic == 0 else index_price * abs(drop) * 0.05
    return (intrinsic + vola_bonus) * 100


def _pick_long_puts(chain: pd.DataFrame, index_price: float,
                    target_dte: int) -> list[dict]:
    """
    Wählt aus der Put-Kette mehrere Long-Put-Kandidaten (Eichhorn 'Blumenstrauß'):
    verschiedene OTM-Grade / Deltas am DTE-nächsten Verfall.
    Rückgabe: Liste je Put mit Strike, Prämie, Delta, DTE.
    """
    if chain.empty:
        return []
    chain = chain.copy()
    for c in ["strike_price", "premium", "delta", "iv", "dte"]:
        chain[c] = pd.to_numeric(chain[c], errors="coerce")
    chain = chain.dropna(subset=["strike_price", "premium", "delta"])
    if chain.empty:
        return []
    chain["dte_dist"] = (chain["dte"] - target_dte).abs()
    best_exp = chain.sort_values("dte_dist").iloc[0]["expiration_date"]
    leg = chain[chain["expiration_date"] == best_exp].copy()
    if leg.empty:
        return []
    dte = int(leg["dte"].iloc[0])

    # Drei Schutzprofile nach Delta (Eichhorn: Delta ~5 als Katastrophen-Teenie,
    # etwas höhere Deltas fangen schon flachere Rücksetzer, kosten aber mehr).
    profiles = [
        ("Teenie (Delta ~5)",   0.05, "Nur echter Crash — billigstes Lotterielos (Eichhorn-Favorit)"),
        ("OTM (Delta ~10)",     0.10, "Fängt tiefe Korrekturen, günstig"),
        ("Nah-OTM (Delta ~20)", 0.20, "Reagiert schon früh, teurer"),
    ]
    picks = []
    used_strikes = set()
    for name, tgt_delta, desc in profiles:
        leg["dd"] = (leg["delta"] - tgt_delta).abs()
        row = leg.sort_values("dd").iloc[0]
        strike = float(row["strike_price"])
        if strike in used_strikes:
            continue
        used_strikes.add(strike)
        picks.append({
            "name": name, "desc": desc,
            "strike": strike, "premium": float(row["premium"]),
            "delta": float(row["delta"]), "iv": float(row["iv"]) if pd.notnull(row["iv"]) else 0.0,
            "dte": dte, "expiry": str(best_exp),
            "otm_pct": (index_price - strike) / index_price * 100,
        })
    return picks


# ═══════════════════════════════════════════════════════════════════════════════
# Charts
# ═══════════════════════════════════════════════════════════════════════════════

def _chart_hedge_payoff(pick: dict, n_contracts: int, index_price: float,
                        target_cover: float) -> go.Figure:
    labels = [s[0] for s in _SCENARIOS]
    drops = [s[1] for s in _SCENARIOS]
    payouts = [_long_put_value_at_drop(pick["strike"], pick["iv"], pick["dte"],
                                       index_price, d) * n_contracts for d in drops]
    cost = pick["premium"] * 100 * n_contracts

    fig = go.Figure()
    fig.add_bar(name="Hedge-Auszahlung (est.)", x=labels, y=payouts, marker_color="#22c55e")
    fig.add_hline(y=cost, line_dash="dot", line_color="#ef4444",
                  annotation_text=f"Prämie (Kosten) ${cost:,.0f}")
    fig.add_hline(y=target_cover, line_dash="dash", line_color="#3b82f6",
                  annotation_text=f"Abzusichern ${target_cover:,.0f}")
    fig.update_layout(title=f"Was zahlt der Hedge im Crash? ({pick['name']})",
                      yaxis_title="$", plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                      font_color="#e5e7eb", height=360, legend=dict(orientation="h", y=1.1))
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    st.header("Portfolio Hedge Calculator")
    st.caption("Portfolio laden → Max-Risiko messen → konkreten Absicherungs-Kontrakt "
               "mit fixer Prämie vorschlagen. Methodik: Eichhorn Coaching (Long Put OTM).")

    with st.expander("Wie funktioniert die Absicherung? (Eichhorn-Methodik)", expanded=False):
        st.markdown("""
**Das Prinzip: Long Put als Versicherung.** Du kaufst einen Put weit aus dem Geld auf
einen Index-ETF (SPY/QQQ). Er kostet eine feste Prämie — **das ist dein einziger,
maximaler Verlust**. Passiert nichts, verfällt er (wie eine nicht-genutzte Versicherung).
Kommt der Crash, explodiert sein Wert (Kurssturz **+** Volatilitäts-Spike).

**Regeln aus den Eichhorn-Transkripten:**
- **Reiner Long Put, kein Debit-Spread** — ein Spread deckelt den Gewinn genau dann,
  wenn du ihn brauchst (tiefer Crash).
- **Weit OTM, niedriges Delta (~5–10)** — billig, aber prozentual riesiger Vola-Hebel
  ("Teenie-Puts", wie Michael Burry). Normalisierte Vega ist bei OTM am höchsten.
- **Laufzeit >100 DTE** wenn du den Crash nicht timest (niedriger Theta-Verlust);
  ~30 DTE nur wenn du zeitnah einen Crash erwartest.
- **Nur bei niedrigem VIX kaufen** (~12–20). Bei VIX >30 ist die Versicherung teuer.
- **Kosten = feste Versicherungssumme**, im Optimalfall verloren. Kein fester %-Wert —
  Eichhorn steuert über ein absolutes Budget.
- **"Bunter Blumenstrauß"**: Budget über mehrere Strikes/Laufzeiten streuen.
- Bei sehr vielen verkauften Optionen zusätzlich **VIX Long Calls** erwägen.
""")

    # ── Portfolio laden ───────────────────────────────────────────────────────
    st.subheader("1. Portfolio laden")
    uploaded = st.file_uploader("IBKR/CapTrader CSV (Trades_Report oder Position Report)",
                                type=["csv"])
    spreads: list[dict] = []
    if uploaded:
        try:
            content = uploaded.read().decode("utf-8", errors="ignore")
            spreads = _parse_csv(content)
            if spreads:
                st.success(f"{len(spreads)} offene Positionen erkannt")
            else:
                st.warning("Keine offenen Spreads/Short-Optionen erkannt. "
                           "Bitte Trades_Report oder Position Report mit Strikes hochladen.")
        except Exception as e:
            st.error(f"Fehler: {e}")

    if not spreads:
        st.info("Bitte CSV hochladen um fortzufahren.")
        return

    # Nur PUT-Seite ist das Crash-Downside (Bull Put Spreads). Calls (Bear Call) steigen
    # im Crash NICHT im Risiko — sie sind sogar profitabel. Also Downside = Put-Spreads.
    put_spreads = [s for s in spreads if s["put_call"] == "P"]
    call_spreads = [s for s in spreads if s["put_call"] == "C"]
    total_put_risk = sum(s["max_risk"] for s in put_spreads)
    total_all_risk = sum(s["max_risk"] for s in spreads)

    # ── Parameter ─────────────────────────────────────────────────────────────
    st.subheader("2. Wieviel absichern?")
    c1, c2, c3 = st.columns(3)
    with c1:
        cover_pct = st.slider("Absicherungsgrad", 10, 100, 50, 5, format="%d%%",
                              help="Welcher Anteil des Put-Downside-Risikos abgesichert werden soll") / 100
    with c2:
        dte_hedge = st.select_slider("Laufzeit Hedge (DTE)", [30, 45, 60, 90, 120, 150],
                                     value=120,
                                     help="Eichhorn: >100 DTE für niedrigen Theta-Verlust, "
                                          "30 DTE nur wenn Crash zeitnah erwartet")
    with c3:
        hedge_etf = st.selectbox("Hedge-Instrument", list(_HEDGE_ETFS.keys()),
                                 format_func=lambda k: f"{k} ({_HEDGE_ETFS[k]})")

    index_price = _fetch_price(hedge_etf, 560.0 if hedge_etf == "SPY" else 480.0)
    vix = _fetch_price("^VIX", 18.0)
    vix_text, vix_color = _vix_verdict(vix)

    # ── Risiko-Kennzahlen ─────────────────────────────────────────────────────
    st.subheader("3. Dein Risiko")
    target_cover = total_put_risk * cover_pct
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Offene Put-Spreads", len(put_spreads),
              help="Bull Put Spreads = dein Crash-Downside")
    k2.metric("Max-Risiko (Puts)", f"${total_put_risk:,.0f}",
              help="Summe der Brettweiten × 100 — was du im Worst Case verlierst")
    k3.metric(f"Abzusichern ({cover_pct*100:.0f}%)", f"${target_cover:,.0f}")
    k4.metric("VIX", f"{vix:.1f}", delta=vix_text,
              delta_color="normal" if vix_color in ("success", "info") else "inverse")

    if call_spreads:
        st.caption(f"Hinweis: {len(call_spreads)} Call-Spread(s) (${sum(s['max_risk'] for s in call_spreads):,.0f} "
                   "Risiko) sind bei einem Markt-CRASH nicht das Problem — Bear Calls profitieren "
                   "bei fallenden Kursen. Abgesichert wird nur das Put-Downside.")

    # VIX-Timing-Warnung
    if vix_color == "error":
        st.error(f"VIX {vix:.0f} ist hoch — die Versicherung ist jetzt teuer. Eichhorn: "
                 "Hedges bei niedrigem VIX aufbauen, nicht mitten im Panik-Spike.")
    elif vix_color == "warning":
        st.warning(f"VIX {vix:.0f} ist erhöht — Versicherung kostet mehr als üblich.")

    if total_put_risk <= 0:
        st.info("Keine Put-Spreads erkannt — nichts abzusichern (oder falsches CSV-Format).")
        return

    # ── Hedge-Vorschläge ──────────────────────────────────────────────────────
    st.subheader("4. Konkrete Absicherungs-Vorschläge")
    chain = _fetch_put_chain(hedge_etf, dte_hedge - 15, dte_hedge + 20)
    picks = _pick_long_puts(chain, index_price, dte_hedge)

    if not picks:
        st.warning(f"Keine {hedge_etf}-Put-Kette für DTE ≈ {dte_hedge} in der DB gefunden. "
                   "DTE anpassen oder DB-Update abwarten.")
        st.stop()

    st.caption(f"{hedge_etf} steht bei ${index_price:.2f}. Verfall {picks[0]['expiry']} "
               f"({picks[0]['dte']} DTE). Jeder Vorschlag ist ein **reiner Long Put** — "
               f"Max-Verlust = Prämie, sonst nichts.")

    for pick in picks:
        # Kontraktzahl: so viele Puts, dass die geschätzte Crash-Auszahlung bei -20%
        # ungefähr den abzusichernden Betrag erreicht.
        payout_20 = _long_put_value_at_drop(pick["strike"], pick["iv"], pick["dte"],
                                            index_price, -0.20)
        n_contracts = max(1, round(target_cover / payout_20)) if payout_20 > 0 else 1
        total_cost = pick["premium"] * 100 * n_contracts

        with st.container(border=True):
            st.markdown(f"### {pick['name']}  ·  {pick['desc']}")
            a1, a2, a3, a4 = st.columns(4)
            a1.metric("Kaufe Put", f"${pick['strike']:.0f}",
                      delta=f"{pick['otm_pct']:.0f}% OTM")
            a2.metric("Delta", f"{pick['delta']:.2f}")
            a3.metric("Kontrakte", n_contracts)
            a4.metric("Prämie gesamt (= Max-Verlust)", f"${total_cost:,.0f}",
                      help="Das ist alles, was du verlieren kannst. Risikofrei nach oben.")

            # Konkrete Order-Beschreibung
            st.markdown(
                f"**Order:** Kaufe **{n_contracts}× {hedge_etf} {pick['expiry']} "
                f"${pick['strike']:.0f} Put** @ ~${pick['premium']:.2f}  →  "
                f"Kosten **${total_cost:,.0f}** (fix, das ist deine Versicherungsprämie)."
            )

            # Payout-Tabelle je Szenario
            rows = []
            for label, drop in _SCENARIOS:
                payout = _long_put_value_at_drop(pick["strike"], pick["iv"], pick["dte"],
                                                 index_price, drop) * n_contracts
                cover = min(100, payout / target_cover * 100) if target_cover else 0
                net = payout - total_cost
                rows.append({
                    "Szenario": label,
                    "Hedge zahlt (est.)": f"${payout:,.0f}",
                    "Abzusichern": f"${target_cover:,.0f}",
                    "Deckt ab": f"{cover:.0f}%",
                    "Netto (Auszahlung − Prämie)": f"${net:,.0f}",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            # Kosten-Einordnung
            cost_pct_of_risk = total_cost / total_put_risk * 100 if total_put_risk else 0
            st.caption(
                f"Kosten = **{cost_pct_of_risk:.1f}%** deines Put-Max-Risikos. "
                f"Bei {pick['dte']} DTE ≈ Versicherung für ~{pick['dte']//30} Monate. "
                "Verfällt wertlos wenn kein Crash kommt (wie jede Versicherung)."
            )
            st.plotly_chart(_chart_hedge_payoff(pick, n_contracts, index_price, target_cover),
                            use_container_width=True)

    # ── Detail-Aufstellung offene Positionen ──────────────────────────────────
    with st.expander("Offene Positionen & Brettweiten"):
        df_pos = pd.DataFrame([{
            "Symbol": s["symbol"],
            "Typ": "Put-Spread" if s["put_call"] == "P" and s["kind"] == "spread"
                   else ("Call-Spread" if s["kind"] == "spread" else "Naked Short"),
            "Short": s["short_strike"], "Long": s["long_strike"],
            "Breite": s["width"], "Max-Risiko $": f"${s['max_risk']:,.0f}",
        } for s in spreads])
        st.dataframe(df_pos, use_container_width=True, hide_index=True)

    # ── VIX-Alternative (Eichhorn: je mehr Optionen verkauft, desto mehr VIX) ──
    with st.expander("Alternative: VIX Long Calls (für aktive Stillhalter)"):
        st.markdown(f"""
Eichhorn: *"Je mehr man Optionen verkauft, desto mehr würde ich direkt in den VIX gehen
und nicht nur in den S&P 500."*

**VIX steht aktuell bei {vix:.1f}.** Ein VIX Long Call (OTM, Delta ~5–10, Strike z.B.
{vix*1.5:.0f}–{vix*2:.0f}) explodiert im Crash, weil der VIX-Future dann hochschießt
(historisch bis ~80–90). Rollierendes System: jeden Monat einen neuen ~100-DTE Call kaufen,
kurz vor Verfall im Vola-Spike verkaufen.

*VIX-Optionen sind nicht im DB-Feed — Strike/Prämie musst du in IBKR/thinkorswim ablesen.
Faustregel Eichhorn: Hedge-Budget als "bunten Blumenstrauß" über mehrere Strikes/Laufzeiten
streuen, nicht alles auf einen Kontrakt.*
""")


main()
