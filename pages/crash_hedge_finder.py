"""Crash Hedge Finder — On-the-fly Korrelation + Prämienverkauf auf Gegenwerte."""

import io
import csv
import re
import logging
import os

import numpy as np
import pandas as pd
import streamlit as st

from src.database import select_into_dataframe
from src.page_display_dataframe import create_claude_prompt_strategy_finder

logger = logging.getLogger(os.path.basename(__file__))

_KNOWN_HEDGES = ["GLD", "SLV", "TLT", "IEF", "XLU", "XLP", "XLV", "VXX"]
_DTE_MIN_DEFAULT  = 21
_DTE_MAX_DEFAULT  = 60
_MIN_NEG_CORR     = -0.20
_MIN_IV_RANK      = 30.0
_MIN_OI           = 50
_MIN_CREDIT       = 30
_MIN_MARKET_CAP_B = 10.0   # ≥ $10 Mrd


# ── CSV-Import ────────────────────────────────────────────────────────────────

def _extract_symbol_from_ibkr(raw: str) -> str | None:
    """Extrahiert Underlying aus IBKR Options-Symbol (z.B. 'AAPL  260904P00295000' → 'AAPL')."""
    raw = raw.strip()
    # IBKR compact format: "AAPL  260904P00295000"
    m = re.match(r"^([A-Z0-9]{1,6})\s+\d{6}[CP]\d+", raw)
    if m:
        return m.group(1)
    # Reines Aktien-Symbol: "AAPL", "MSFT"
    if re.match(r"^[A-Z]{1,5}$", raw):
        return raw
    return None


def _parse_transaction_history_csv(content: str) -> list[dict]:
    """
    Parst IBKR Transaction History CSV.
    Leitet offene Positionen ab: nettiert Qty pro Underlying, gibt Symbole mit Netto != 0 zurück.
    Format: Transaction History,Data,Date,Account,Description,Transaction Type,Symbol,Quantity,...
    """
    from collections import defaultdict
    qty_net: dict[str, float] = defaultdict(float)
    header: list[str] = []

    reader = csv.reader(io.StringIO(content))
    for row in reader:
        if not row or len(row) < 3:
            continue
        section = row[0].strip()
        if section != "Transaction History":
            continue
        record_type = row[1].strip()
        if record_type == "Header":
            header = [c.strip() for c in row[2:]]
            continue
        if record_type != "Data" or not header:
            continue

        data = dict(zip(header, row[2:]))
        tx_type  = data.get("Transaction Type", "").strip()
        sym_raw  = data.get("Symbol", "").strip()
        qty_str  = data.get("Quantity", "").strip()

        # Nur echte Trades (keine Dividenden, FX, Fees)
        if tx_type not in ("Buy", "Sell", "BuyOrSell"):
            continue
        if not sym_raw or sym_raw == "-":
            continue

        underlying = _extract_symbol_from_ibkr(sym_raw)
        if not underlying:
            continue

        try:
            qty = float(qty_str) if qty_str and qty_str != "-" else 0.0
        except ValueError:
            continue

        qty_net[underlying] += qty

    # Alle Symbole die netto != 0 haben = offene Position
    positions = []
    for sym, net_qty in qty_net.items():
        if abs(net_qty) >= 0.5:
            positions.append({
                "type": "option",
                "symbol": sym,
                "qty": int(abs(net_qty)),
                "direction": "Long" if net_qty > 0 else "Short",
            })
    return positions


def _parse_position_report_csv(content: str) -> list[dict]:
    """
    Parst IBKR/CapTrader Flex Query Position Report.
    Format: ClientAccountID, Symbol, Quantity, MarkPrice, ..., AssetClass, ...
    Direkte offene Positionen — kein Netting nötig.
    """
    positions = []
    reader = csv.reader(io.StringIO(content))
    header = []
    for row in reader:
        if not row:
            continue
        # Erster Row = Header
        if not header:
            header = [c.strip().strip('"') for c in row]
            continue
        data = dict(zip(header, [c.strip().strip('"') for c in row]))
        asset_class = data.get("AssetClass", "").strip()
        symbol_raw  = data.get("Symbol", "").strip()
        try:
            qty = float(data.get("Quantity", "0") or "0")
        except ValueError:
            continue
        if qty == 0:
            continue

        if asset_class == "STK":
            positions.append({
                "type": "stock",
                "symbol": symbol_raw,
                "qty": int(abs(qty)),
                "direction": "Long" if qty > 0 else "Short",
            })
        elif asset_class == "OPT":
            underlying = _extract_symbol_from_ibkr(symbol_raw)
            if underlying:
                positions.append({
                    "type": "option",
                    "symbol": underlying,
                    "qty": int(abs(qty)),
                    "direction": "Long" if qty > 0 else "Short",
                })
    return positions


def _parse_ibkr_csv(content: str) -> list[dict]:
    """
    Universeller Parser — erkennt automatisch Position Report vs. Transaction History vs. Activity Statement.
    """
    # Position Report (Flex Query) — hat ClientAccountID als erste Spalte
    if content.lstrip().startswith('"ClientAccountID"') or content.lstrip().startswith('ClientAccountID'):
        return _parse_position_report_csv(content)

    # Transaction History Format
    if "Transaction History" in content[:500]:
        return _parse_transaction_history_csv(content)

    # Activity Statement Format (Mark-to-Market)
    positions = []
    reader = csv.reader(io.StringIO(content))
    mtm_header: list[str] = []
    for row in reader:
        if not row:
            continue
        if row[0].strip() != "Mark-to-Market-Performance-Überblick":
            continue
        record_type = row[1].strip() if len(row) > 1 else ""
        if record_type == "Header":
            mtm_header = [c.strip() for c in row[2:]]
            continue
        if record_type != "Data" or not mtm_header:
            continue
        data = dict(zip(mtm_header, row[2:]))
        asset_class = data.get("Vermögenswertkategorie", "").strip()
        symbol_raw  = data.get("Symbol", "").strip()
        try:
            qty_now = float(data.get("Aktuell Menge", "0") or "0")
        except ValueError:
            continue
        if qty_now == 0:
            continue
        if asset_class == "Aktien":
            positions.append({"type": "stock", "symbol": symbol_raw,
                               "qty": int(abs(qty_now)),
                               "direction": "Long" if qty_now > 0 else "Short"})
        elif asset_class == "Aktien- und Indexoptionen":
            m = re.match(r"^([A-Z0-9]+)\s+(\d{2}[A-Z]{3}\d{2})\s+([\d.]+)\s+([CP])$", symbol_raw)
            if not m:
                continue
            sym, expiry_raw, strike_str, cp = m.groups()
            try:
                from datetime import datetime
                expiry = datetime.strptime(expiry_raw, "%d%b%y").strftime("%Y-%m-%d")
            except ValueError:
                expiry = expiry_raw
            positions.append({"type": "option", "symbol": sym,
                               "contract_type": "call" if cp == "C" else "put",
                               "strike": float(strike_str), "expiry": expiry,
                               "contracts": int(abs(qty_now)),
                               "direction": "Long" if qty_now > 0 else "Short"})
    return positions


# ── Datenbankabfragen ─────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _load_large_cap_symbols(min_market_cap_b: float) -> list[str]:
    """Alle Symbole aus OptionDataMerged mit Market Cap ≥ Schwelle."""
    df = select_into_dataframe(
        query="""
            SELECT DISTINCT symbol
            FROM "OptionDataMerged"
            WHERE "Summary_marketCap" >= :min_mcap
            ORDER BY symbol
        """,
        params={"min_mcap": min_market_cap_b * 1_000_000_000},
    )
    if df is None or df.empty:
        return []
    known = set(_KNOWN_HEDGES)
    syms = df["symbol"].dropna().astype(str).tolist()
    # Immer bekannte Hedge-Symbole ergänzen, auch wenn Market Cap fehlt
    for s in _KNOWN_HEDGES:
        if s not in syms:
            syms.append(s)
    return syms


@st.cache_data(ttl=3600, show_spinner=False)
def _load_prices_for_symbols(symbols: tuple[str, ...], lookback_days: int) -> pd.DataFrame:
    """
    Lädt Tagesschlusskurse für die gegebenen Symbole on-the-fly.
    Gibt Wide-DataFrame zurück: Index=Datum, Columns=Symbole.
    """
    if not symbols:
        return pd.DataFrame()
    df = select_into_dataframe(
        query="""
            SELECT symbol, snapshot_date, close
            FROM "StockPricesYahooHistoryDaily"
            WHERE symbol = ANY(:syms)
              AND snapshot_date >= CURRENT_DATE - CAST(:lb || ' days' AS INTERVAL)
              AND close IS NOT NULL
            ORDER BY snapshot_date
        """,
        params={"syms": list(symbols), "lb": str(lookback_days)},
    )
    if df is None or df.empty:
        return pd.DataFrame()
    pivot = df.pivot(index="snapshot_date", columns="symbol", values="close")
    min_pts = int(pivot.shape[0] * 0.7)
    pivot = pivot.dropna(axis=1, thresh=min_pts).ffill()
    return pivot


@st.cache_data(ttl=600, show_spinner=False)
def _load_option_candidates(symbols: tuple[str, ...], dte_min: int, dte_max: int,
                             min_oi: int) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame()
    df = select_into_dataframe(
        query="""
            SELECT
                symbol, contract_type AS option_type, strike_price,
                day_close          AS premium,
                greeks_delta,
                implied_volatility AS iv,
                iv_rank,
                open_interest,
                expiration_date,
                days_to_expiration AS dte,
                live_stock_price   AS stock_price,
                company_name,
                company_sector
            FROM "OptionDataMerged"
            WHERE symbol = ANY(:syms)
              AND days_to_expiration BETWEEN :dte_min AND :dte_max
              AND open_interest >= :min_oi
              AND day_close > 0
        """,
        params={"syms": list(symbols), "dte_min": dte_min,
                "dte_max": dte_max, "min_oi": min_oi},
    )
    return df if df is not None else pd.DataFrame()


# ── Korrelationsberechnung on-the-fly ─────────────────────────────────────────

def _compute_correlations(portfolio_symbols: list[str], universe_symbols: list[str],
                           lookback_days: int) -> pd.DataFrame:
    """
    Berechnet Ø-Korrelation jedes Universe-Symbols vs. allen Portfolio-Symbolen.
    Gibt DataFrame [peer_symbol, correlation_mean] zurück, sortiert aufsteigend.
    """
    all_syms = tuple(sorted(set(portfolio_symbols) | set(universe_symbols)))
    prices = _load_prices_for_symbols(all_syms, lookback_days)

    if prices.empty:
        return pd.DataFrame()

    returns = prices.pct_change().dropna(how="all")

    port_cols  = [s for s in portfolio_symbols if s in returns.columns]
    peer_cols  = [s for s in universe_symbols  if s in returns.columns
                  and s not in portfolio_symbols]

    if not port_cols or not peer_cols:
        return pd.DataFrame()

    # Korrelation jedes Peers gegen alle Portfolio-Symbole → Durchschnitt
    port_ret  = returns[port_cols]
    peer_ret  = returns[peer_cols]
    corr_full = peer_ret.corrwith(port_ret.mean(axis=1), method="pearson")

    result = (
        corr_full
        .rename("correlation_mean")
        .reset_index()
        .rename(columns={"index": "peer_symbol", "symbol": "peer_symbol"})
    )
    result.columns = ["peer_symbol", "correlation_mean"]
    result = result.dropna().sort_values("correlation_mean")
    return result


# ── Strategie-Builder ─────────────────────────────────────────────────────────

def _build_short_put_candidates(opt_df: pd.DataFrame, corr_map: dict,
                                 min_credit: float, min_iv_rank: float) -> list[dict]:
    results = []
    puts = opt_df[opt_df["option_type"] == "put"].copy()
    for col in ["strike_price", "premium", "greeks_delta", "iv", "iv_rank",
                "open_interest", "dte", "stock_price"]:
        puts[col] = pd.to_numeric(puts[col], errors="coerce")
    puts = puts.dropna(subset=["premium", "greeks_delta", "iv_rank", "stock_price"])

    for (sym, exp), group in puts.groupby(["symbol", "expiration_date"]):
        group = group.copy()
        group["_dd"] = (group["greeks_delta"].abs() - 0.30).abs()
        leg = group.loc[group["_dd"].idxmin()]

        stock_price = float(leg["stock_price"])
        strike      = float(leg["strike_price"])
        premium     = float(leg["premium"])
        credit      = premium * 100
        risk        = strike * 100
        iv_rank     = float(leg["iv_rank"])
        dte         = int(leg["dte"])
        iv          = float(leg["iv"])

        if credit < min_credit or risk <= 0 or iv_rank < min_iv_rank:
            continue

        ror  = credit / risk * 100
        otm  = (stock_price - strike) / stock_price * 100
        corr = corr_map.get(sym, 0.0)
        hedge_score = round(abs(corr) * ror, 2)

        results.append({
            "Strategie":     "Short Put",
            "Symbol":        sym,
            "Verfall":       str(exp),
            "DTE":           dte,
            "Beine":         f"Sell {strike:.2f}P",
            "Kredit $":      round(credit, 0),
            "Max Profit $":  round(credit, 0),
            "Max Risiko $":  round(risk, 0),
            "RoR %":         round(ror, 1),
            "Breakeven":     round(strike - premium, 2),
            "Delta":         round(float(leg["greeks_delta"]), 2),
            "IV %":          round(iv * 100, 1),
            "IV Rank":       round(iv_rank, 0),
            "OTM %":         round(otm, 1),
            "Korrelation":   round(corr, 3),
            "Hedge Score":   hedge_score,
            "_stock_price":  stock_price,
            "_company_name": str(leg.get("company_name") or sym),
            "_company_sector": str(leg.get("company_sector") or ""),
            "_legs": [{
                "type": "Put", "action": "Short",
                "strike": strike, "premium": premium, "bs": None,
                "delta": float(leg["greeks_delta"]), "iv": iv,
                "theta": 0.0, "oi": int(leg.get("open_interest") or 0), "volume": 0,
            }],
            "_earnings_warn": False,
        })
    return results


@st.cache_data(ttl=3600, show_spinner=False)
def _load_betas(symbols: tuple[str, ...]) -> dict[str, float]:
    """Lädt Summary_beta aus OptionDataMerged für die gegebenen Symbole."""
    if not symbols:
        return {}
    df = select_into_dataframe(
        query="""
            SELECT DISTINCT ON (symbol) symbol, "Summary_beta"
            FROM "OptionDataMerged"
            WHERE symbol = ANY(:syms)
              AND "Summary_beta" IS NOT NULL
        """,
        params={"syms": list(symbols)},
    )
    if df is None or df.empty:
        return {}
    return dict(zip(df["symbol"], df["Summary_beta"].astype(float)))


@st.cache_data(ttl=3600, show_spinner=False)
def _load_stock_prices_current(symbols: tuple[str, ...]) -> dict[str, float]:
    """Aktueller Kurs pro Symbol aus OptionDataMerged."""
    if not symbols:
        return {}
    df = select_into_dataframe(
        query="""
            SELECT DISTINCT ON (symbol) symbol, live_stock_price
            FROM "OptionDataMerged"
            WHERE symbol = ANY(:syms)
              AND live_stock_price IS NOT NULL
        """,
        params={"syms": list(symbols)},
    )
    if df is None or df.empty:
        return {}
    return dict(zip(df["symbol"], df["live_stock_price"].astype(float)))


# ── Stress-Test Berechnung ────────────────────────────────────────────────────

_SCENARIOS = {
    "−5% Korrektur":   -0.05,
    "−10% Schwäche":   -0.10,
    "−20% Bärenmarkt": -0.20,
    "−30% Crash":      -0.30,
    "−50% Crash 2008": -0.50,
}

# Bekannte Betas für ETFs/Indizes die nicht in OptionDataMerged sind
_FALLBACK_BETAS = {
    "GLD": -0.05, "SLV": 0.10, "TLT": -0.30, "IEF": -0.20,
    "XLU": 0.35,  "XLP": 0.45, "XLV": 0.55,  "VXX": -3.5,
    "SPY": 1.0,   "QQQ": 1.2,  "IWM": 1.1,
}


def _estimate_portfolio_pnl(
    positions: list[dict],
    betas: dict[str, float],
    prices: dict[str, float],
    market_move: float,
) -> dict:
    """
    Schätzt P&L des Portfolios für ein Markt-Szenario.
    Nur Long-Aktienpositionen fließen ein (Optionen vereinfacht via Delta-Näherung).
    """
    rows = []
    total_pnl = 0.0
    total_value = 0.0

    seen = set()
    for p in positions:
        sym = p["symbol"]
        if sym in seen or p.get("direction") != "Long":
            continue
        seen.add(sym)

        beta  = betas.get(sym) or _FALLBACK_BETAS.get(sym) or 1.0
        price = prices.get(sym)
        qty   = p.get("qty", 0)
        if not price or not qty:
            continue

        pos_value   = price * qty
        est_move    = market_move * beta
        est_pnl     = pos_value * est_move
        total_value += pos_value
        total_pnl   += est_pnl

        rows.append({
            "Symbol":        sym,
            "Beta":          round(beta, 2),
            "Kurs":          round(price, 2),
            "Qty":           qty,
            "Position $":    round(pos_value, 0),
            "Geschätzte Bewegung %": round(est_move * 100, 1),
            "Est. P&L $":    round(est_pnl, 0),
        })

    return {
        "rows":        sorted(rows, key=lambda x: x["Est. P&L $"]),
        "total_pnl":   round(total_pnl, 0),
        "total_value": round(total_value, 0),
    }


def _estimate_hedge_pnl(strategy: dict, corr: float, market_move: float) -> dict:
    """
    Schätzt P&L einer Short-Put Hedge-Position im Szenario.
    Underlying bewegt sich ca. corr × market_move (vereinfacht).
    Short Put verliert wenn Underlying fällt unter Break-even.
    """
    underlying_move = corr * market_move  # negativ korreliert → positiv wenn Markt fällt
    stock_price     = strategy["_stock_price"]
    strike          = strategy["_legs"][0]["strike"]
    premium         = strategy["_legs"][0]["premium"]
    delta           = abs(strategy["_legs"][0]["delta"])
    credit          = strategy["Kredit $"]
    breakeven       = strategy["Breakeven"]

    new_price       = stock_price * (1 + underlying_move)
    # Short Put P&L: wenn new_price > strike → voller Kredit
    # wenn new_price zwischen strike und breakeven → partial loss
    # wenn new_price < breakeven → verlust
    if new_price >= strike:
        option_pnl = credit  # voll verfallen
    elif new_price > breakeven:
        option_pnl = (new_price - breakeven) * 100
    else:
        option_pnl = (new_price - strike) * 100 + credit  # max loss

    return {
        "underlying_move_pct": round(underlying_move * 100, 1),
        "new_price":           round(new_price, 2),
        "option_pnl":          round(option_pnl, 0),
        "credit":              round(credit, 0),
    }


# ── Stress-Test Rendering ─────────────────────────────────────────────────────

def _render_stress_test(positions: list[dict], results: list[dict],
                         betas: dict, prices: dict):
    st.markdown("#### Portfolio Stress-Test")
    st.caption(
        "Schätzt den Verlust deines Portfolios in verschiedenen Marktszenarien "
        "und zeigt wie viel ein Hedge-Kandidat davon abfangen würde."
    )

    # Szenario-Auswahl
    scenario_name = st.select_slider(
        "Szenario", options=list(_SCENARIOS.keys()), value="−20% Bärenmarkt"
    )
    market_move = _SCENARIOS[scenario_name]

    port_result = _estimate_portfolio_pnl(positions, betas, prices, market_move)

    if not port_result["rows"]:
        st.warning("Keine Aktienpositionen mit Kursdaten für den Stress-Test gefunden.")
        return

    # Übersicht-Kacheln
    pnl   = port_result["total_pnl"]
    val   = port_result["total_value"]
    pct   = pnl / val * 100 if val else 0
    c1, c2, c3 = st.columns(3)
    c1.metric("Portfolio-Wert (Aktien)", f"${val:,.0f}")
    c2.metric("Geschätzter Verlust", f"${pnl:,.0f}", delta=f"{pct:.1f}%",
              delta_color="inverse")
    c3.metric("Szenario", scenario_name)

    # Portfolio-Tabelle
    with st.expander("Portfolio-Positionen im Detail", expanded=False):
        df_port = pd.DataFrame(port_result["rows"])

        def _color_pnl(col):
            return ["color:#ef4444;font-weight:700" if v < 0
                    else "color:#34d399;font-weight:700" for v in col]

        st.dataframe(
            df_port.style
            .apply(_color_pnl, subset=["Est. P&L $"])
            .format({"Kurs": "${:.2f}", "Position $": "${:,.0f}",
                     "Est. P&L $": "${:,.0f}", "Geschätzte Bewegung %": "{:.1f}%"}),
            hide_index=True,
            use_container_width=True,
        )
        st.caption("Schätzung basiert auf Beta × Marktbewegung. Optionspositionen nicht enthalten.")

    st.divider()

    # Hedge-Kandidaten Gegenrechnung
    st.markdown("#### Hedge-Kandidaten im Szenario")
    st.caption(
        "Für jeden Hedge-Kandidaten: wie entwickelt sich der Kurs im Szenario "
        "(via Korrelation), und wie viel P&L bringt / kostet der Short Put?"
    )

    if not results:
        st.info("Erst 'Hedge-Kandidaten suchen' ausführen.")
        return

    hedge_rows = []
    for r in results[:30]:  # Top 30
        h = _estimate_hedge_pnl(r, r["Korrelation"], market_move)
        hedge_rows.append({
            "Symbol":             r["Symbol"],
            "Strategie":          r["Beine"],
            "Korrelation":        r["Korrelation"],
            "Underlying Δ%":      h["underlying_move_pct"],
            "Neuer Kurs":         h["new_price"],
            "Kredit $":           h["credit"],
            "Option P&L $":       h["option_pnl"],
            "Hedge-Effizienz %":  round(h["option_pnl"] / abs(pnl) * 100, 1) if pnl != 0 else 0,
            "_r": r,
        })

    hedge_rows.sort(key=lambda x: x["Option P&L $"], reverse=True)

    display_cols = ["Symbol", "Strategie", "Korrelation", "Underlying Δ%",
                    "Kredit $", "Option P&L $", "Hedge-Effizienz %"]
    df_hedge = pd.DataFrame(hedge_rows)[display_cols].copy()

    def _color_hedge(col):
        return ["color:#34d399;font-weight:700" if v > 0
                else "color:#ef4444" for v in col]
    def _color_corr(col):
        return ["color:#34d399;font-weight:700" if v <= -0.4
                else ("color:#f59e0b" if v <= -0.2 else "color:#94a3b8") for v in col]

    event = st.dataframe(
        df_hedge.style
        .apply(_color_hedge, subset=["Option P&L $"])
        .apply(_color_corr,  subset=["Korrelation"])
        .format({
            "Korrelation":       "{:.3f}",
            "Underlying Δ%":     "{:+.1f}%",
            "Kredit $":          "${:.0f}",
            "Option P&L $":      "${:+.0f}",
            "Hedge-Effizienz %": "{:.1f}%",
        }),
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key="chf_stress_table",
    )

    sel = event.selection.rows if hasattr(event, "selection") else []
    if sel:
        row_data = hedge_rows[sel[0]]
        h = _estimate_hedge_pnl(row_data["_r"], row_data["_r"]["Korrelation"], market_move)
        st.divider()
        st.markdown(f"**{row_data['Symbol']} — {row_data['Strategie']} im Szenario '{scenario_name}'**")
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Underlying Δ", f"{h['underlying_move_pct']:+.1f}%",
                  help="Geschätzte Kursbewegung via Korrelation × Marktbewegung")
        d2.metric("Neuer Kurs", f"${h['new_price']:.2f}")
        d3.metric("Option P&L", f"${h['option_pnl']:+.0f}",
                  help="Positiv = Prämie bleibt, Negativ = Position läuft gegen dich")
        d4.metric("Hedge-Effizienz",
                  f"{row_data['Hedge-Effizienz %']:.1f}%",
                  help="Option P&L als % des geschätzten Portfolio-Verlustes")

        net = pnl + h["option_pnl"]
        net_pct = net / val * 100 if val else 0
        st.info(
            f"Portfolio-Verlust ohne Hedge: **${pnl:,.0f}** ({pct:.1f}%)  \n"
            f"Option P&L: **${h['option_pnl']:+,.0f}**  \n"
            f"**Netto-Verlust mit Hedge: ${net:,.0f} ({net_pct:.1f}%)**"
        )
        _render_detail(row_data["_r"])

    with st.expander("Wie wird der Stress-Test berechnet?"):
        st.markdown("""
**Portfolio-Verlust:**
`Position $ × Beta × Marktbewegung`
Beta misst wie stark ein Aktie historisch auf den Markt reagiert. Beta 1.5 = 1.5× Marktbewegung.

**Underlying-Bewegung des Hedge-Kandidaten:**
`Korrelation × Marktbewegung`
Korrelation −0.6 bei −20% Markt → Underlying +12% (Gegenbewegung).

**Option P&L (Short Put):**
- Underlying steigt über Strike → voller Kredit eingenommen ✅
- Underlying zwischen Strike und Break-even → teilweiser Verlust
- Underlying unter Break-even → maximaler Verlust

**Hedge-Effizienz %:**
`Option P&L ÷ Portfolio-Verlust × 100`
Zeigt wie viel % des Portfolio-Verlustes der Hedge theoretisch auffängt.

⚠️ *Vereinfachtes Modell — keine Vega/Theta-Effekte, keine Bid-Ask-Spreads, keine Gamma-Einflüsse.*
""")


_DISPLAY_COLS = [
    "Symbol", "Strategie", "Verfall", "DTE", "Beine",
    "Kredit $", "RoR %", "IV Rank", "Korrelation", "Hedge Score", "OTM %",
]


def _style_table(df: pd.DataFrame):
    def _ror(col):
        return ["color:#34d399;font-weight:700" if v >= 15
                else ("color:#f59e0b;font-weight:700" if v >= 8 else "color:#ef4444")
                for v in col]
    def _corr(col):
        return ["color:#34d399;font-weight:700" if v <= -0.4
                else ("color:#f59e0b" if v <= -0.2 else "color:#94a3b8")
                for v in col]
    def _ivr(col):
        return ["color:#34d399;font-weight:700" if 35 <= v <= 65
                else ("color:#f59e0b" if 20 <= v <= 80 else "color:#ef4444")
                for v in col]
    return (
        df.style
        .apply(_ror,  subset=["RoR %"])
        .apply(_corr, subset=["Korrelation"])
        .apply(_ivr,  subset=["IV Rank"])
        .format({
            "Kredit $":    "{:.0f}",
            "RoR %":       "{:.1f}",
            "IV Rank":     "{:.0f}",
            "Korrelation": "{:.3f}",
            "Hedge Score": "{:.2f}",
            "OTM %":       "{:.1f}",
        })
    )


def _render_detail(row: dict):
    st.divider()
    ror   = row["RoR %"]
    corr  = row["Korrelation"]
    color = "#34d399" if ror >= 15 else ("#f59e0b" if ror >= 8 else "#ef4444")
    c_col = "#34d399" if corr <= -0.4 else ("#f59e0b" if corr <= -0.2 else "#94a3b8")
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:12px;margin-bottom:8px;flex-wrap:wrap'>"
        f"<span style='font-size:20px;font-weight:700;'>{row['Strategie']} — {row['Symbol']}</span>"
        f"<span style='background:{color}22;border:1px solid {color}66;border-radius:20px;"
        f"padding:3px 14px;font-size:13px;font-weight:700;color:{color};'>RoR {ror:.1f}%</span>"
        f"<span style='background:{c_col}22;border:1px solid {c_col}66;border-radius:20px;"
        f"padding:3px 14px;font-size:13px;font-weight:600;color:{c_col};'>Korr. {corr:.3f}</span>"
        f"<span style='background:#1e293b;border:1px solid #334155;border-radius:20px;"
        f"padding:3px 14px;font-size:13px;color:#94a3b8;'>Kurs ${row['_stock_price']:.2f}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(f"Verfall: **{row['Verfall']}** · {row['DTE']} DTE · "
               f"Hedge Score: **{row['Hedge Score']:.2f}** (|Korr.| × RoR)")
    st.code(row["Beine"], language=None)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Kredit",     f"${row['Kredit $']:.0f}")
    c2.metric("Max Risiko", f"${row['Max Risiko $']:.0f}")
    c3.metric("IV Rank",    f"{row['IV Rank']:.0f}")
    c4.metric("Breakeven",  f"${row['Breakeven']:.2f}")
    claude_url = create_claude_prompt_strategy_finder(row, sector=row.get("_company_sector"))
    st.link_button("Claude AI Analyse", claude_url, type="primary", use_container_width=True)


def _render_portfolio_heatmap(portfolio_symbols: list[str], lookback_days: int):
    if len(portfolio_symbols) < 2:
        st.info("Mindestens 2 Symbole für die Heatmap.")
        return
    prices = _load_prices_for_symbols(tuple(sorted(portfolio_symbols)), lookback_days)
    if prices.empty:
        st.warning("Keine Preishistorie für die Portfolio-Symbole gefunden.")
        return
    available = [s for s in portfolio_symbols if s in prices.columns]
    if len(available) < 2:
        st.warning("Zu wenige Symbole mit Preishistorie für die Heatmap.")
        return
    returns = prices[available].pct_change().dropna(how="all")
    matrix  = returns.corr(method="pearson")
    styled  = (
        matrix.style
        .background_gradient(cmap="RdYlGn_r", vmin=-1, vmax=1)
        .format("{:.2f}")
    )
    st.dataframe(styled, use_container_width=True)
    pairs = [(a, b) for a in available for b in available
             if a < b and matrix.loc[a, b] >= 0.7]
    if pairs:
        pair_strs = ", ".join(f"{a}/{b}" for a, b in pairs[:5])
        st.warning(f"Klumpenrisiko: {pair_strs} korrelieren ≥ 0.70")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    st.title("Crash Hedge Finder")
    st.caption(
        "Portfolio eingeben → Korrelation gegen Large-Caps berechnen → "
        "Optionsstrategien auf negativ-korrelierte Gegenwerte finden."
    )

    # ── Schritt 1: Portfolio eingeben ─────────────────────────────────────────
    with st.container(border=True):
        col_csv, col_manual = st.columns([1, 1], gap="large")

        with col_csv:
            st.markdown("**CSV-Import (CapTrader / IBKR)**")
            st.caption("Flex Query Position Report **oder** Activity Statement CSV")
            uploaded = st.file_uploader("CSV hochladen", type=["csv"], key="chf_csv",
                                        label_visibility="collapsed")
            if uploaded is not None:
                content  = uploaded.read().decode("utf-8", errors="replace")
                imported = _parse_ibkr_csv(content)
                if imported:
                    st.session_state["chf_positions"] = imported
                    syms = sorted({p["symbol"] for p in imported})
                    st.success(f"{len(imported)} Positionen importiert: {', '.join(syms[:10])}{'...' if len(syms) > 10 else ''}")
                else:
                    st.error(
                        "Keine offenen Positionen gefunden. Unterstützte Formate:\n"
                        "- **Transaction History** CSV (Flex Query / TRANSACTIONS)\n"
                        "- **Activity Statement** CSV mit 'Mark-to-Market Performance' Sektion"
                    )

        with col_manual:
            st.markdown("**Symbole manuell eingeben**")
            st.caption("Kommagetrennt, z.B. AAPL, MSFT, NVDA")
            manual_input = st.text_input(
                "Symbole", placeholder="AAPL, MSFT, NVDA, AMZN",
                key="chf_manual", label_visibility="collapsed"
            )
            if st.button("Übernehmen", key="chf_manual_btn") and manual_input:
                syms = [s.strip().upper() for s in manual_input.split(",") if s.strip()]
                st.session_state["chf_positions"] = [
                    {"type": "stock", "symbol": s, "qty": 100, "direction": "Long"}
                    for s in syms
                ]
                st.success(f"{len(syms)} Symbole übernommen.")

    positions: list[dict] = st.session_state.get("chf_positions", [])
    if not positions:
        st.info("Portfolio hochladen oder Symbole eingeben um fortzufahren.")
        return

    portfolio_symbols = sorted({
        p["symbol"] for p in positions
        if p.get("direction", "Long") == "Long"
    })

    st.markdown(
        f"**Portfolio ({len(portfolio_symbols)} Symbole):** "
        + "  ".join(f"`{s}`" for s in portfolio_symbols)
    )

    # ── Parameter ─────────────────────────────────────────────────────────────
    with st.expander("Parameter", expanded=False):
        p1, p2, p3 = st.columns(3)
        with p1:
            lookback_days = st.selectbox(
                "Korrelations-Lookback", [63, 126, 252, 504, 756, 1260, 1512, 2520],
                index=2,
                format_func=lambda x: {
                    63:   "3 Monate",
                    126:  "6 Monate",
                    252:  "1 Jahr",
                    504:  "2 Jahre",
                    756:  "3 Jahre",
                    1260: "5 Jahre",
                    1512: "6 Jahre",
                    2520: "10 Jahre",
                }[x],
            )
            min_neg_corr = st.slider(
                "Max. Korrelation (Schwelle)", -1.0, 0.0, _MIN_NEG_CORR, 0.05,
            )
        with p2:
            dte_range    = st.slider("DTE-Fenster", 7, 120, (_DTE_MIN_DEFAULT, _DTE_MAX_DEFAULT))
            min_iv_rank  = st.slider("Min. IV Rank", 0, 100, int(_MIN_IV_RANK), 5)
        with p3:
            min_credit   = st.number_input("Min. Kredit ($)", 0, 5000, _MIN_CREDIT, 10)
            min_oi       = st.number_input("Min. Open Interest", 0, 10000, _MIN_OI, 10)
            top_n        = st.slider("Top N Gegenwerte", 5, 50, 20, 5)

        # Sektor-Filter — volle Breite unter den 3 Spalten
        try:
            _sec_df = select_into_dataframe(
                query='SELECT DISTINCT company_sector AS sector FROM "FundamentalData" '
                      "WHERE company_sector IS NOT NULL AND company_sector <> '' ORDER BY company_sector"
            )
            _sector_options = _sec_df["sector"].dropna().tolist() if _sec_df is not None else []
        except Exception:
            _sector_options = []
        selected_sectors = st.multiselect(
            "Sektoren filtern (leer = alle)",
            options=_sector_options,
            key="chf_sectors",
            help="Filtert die Hedge-Strategien nach Sektor des Underlying. Leer = alle Sektoren.",
        )

    # ── Suche-Button ──────────────────────────────────────────────────────────
    run = st.button("Hedge-Kandidaten suchen", type="primary", use_container_width=True)

    if not run and "chf_results" not in st.session_state:
        return

    if run:
        with st.status("Berechne Korrelationen...", expanded=True) as status:
            st.write(f"Lade Large-Cap Universum (≥ ${_MIN_MARKET_CAP_B:.0f} Mrd)...")
            universe = _load_large_cap_symbols(_MIN_MARKET_CAP_B)
            st.write(f"→ {len(universe)} Symbole im Universum")

            st.write(f"Lade Preishistorie ({lookback_days} Tage) für Portfolio + Universum...")
            corr_df = _compute_correlations(portfolio_symbols, universe, lookback_days)

            if corr_df is None or corr_df.empty:
                status.update(label="Fehler", state="error")
                st.error("Keine Preishistorie gefunden.")
                return

            neg_corr = corr_df[corr_df["correlation_mean"] <= min_neg_corr].head(top_n)
            # Bekannte Hedge-Symbole immer ergänzen
            extra = [s for s in _KNOWN_HEDGES if s not in neg_corr["peer_symbol"].values]
            if extra:
                extra_df = corr_df[corr_df["peer_symbol"].isin(extra)]
                neg_corr = pd.concat([neg_corr, extra_df], ignore_index=True).drop_duplicates("peer_symbol")

            st.write(f"→ {len(neg_corr)} negativ-korrelierte Gegenwerte gefunden")

            if neg_corr.empty:
                status.update(label="Keine Gegenwerte gefunden", state="error")
                st.warning("Keine negativ-korrelierten Symbole — Schwelle erhöhen oder Lookback ändern.")
                return

            corr_map = dict(zip(neg_corr["peer_symbol"], neg_corr["correlation_mean"]))
            candidate_symbols = tuple(neg_corr["peer_symbol"].tolist())

            st.write(f"Lade Optionsdaten für {len(candidate_symbols)} Gegenwerte...")
            opt_df = _load_option_candidates(candidate_symbols, dte_range[0], dte_range[1], min_oi)

            if opt_df is None or opt_df.empty:
                status.update(label="Keine Optionsdaten", state="error")
                st.warning("Keine Optionsdaten — DTE-Fenster oder OI-Filter anpassen.")
                return

            results = _build_short_put_candidates(opt_df, corr_map, min_credit, min_iv_rank)
            results.sort(key=lambda x: x["Hedge Score"], reverse=True)
            st.write(f"→ {len(results)} Strategien berechnet")

            # Betas + aktuelle Kurse für Stress-Test
            all_port_syms = tuple(sorted(portfolio_symbols))
            st.write("Lade Beta-Werte für Stress-Test...")
            betas  = _load_betas(all_port_syms)
            prices = _load_stock_prices_current(all_port_syms)
            status.update(label="Fertig", state="complete", expanded=False)

        st.session_state["chf_results"]   = results
        st.session_state["chf_corr_df"]   = neg_corr
        st.session_state["chf_portfolio"] = portfolio_symbols
        st.session_state["chf_lookback"]  = lookback_days
        st.session_state["chf_betas"]     = betas
        st.session_state["chf_prices"]    = prices

    # ── Ergebnisse ────────────────────────────────────────────────────────────
    results        = st.session_state.get("chf_results", [])
    neg_corr       = st.session_state.get("chf_corr_df", pd.DataFrame())
    portfolio_syms = st.session_state.get("chf_portfolio", portfolio_symbols)
    lb             = st.session_state.get("chf_lookback", lookback_days)
    betas          = st.session_state.get("chf_betas", {})
    prices         = st.session_state.get("chf_prices", {})

    # Sektor-Filter on-the-fly (kein Rerun nötig)
    selected_sectors = st.session_state.get("chf_sectors", []) or []
    if selected_sectors and results:
        results_filtered = [r for r in results
                            if r.get("_company_sector", "") in selected_sectors]
    else:
        results_filtered = results

    tab_heatmap, tab_corr, tab_strategies, tab_stress = st.tabs([
        "Portfolio-Matrix", "Negativ-Korrelierte", "Hedge-Strategien", "Stress-Test"
    ])

    with tab_heatmap:
        st.caption("Rot = hohes Klumpenrisiko · Grün = gut diversifiziert")
        _render_portfolio_heatmap(portfolio_syms, lb)

    with tab_corr:
        st.caption("Gegenwerte mit negativer Korrelation zu deinem Portfolio")
        if not neg_corr.empty:
            styled_corr = (
                neg_corr
                .rename(columns={"peer_symbol": "Symbol", "correlation_mean": "Korrelation (Ø)"})
                .style
                .background_gradient(subset=["Korrelation (Ø)"], cmap="RdYlGn", vmin=-1, vmax=0)
                .format({"Korrelation (Ø)": "{:.3f}"})
            )
            st.dataframe(styled_corr, hide_index=True, use_container_width=True)

    with tab_strategies:
        if not results_filtered:
            st.info("Keine Strategien — Parameter lockern oder Sektor-Filter entfernen.")
        else:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Kandidaten",        len({r["Symbol"] for r in results_filtered}))
            m2.metric("Strategien",         len(results_filtered))
            m3.metric("Bester Hedge Score", f"{results_filtered[0]['Hedge Score']:.2f}")
            m4.metric("Bester RoR",         f"{results_filtered[0]['RoR %']:.1f}%")
            if selected_sectors:
                st.caption(f"Sektor-Filter aktiv: {', '.join(selected_sectors)} · {len(results) - len(results_filtered)} ausgeblendet")

            df_disp = pd.DataFrame(results_filtered)[_DISPLAY_COLS].copy()
            event = st.dataframe(
                _style_table(df_disp),
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="chf_table",
                column_config={
                    "Beine":       st.column_config.TextColumn("Beine", width="medium"),
                    "Kredit $":    st.column_config.NumberColumn("Kredit $",    format="$%.0f"),
                    "Korrelation": st.column_config.NumberColumn("Korrelation", format="%.3f"),
                    "Hedge Score": st.column_config.NumberColumn("Hedge Score", format="%.2f"),
                },
            )
            sel = event.selection.rows if hasattr(event, "selection") else []
            if sel:
                _render_detail(results_filtered[sel[0]])
            else:
                st.caption(
                    "Zeile anklicken für Details + Claude-Analyse. "
                    "**Hedge Score** = |Korrelation| × RoR%"
                )

            with st.expander("Wie funktioniert der Hedge Score?"):
                st.markdown("""
**Hedge Score = |Korrelation| × RoR%**

- **Korrelation**: Wie stark bewegt sich dieses Symbol *entgegen* deinem Portfolio?
  Berechnet on-the-fly aus historischen Tagesrenditen (kein Caching auf dem Server).
- **RoR%**: Kredit ÷ maximales Risiko der Short-Put-Position

Ein Short Put auf GLD mit Korrelation −0.6 und RoR 12% → Score **7.2**
Ein Short Put auf XLU mit Korrelation −0.3 und RoR 18% → Score **5.4**

→ GLD ist als Crash-Hedge attraktiver, obwohl XLU mehr Prämie bringt.
""")

    with tab_stress:
        if not results_filtered:
            st.info("Erst 'Hedge-Kandidaten suchen' ausführen.")
        else:
            _render_stress_test(
                [p for p in positions if p.get("direction", "Long") == "Long"],
                results_filtered, betas, prices,
            )


if __name__ == "__main__":
    main()
