"""
Portfolio Hedge Calculator — vollständig nach Eric Ludwig "Hedging mit Optionen"
================================================================================
Tab 1: Portfolio-Analyse   — was für ein Portfolio habe ich?
Tab 2: Kanarienvögel       — Frühwarnindikatoren (VIX, Put/Call Ratio, Hindenburg Omen)
Tab 3: Strategie-Wahl      — alle 6 Strategien aus dem Buch mit Auto-Empfehlung
Tab 4: Konkrete Absicherung — konkrete Kontrakte aus der DB
Tab 5: Ausstiegs-Timing    — Das Licht am Ende des Tunnels (MACD + VIX-Doppelsignal)
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

_SCENARIOS = [
    ("-10% Korrektur",  -0.10),
    ("-20% Bärenmarkt", -0.20),
    ("-35% Crash",      -0.35),
    ("-50% Krise",      -0.50),
]

_SECTOR_TO_HEDGE: dict[str, str] = {
    "technology":         "QQQ / XLK",
    "communication":      "QQQ / XLK",
    "energy":             "XLE",
    "utilities":          "XLU",
    "health":             "XLV",
    "healthcare":         "XLV",
    "consumer staples":   "XLP",
    "consumer defensive": "XLP",
    "financials":         "XLF",
    "industrials":        "XLI",
    "materials":          "XLB",
    "real estate":        "XLRE",
}

_FALLBACK_BETAS: dict[str, float] = {
    "GLD": -0.05, "SLV": 0.10, "TLT": -0.30, "IEF": -0.20,
    "XLU": 0.35,  "XLP": 0.45, "XLV": 0.55,  "VXX": -3.5,
    "SPY": 1.0,   "QQQ": 1.2,  "IWM": 1.1,
}

_STRATEGIES = [
    {
        "name":         "VXX Time-Straddle",
        "badge":        "Autor Nr. 1",
        "badge_color":  "#22c55e",
        "cost_label":   "Selbstfinanzierend",
        "book":         "Kapitel 9 — Der VXX Time-Straddle",
        "short":        "Dauerhafter Crash-Schutz via Volatilität — selbstfinanziert durch wöchentliche Short Calls.",
        "construction": "3× Long Straddle (Put+Call ATM, ≥120 DTE) + 1× Weekly Short Call\nVerhältnis immer 3 Straddles : 1 Short Call",
        "when":         "Immer aktiv (bei VIX < 25). Einzige Ausnahme: nach Ausstiegssignal warten bis VIX < 25.",
        "cost":         "Wöchentliche Call-Prämien finanzieren die Straddle-Kosten. Bei Crash: Straddle explodiert.",
        "key":          "vxx_straddle",
    },
    {
        "name":         "Grizzly-Hedge",
        "badge":        "Selbstfinanziert",
        "badge_color":  "#22c55e",
        "cost_label":   "Kostenlos möglich",
        "book":         "Kapitel 7 — Der Grizzly-Hedge",
        "short":        "Bear Put Spread + Short Call. Der Call finanziert den Spread — keine Kosten.",
        "construction": "Long Put Strike A + Short Put Strike B (B < A) + Short Call Strike C\nCall-Prämie ≥ 50% der Spread-Kosten",
        "when":         "Wenn Aufwärtspotenzial des Depots ohnehin begrenzt ist. Call NUR wenn gedeckt (1 Call : 100 Aktien).",
        "cost":         "Selbstfinanziert wenn Call-Prämie ≥ 50% der Spread-Kosten. Sonst nicht verwenden.",
        "key":          "grizzly",
    },
    {
        "name":         "Zorro-Hedge",
        "badge":        "Günstig",
        "badge_color":  "#22c55e",
        "cost_label":   "~10–15% der Prämie",
        "book":         "Kapitel 6 — Der Zorro-Hedge",
        "short":        "2× Bear Put Spread — das Zick-Zack-Profil. Mehr Schutz als einfacher Spread.",
        "construction": "2× (Long Put Strike A + Short Put Strike B)\nKosten = 12–20% des maximalen Gewinns (Faustregel)",
        "when":         "Bei konkreter Crash-Erwartung. Stop-Loss bei 50% der Kosten.",
        "cost":         "~10–15% der monatlichen Prämieneinnahme.",
        "key":          "zorro",
    },
    {
        "name":         "Bear Put Spread",
        "badge":        "Moderat",
        "badge_color":  "#f59e0b",
        "cost_label":   "~10–20% der Prämie",
        "book":         "Kapitel 6 — Der Zorro-Hedge (Basis)",
        "short":        "Klassischer Bear Put Spread. Schützt in einer definierten Zone.",
        "construction": "Long Put Strike A (aus dem Geld) + Short Put Strike B (B < A)\nBeide gleiche Laufzeit (Vertical Spread)",
        "when":         "Bei Crash-Erwartung. Stop-Loss 50% der Kosten. Kosten = 12–20% des Max-Gewinns.",
        "cost":         "~10–20% der monatlichen Prämieneinnahme.",
        "key":          "bear_put_spread",
    },
    {
        "name":         "Collar / Open Collar",
        "badge":        "Kostenlos möglich",
        "badge_color":  "#f59e0b",
        "cost_label":   "Zero-Cost möglich",
        "book":         "Kapitel 4 — Der Collar und der Open Collar",
        "short":        "Long Put + Short Call gegen bestehende Aktienposition. Call finanziert Put.",
        "construction": "Long Put Strike A (OTM) + Short Call Strike B (OTM, B > Kurs)\nBeide gleiche Laufzeit. 1 Call pro 100 Aktien!",
        "when":         "Für Einzelpositionen. Wenn Aktien bereits Buchgewinne haben. Bei Seitwärtsmarkt.",
        "cost":         "Zero-Cost wenn Call-Prämie = Put-Prämie. Aufwärtspotenzial bis Call-Strike.",
        "key":          "collar",
    },
    {
        "name":         "Butterfly-Hedge",
        "badge":        "Sehr günstig",
        "badge_color":  "#f59e0b",
        "cost_label":   "Fast kostenlos",
        "book":         "Kapitel 8 — Der Butterfly-Hedge",
        "short":        "Long Put A + 2× Short Put B + Long Put C. Sehr billig, aber nur für ~10% Korrektur.",
        "construction": "Long Put A (5% OTM) + Short 2× Put B (weitere 7% OTM) + Long Put C (gleicher Abstand)\nAlle gleiche Laufzeit. ≥45 Tage.",
        "when":         "Nur bei klassischer ~10% Korrektur, NICHT bei echtem Crash (Schutz endet bei Strike C).",
        "cost":         "Fast kostenlos durch 2 Short Puts. Gewinn-Exit bei 30% Max-Gewinn, Stop bei 50% Kosten.",
        "key":          "butterfly",
    },
    {
        "name":         "Protective Put",
        "badge":        "Teuer",
        "badge_color":  "#ef4444",
        "cost_label":   "20–30% der Prämie",
        "book":         "Kapitel 3 — Der Protective Put",
        "short":        "Klassische Vollkasko-Versicherung. Teuer — langfristig oft ein Pyrrhussieg.",
        "construction": "Long Put (am Geld oder leicht OTM) pro 100 Aktien\nMin. 6 Monate Laufzeit. Stop-Loss 50%.",
        "when":         "NUR bei VIX < 20 kaufen. Langfristig zu teuer für dauerhaften Einsatz (Pyrrhussieg).",
        "cost":         "20–30% der monatlichen Prämieneinnahme. Kosten häufen sich über die Zeit.",
        "key":          "protective_put",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# CSV-Parser (unverändert — bereits gefixt für IBKR Flex Query)
# ═══════════════════════════════════════════════════════════════════════════════

def _f(x) -> float:
    try:
        return float(x)
    except (ValueError, TypeError):
        return 0.0


def _extract_symbol(raw: str) -> str | None:
    raw = raw.strip()
    m = re.match(r"^([A-Z0-9]{1,6})\s+\d{6}[CP]\d+", raw)
    if m:
        return m.group(1)
    if re.match(r"^[A-Z]{1,5}$", raw):
        return raw
    return None


def _parse_trades_report(content: str) -> list[dict]:
    try:
        trades = list(csv.DictReader(io.StringIO(content)))
    except Exception:
        return []
    grp: dict = defaultdict(list)
    for t in trades:
        sym = t.get("Symbol", "").strip().split()[0]
        grp[(sym, t.get("Expiry", ""), t.get("Put/Call", ""))].append(t)
    spreads = []
    for (sym, exp, pc), legs in grp.items():
        shorts = [l for l in legs if l.get("Open/CloseIndicator") == "O" and _f(l.get("Quantity")) < 0]
        longs  = [l for l in legs if l.get("Open/CloseIndicator") == "O" and _f(l.get("Quantity")) > 0]
        if shorts and longs:
            ss, ls = _f(shorts[0].get("Strike")), _f(longs[0].get("Strike"))
            if ss and ls:
                w = abs(ss - ls)
                spreads.append({"symbol": sym, "put_call": pc, "short_strike": ss,
                                "long_strike": ls, "width": w, "max_risk": w * 100, "kind": "spread"})
        elif shorts:
            ss = _f(shorts[0].get("Strike"))
            if ss:
                spreads.append({"symbol": sym, "put_call": pc, "short_strike": ss,
                                "long_strike": 0.0, "width": ss, "max_risk": ss * 100, "kind": "naked_short"})
    return spreads


def _parse_position_report(content: str) -> list[dict]:
    reader = csv.reader(io.StringIO(content))
    header: list[str] = []
    legs: list[dict] = []
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
        sym_raw = data.get("Symbol", "").strip()
        sym = _extract_symbol(sym_raw)
        if not sym:
            continue
        strike_raw   = data.get("Strike", "")
        expiry_raw   = data.get("Expiry", "") or data.get("LastTradingDay", "")
        put_call_raw = (data.get("Put/Call", "") or "").strip().upper()
        m = re.match(r"^([A-Z0-9]{1,6})\s+(\d{6})([CP])(\d+)$", sym_raw.strip())
        if m and (not strike_raw or not put_call_raw):
            try:
                from datetime import datetime as _dt
                expiry_raw   = _dt.strptime(m.group(2), "%y%m%d").strftime("%Y-%m-%d")
                put_call_raw = m.group(3)
                strike_raw   = str(float(m.group(4)) / 1000.0)
            except Exception:
                pass
        legs.append({"symbol": sym, "qty": qty, "strike": _f(strike_raw),
                     "expiry": expiry_raw, "put_call": put_call_raw})

    grp: dict = defaultdict(list)
    for l in legs:
        grp[(l["symbol"], l["expiry"], l["put_call"])].append(l)
    spreads = []
    for (sym, exp, pc), grp_legs in grp.items():
        shorts = [l for l in grp_legs if l["qty"] < 0]
        longs  = [l for l in grp_legs if l["qty"] > 0]
        if shorts and longs:
            ss, ls = shorts[0]["strike"], longs[0]["strike"]
            if ss and ls:
                w = abs(ss - ls)
                spreads.append({"symbol": sym, "put_call": pc, "short_strike": ss,
                                "long_strike": ls, "width": w, "max_risk": w * 100, "kind": "spread"})
        elif shorts:
            ss = shorts[0]["strike"]
            if ss:
                spreads.append({"symbol": sym, "put_call": pc, "short_strike": ss,
                                "long_strike": 0.0, "width": ss, "max_risk": ss * 100, "kind": "naked_short"})
    return spreads


def _parse_position_report_full(content: str) -> list[dict]:
    """Parst Flex Query — gibt vollständige Positions-Liste (STK + OPT) zurück."""
    reader = csv.reader(io.StringIO(content))
    header: list[str] = []
    positions: list[dict] = []
    for row in reader:
        if not row:
            continue
        if not header:
            header = [c.strip().strip('"') for c in row]
            continue
        data = dict(zip(header, [c.strip().strip('"') for c in row]))
        asset_class = data.get("AssetClass", "").strip()
        sym_raw = data.get("Symbol", "").strip()
        try:
            qty = float(data.get("Quantity", "0") or "0")
        except ValueError:
            continue
        if qty == 0:
            continue
        def _fv(k):
            v = data.get(k, "").strip()
            try:
                return float(v) if v else None
            except ValueError:
                return None
        if asset_class == "STK":
            positions.append({
                "type": "stock", "symbol": sym_raw,
                "qty": int(abs(qty)), "direction": "Long" if qty > 0 else "Short",
                "cost_basis_price": _fv("CostBasisPrice"),
                "mark_price": _fv("MarkPrice"),
                "currency": data.get("CurrencyPrimary", "USD").strip(),
            })
        elif asset_class == "OPT":
            underlying = _extract_symbol(sym_raw)
            if not underlying:
                continue
            m = re.match(r"^([A-Z0-9]{1,6})\s+(\d{6})([CP])(\d+)$", sym_raw.strip())
            strike = expiry = option_type = None
            if m:
                try:
                    from datetime import datetime as _dt
                    expiry      = _dt.strptime(m.group(2), "%y%m%d").strftime("%Y-%m-%d")
                    option_type = "put" if m.group(3) == "P" else "call"
                    strike      = float(m.group(4)) / 1000.0
                except Exception:
                    pass
            positions.append({
                "type": "option", "symbol": underlying,
                "qty": int(abs(qty)), "direction": "Long" if qty > 0 else "Short",
                "strike": strike, "expiry": expiry, "option_type": option_type,
                "cost_basis_price": _fv("CostBasisPrice"),
                "mark_price": _fv("MarkPrice"),
                "currency": data.get("CurrencyPrimary", "USD").strip(),
            })
    return positions


def _parse_csv_full(content: str) -> tuple[list[dict], list[dict]]:
    """Gibt (positions, spreads) zurück."""
    first = content.lstrip()
    if first.startswith('"ClientAccountID"') or first.startswith("ClientAccountID"):
        first_line = content.split("\n")[0]
        if "Open/CloseIndicator" in first_line or "FifoPnlRealized" in first_line:
            return [], _parse_trades_report(content)
        positions = _parse_position_report_full(content)
        spreads   = _parse_position_report(content)
        return positions, spreads
    return [], []


# ═══════════════════════════════════════════════════════════════════════════════
# DB-Helfer
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


@st.cache_data(ttl=300, show_spinner=False)
def _phc_load_vix() -> float | None:
    df = select_into_dataframe(
        query='SELECT live_stock_price FROM "OptionDataMerged" WHERE symbol IN (\'I:VIX\',\'^VIX\',\'VIX\') AND live_stock_price IS NOT NULL LIMIT 1',
    )
    if df is not None and not df.empty:
        return float(df.iloc[0]["live_stock_price"])
    return _fetch_price("^VIX", None) or None


@st.cache_data(ttl=300, show_spinner=False)
def _phc_load_vix3m() -> float | None:
    df = select_into_dataframe(
        query='SELECT live_stock_price FROM "OptionDataMerged" WHERE symbol IN (\'VIX3M\',\'^VIX3M\',\'VXMT\') AND live_stock_price IS NOT NULL LIMIT 1',
    )
    if df is not None and not df.empty:
        return float(df.iloc[0]["live_stock_price"])
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def _phc_load_meta(symbols: tuple) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame()
    df = select_into_dataframe(
        query="""
            SELECT DISTINCT ON (symbol) symbol,
                "Summary_beta"   AS beta,
                live_stock_price AS price,
                company_sector   AS sector
            FROM "OptionDataMerged"
            WHERE symbol = ANY(:syms) AND live_stock_price IS NOT NULL
            ORDER BY symbol, live_stock_price DESC
        """,
        params={"syms": list(symbols)},
    )
    return df if df is not None else pd.DataFrame()


@st.cache_data(ttl=300)
def _fetch_put_chain(symbol: str, dte_min: int, dte_max: int) -> pd.DataFrame:
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


@st.cache_data(ttl=300, show_spinner=False)
def _phc_load_bear_put_chain(symbol: str, dte_min: int, dte_max: int) -> pd.DataFrame:
    """Put-Chain für Bear-Put-Spread-Kandidaten."""
    return _fetch_put_chain(symbol, dte_min, dte_max)


# ═══════════════════════════════════════════════════════════════════════════════
# Portfolio-Profil (analog crash_hedge_finder._load_portfolio_profile)
# ═══════════════════════════════════════════════════════════════════════════════

def _phc_portfolio_profile(positions: list[dict], spreads: list[dict]) -> dict:
    stock_pos = [p for p in positions if p.get("type") == "stock" and p.get("direction", "Long") == "Long"]
    n_stocks  = len(stock_pos)
    symbols   = tuple(sorted({p["symbol"] for p in positions}))

    meta_df = _phc_load_meta(symbols)
    betas:   dict[str, float] = {}
    prices:  dict[str, float] = {}
    sectors: dict[str, str]   = {}
    if not meta_df.empty:
        for _, row in meta_df.iterrows():
            sym = str(row["symbol"])
            try:
                if row.get("beta") is not None:
                    betas[sym]  = float(row["beta"])
                if row.get("price") is not None:
                    prices[sym] = float(row["price"])
                if row.get("sector") and str(row["sector"]).strip():
                    sectors[sym] = str(row["sector"]).strip()
            except (TypeError, ValueError):
                pass

    total_value = 0.0
    for p in stock_pos:
        sym = p["symbol"]
        px  = prices.get(sym)
        qty = p.get("qty", 0)
        if px and qty:
            total_value += px * qty

    weighted_beta = 1.0
    if total_value > 0:
        num = sum(
            prices.get(p["symbol"], 0.0) * p.get("qty", 0)
            * (betas.get(p["symbol"]) or _FALLBACK_BETAS.get(p["symbol"]) or 1.0)
            for p in stock_pos
        )
        weighted_beta = num / total_value

    from collections import defaultdict as _dd
    sector_value: dict[str, float] = _dd(float)
    for p in stock_pos:
        s  = sectors.get(p["symbol"], "")
        px = prices.get(p["symbol"], 0.0)
        if s and s.lower() != "unknown" and px:
            sector_value[s] += px * p.get("qty", 0)
    dominant_sector = (
        max(sector_value, key=lambda k: sector_value[k])
        if sector_value else "Unbekannt"
    )

    put_spreads   = [s for s in spreads if s.get("put_call") == "P"]
    n_spreads     = len(spreads)
    n_put_spreads = len(put_spreads)
    option_max_loss = sum(s["max_risk"] for s in put_spreads)
    depot_groesse   = total_value + option_max_loss

    n_short_opts = n_spreads
    if n_spreads > 3 and n_short_opts >= max(n_stocks, 1):
        portfolio_type = "Prämienverkäufer"
    elif n_stocks > n_short_opts:
        portfolio_type = "Aktien-Depot"
    else:
        portfolio_type = "Gemischt"

    # Empfohlener Basiswert
    sec_lower = dominant_sector.lower()
    recommended_hedge = "SPY / RSP"
    for key, etf in _SECTOR_TO_HEDGE.items():
        if key in sec_lower:
            recommended_hedge = etf
            break

    return {
        "total_value":       round(total_value, 2),
        "option_max_loss":   round(option_max_loss, 2),
        "depot_groesse":     round(depot_groesse, 2),
        "weighted_beta":     round(weighted_beta, 2),
        "dominant_sector":   dominant_sector,
        "portfolio_type":    portfolio_type,
        "n_spreads":         n_spreads,
        "n_put_spreads":     n_put_spreads,
        "n_stocks":          n_stocks,
        "betas":             betas,
        "prices":            prices,
        "sectors":           sectors,
        "recommended_hedge": recommended_hedge,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Eichhorn Long-Put Logik (unverändert)
# ═══════════════════════════════════════════════════════════════════════════════

def _long_put_value_at_drop(strike: float, entry_iv: float, dte: int,
                            index_price: float, drop: float) -> float:
    price_at_drop = index_price * (1 + drop)
    intrinsic  = max(strike - price_at_drop, 0.0)
    vola_bonus = index_price * abs(drop) * 0.10 if intrinsic == 0 else index_price * abs(drop) * 0.05
    return (intrinsic + vola_bonus) * 100


def _pick_long_puts(chain: pd.DataFrame, index_price: float, target_dte: int) -> list[dict]:
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
    profiles = [
        ("Teenie (Delta ~5)",   0.05, "Nur echter Crash — billigstes Lotterielos (Eichhorn-Favorit)"),
        ("OTM (Delta ~10)",     0.10, "Fängt tiefe Korrekturen, günstig"),
        ("Nah-OTM (Delta ~20)", 0.20, "Reagiert schon früh, teurer"),
    ]
    picks, used = [], set()
    for name, tgt_delta, desc in profiles:
        leg["dd"] = (leg["delta"] - tgt_delta).abs()
        row    = leg.sort_values("dd").iloc[0]
        strike = float(row["strike_price"])
        if strike in used:
            continue
        used.add(strike)
        picks.append({
            "name": name, "desc": desc, "strike": strike,
            "premium": float(row["premium"]),
            "delta": float(row["delta"]),
            "iv": float(row["iv"]) if pd.notnull(row["iv"]) else 0.0,
            "dte": dte, "expiry": str(best_exp),
            "otm_pct": (index_price - strike) / index_price * 100,
        })
    return picks


def _chart_hedge_payoff(pick: dict, n_contracts: int, index_price: float,
                        target_cover: float) -> go.Figure:
    labels  = [s[0] for s in _SCENARIOS]
    drops   = [s[1] for s in _SCENARIOS]
    payouts = [_long_put_value_at_drop(pick["strike"], pick["iv"], pick["dte"],
                                       index_price, d) * n_contracts for d in drops]
    cost = pick["premium"] * 100 * n_contracts
    fig  = go.Figure()
    fig.add_bar(name="Hedge-Auszahlung (est.)", x=labels, y=payouts, marker_color="#22c55e")
    fig.add_hline(y=cost, line_dash="dot", line_color="#ef4444",
                  annotation_text=f"Prämie ${cost:,.0f}")
    fig.add_hline(y=target_cover, line_dash="dash", line_color="#3b82f6",
                  annotation_text=f"Ziel ${target_cover:,.0f}")
    fig.update_layout(title=f"Crash-Auszahlung — {pick['name']}",
                      yaxis_title="$", plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                      font_color="#e5e7eb", height=340,
                      legend=dict(orientation="h", y=1.1))
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# VIX-Ampel
# ═══════════════════════════════════════════════════════════════════════════════

def _vix_verdict(vix: float) -> tuple[str, str]:
    if vix < 16: return ("günstig", "success")
    if vix < 22: return ("normal", "info")
    if vix < 30: return ("erhöht", "warning")
    return ("teuer – Hedge lohnt kaum", "error")


def _vix_ampel_html(vix: float | None) -> str:
    if vix is None:
        return "<span style='color:#94a3b8;'>VIX nicht verfügbar</span>"
    if vix < 15:
        color, text = "#22c55e", f"VIX {vix:.1f} — Ideal für Hedge-Aufbau"
    elif vix <= 20:
        color, text = "#f59e0b", f"VIX {vix:.1f} — Akzeptabler Einstiegszeitpunkt"
    elif vix <= 30:
        color, text = "#f97316", f"VIX {vix:.1f} — Optionen teuer, vorsichtig sein"
    else:
        color, text = "#ef4444", f"VIX {vix:.1f} — Zu teuer, warten bis VIX < 25"
    return (f"<div style='background:{color}22;border:1px solid {color}66;"
            f"border-radius:8px;padding:8px 14px;'>"
            f"<span style='color:{color};font-weight:700;'>{text}</span></div>")


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 1 — Portfolio-Analyse
# ═══════════════════════════════════════════════════════════════════════════════

def _render_portfolio_analyse(positions: list[dict], spreads: list[dict], profile: dict) -> None:
    st.markdown("### Portfolio-Profil")

    put_spreads = [s for s in spreads if s.get("put_call") == "P"]
    call_spreads = [s for s in spreads if s.get("put_call") == "C"]
    total_put_risk = sum(s["max_risk"] for s in put_spreads)

    c1, c2, c3 = st.columns(3)
    c1.metric("Depotgröße (geschätzt)",   f"${profile['depot_groesse']:,.0f}")
    c2.metric("Portfolio-Beta",            f"{profile['weighted_beta']:.2f}")
    c3.metric("Dominanter Sektor",         profile["dominant_sector"])

    c4, c5, c6 = st.columns(3)
    c4.metric("Portfolio-Typ",            profile["portfolio_type"])
    c5.metric("Offene Spreads (gesamt)",  profile["n_spreads"])
    c6.metric("davon Put-Spreads",        profile["n_put_spreads"])

    st.divider()
    st.markdown("#### Crash-Risiko-Schätzung bei −20% Marktfall")

    beta_loss = profile["total_value"] * profile["weighted_beta"] * 0.20
    total_exp = beta_loss + total_put_risk

    kc1, kc2, kc3 = st.columns(3)
    kc1.markdown(
        f"<div style='background:#7f1d1d22;border:2px solid #ef4444;border-radius:10px;"
        f"padding:16px;text-align:center;'>"
        f"<div style='color:#9ca3af;font-size:12px;font-weight:600;'>PUT-SPREAD MAX-LOSS</div>"
        f"<div style='color:#ef4444;font-size:28px;font-weight:800;'>${total_put_risk:,.0f}</div>"
        f"<div style='color:#fca5a5;font-size:12px;'>Worst Case alle Spreads</div></div>",
        unsafe_allow_html=True,
    )
    kc2.markdown(
        f"<div style='background:#78350f22;border:2px solid #f59e0b;border-radius:10px;"
        f"padding:16px;text-align:center;'>"
        f"<div style='color:#9ca3af;font-size:12px;font-weight:600;'>AKTIEN-VERLUST (β×−20%)</div>"
        f"<div style='color:#f59e0b;font-size:28px;font-weight:800;'>${beta_loss:,.0f}</div>"
        f"<div style='color:#fcd34d;font-size:12px;'>Beta {profile['weighted_beta']:.2f} × ${profile['total_value']:,.0f}</div></div>",
        unsafe_allow_html=True,
    )
    kc3.markdown(
        f"<div style='background:#14532d22;border:2px solid #22c55e;border-radius:10px;"
        f"padding:16px;text-align:center;'>"
        f"<div style='color:#9ca3af;font-size:12px;font-weight:600;'>GESAMTEXPOSURE</div>"
        f"<div style='color:#22c55e;font-size:28px;font-weight:800;'>${total_exp:,.0f}</div>"
        f"<div style='color:#86efac;font-size:12px;'>Spreads + Aktien kombiniert</div></div>",
        unsafe_allow_html=True,
    )

    st.divider()
    st.markdown(
        f"**Empfohlener Hedge-Basiswert:** `{profile['recommended_hedge']}`  \n"
        f"*Äpfel mit Birnen hedgen ist riskant — am besten einen Index nehmen der stark mit "
        f"dem Portfolio korreliert.*"
    )
    if call_spreads:
        st.caption(
            f"{len(call_spreads)} Bear Call Spread(s) erkannt — bei einem Crash KEIN Problem "
            f"(Calls profitieren von fallenden Kursen). Nur die Put-Spreads brauchen Absicherung."
        )

    if spreads:
        with st.expander(f"Alle {len(spreads)} Spreads im Detail", expanded=False):
            rows = []
            for s in sorted(spreads, key=lambda x: x["max_risk"], reverse=True):
                rows.append({
                    "Symbol":      s["symbol"],
                    "Typ":         (
                        ("Put-Spread" if s["put_call"] == "P" else "Call-Spread")
                        if s.get("kind") == "spread"
                        else ("Naked Short Put" if s["put_call"] == "P" else "Naked Short Call")
                    ),
                    "Short Strike": f"${s['short_strike']:.0f}",
                    "Long Strike":  f"${s['long_strike']:.0f}",
                    "Breite":       f"${s['width']:.0f}",
                    "Max-Risiko":   f"${s['max_risk']:,.0f}",
                    "Art":          s.get("kind", "spread"),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Kanarienvögel
# ═══════════════════════════════════════════════════════════════════════════════

def _render_kanarienvoegel() -> None:
    st.markdown("### Kanarienvögel in der Kohlemine")
    st.caption(
        "Diese Indikatoren fungieren als Frühwarnsystem. Kein Einzelindikator entscheidet — "
        "immer das Gesamtbild betrachten. *(Eric Ludwig, Kapitel 'Kanarienvögel')*"
    )

    vix   = _phc_load_vix()
    vix3m = _phc_load_vix3m()

    red_count = 0

    # ── Indikator 1: VIX vs VIX3M ────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**Indikator 1 — VIX vs. VIX3M (Terminkurve)**")
        col1, col2 = st.columns(2)
        with col1:
            if vix is not None:
                st.metric("VIX (30 Tage)", f"{vix:.1f}")
            else:
                st.metric("VIX", "N/A")
        with col2:
            if vix3m is not None:
                st.metric("VIX3M (90 Tage)", f"{vix3m:.1f}")
            else:
                st.metric("VIX3M", "N/A")

        if vix is not None and vix3m is not None:
            if vix >= vix3m:
                red_count += 1
                st.error(f"VIX ({vix:.1f}) ≥ VIX3M ({vix3m:.1f}) — Kurzfristige Unsicherheit größer als langfristige. **Hedging aufstocken!**")
            else:
                st.success(f"Normal: VIX ({vix:.1f}) < VIX3M ({vix3m:.1f}) — Terminkurve in Contango")
        elif vix is not None:
            if vix > 20:
                red_count += 1
                st.warning(f"VIX3M nicht verfügbar. VIX {vix:.1f} erhöht — Vorsicht.")
            else:
                st.info(f"VIX3M nicht in DB. VIX = {vix:.1f}")
        st.caption("Normal: VIX < VIX3M (Märkte erwarten langfristig mehr Unsicherheit). Umkehr = Panik-Signal.")

    # ── Indikator 2: VIX-Level für Einstieg ──────────────────────────────────
    with st.container(border=True):
        st.markdown("**Indikator 2 — VIX-Level für Hedge-Einstieg**")
        st.markdown(_vix_ampel_html(vix), unsafe_allow_html=True)
        if vix is not None and vix > 20:
            red_count += 1
        st.caption("Eichhorn & Ludwig: Hedges NUR bei VIX < 20 aufbauen. Bei VIX > 30 ist die Versicherung zu teuer.")

    # ── Indikator 3: Put/Call Ratio ───────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**Indikator 3 — Put/Call Ratio**")
        st.info(
            "Put/Call Ratio ist nicht direkt in der DB verfügbar. "
            "Warnschwelle: **PCR < 0.8** = zu wenig Hedging am Markt (Euphorie-Warnung)."
        )
        col_pcr, col_link = st.columns([3, 1])
        with col_pcr:
            pcr_manual = st.number_input(
                "PCR manuell eingeben (von CBOE.com)",
                min_value=0.0, max_value=5.0, value=0.0, step=0.01,
                format="%.2f", key="phc_pcr_manual",
                label_visibility="collapsed",
            )
        with col_link:
            st.link_button("CBOE PCR", "https://www.cboe.com/us/options/market_statistics/daily/")
        if pcr_manual > 0:
            if pcr_manual < 0.8:
                red_count += 1
                st.error(f"PCR {pcr_manual:.2f} < 0.8 — Zu wenig Hedging am Markt. **Euphorie-Warnung!**")
            elif pcr_manual <= 1.2:
                st.success(f"PCR {pcr_manual:.2f} — Normales Niveau")
            else:
                st.warning(f"PCR {pcr_manual:.2f} > 1.2 — Erhöhte Absicherung im Markt (oft Bodenbildung)")
        st.caption("Sehr niedriger Wert = Marktteilnehmer hedgen kaum = mögliches Warnsignal für Überhitzung.")

    # ── Indikator 4: Hindenburg Omen ──────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**Indikator 4 — Hindenburg Omen**")
        hindenburg = st.checkbox(
            "Hindenburg Omen aktuell aktiv? (auf TradingView prüfen)",
            key="phc_hindenburg",
        )
        st.link_button("TradingView — Hindenburg Omen prüfen",
                       "https://www.tradingview.com/scripts/hindenburgomen/")
        if hindenburg:
            red_count += 1
            st.error("Hindenburg Omen aktiv — erhöhte Crash-Wahrscheinlichkeit!")
        with st.expander("Was ist das Hindenburg Omen?"):
            st.markdown("""
**4 Kriterien müssen gleichzeitig erfüllt sein:**
1. S&P 500 liegt über seinem 50-Tage-Durchschnitt
2. Neue 52-Wochen-Hochs UND neue 52-Wochen-Tiefs machen jeweils mehr als **2,2%** aller Aktien an der NYSE aus
3. **McClellan-Oszillator ist negativ**
4. Neue 52-Wochen-Hochs sind NICHT mehr als doppelt so groß wie neue 52-Wochen-Tiefs

**Historische Signale (aus dem Buch):** Juli 2019, September 2018 (5× in 2 Wochen), Februar 2018, 30.01.2020 und 10.02.2020 vor dem Covid-Crash.

Mehrere Signale in 4 Wochen = stärkere Aussagekraft.
""")

    # ── Gesamtbild ────────────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Gesamtbild")
    if red_count >= 2:
        st.error(f"**{red_count} Warnsignale aktiv** — Hedging-Positionen aufstocken! Mehrere Indikatoren zeigen erhöhtes Risiko.")
    elif red_count == 1:
        st.warning(f"**1 Warnsignal aktiv** — Erhöhte Aufmerksamkeit. Hedges überprüfen.")
    else:
        st.success("**Keine Warnsignale** — Ruhige Marktlage. Guter Zeitpunkt für Hedge-Aufbau bei niedrigem VIX.")

    with st.expander("Wie kombiniere ich die Indikatoren? (aus dem Buch)"):
        st.markdown("""
**Kombinations-Logik nach Eric Ludwig:**
- **Hindenburg Omen + RSI-Divergenz + Sentiment-Überstreckung gleichzeitig** = höchste Warnstufe → Hedging-Positionen vergrößern
- **VIX > VIX3M** allein = aufstocken, aber nicht Panik
- **Put/Call Ratio < 0.8 über längere Zeit** = Märkte zu sorglos — typisches Vorzeichen

**Wichtig:** Crash-Propheten ignorieren. Eigene Indikatoren-Analyse betreiben.
""")


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 3 — Strategie-Wahl
# ═══════════════════════════════════════════════════════════════════════════════

def _render_strategie_wahl(profile: dict) -> None:
    st.markdown("### Welche Strategie passt zu dir?")

    # Auto-Empfehlung
    pt   = profile["portfolio_type"]
    beta = profile["weighted_beta"]
    n_sp = profile["n_spreads"]

    if pt == "Prämienverkäufer" and n_sp > 10:
        rec_primary   = "Grizzly-Hedge"
        rec_secondary = "VXX Time-Straddle"
        rec_why = f"Als Prämienverkäufer mit {n_sp} Spreads finanziert der Grizzly-Hedge sich selbst. VXX Time-Straddle als dauerhafter Crash-Schutz obendrauf."
    elif pt == "Prämienverkäufer":
        rec_primary   = "Bear Put Spread"
        rec_secondary = "Grizzly-Hedge"
        rec_why = f"Bear Put Spread als kostengünstige Absicherung deiner Spread-Positionen."
    elif beta > 1.5:
        rec_primary   = "VXX Time-Straddle"
        rec_secondary = "Zorro-Hedge"
        rec_why = f"Portfolio-Beta {beta:.2f} ist hoch — VXX Time-Straddle schützt am stärksten bei Crash."
    elif pt == "Aktien-Depot":
        rec_primary   = "Collar"
        rec_secondary = "Bear Put Spread"
        rec_why = f"Collar für Einzelpositionen (kostenlos möglich), Bear Put Spread für das Gesamtdepot."
    else:
        rec_primary   = "Bear Put Spread"
        rec_secondary = "Grizzly-Hedge"
        rec_why = "Ausgewogene Wahl für gemischtes Portfolio."

    with st.container(border=True):
        st.markdown(
            f"**Auto-Empfehlung für dein Portfolio ({pt}, Beta {beta:.2f}, {n_sp} Spreads):**  \n"
            f"→ **{rec_primary}** als Basis  \n"
            f"→ **{rec_secondary}** als Ergänzung  \n"
            f"*{rec_why}*"
        )

    st.markdown("#### Alle Strategien aus dem Buch")
    st.caption("Persönliche Abwehrkette des Autors — von oben nach unten: bevorzugt → weniger bevorzugt")

    for strat in _STRATEGIES:
        is_rec = strat["name"] in (rec_primary, rec_secondary)
        title  = f"{'' if is_rec else ''}{strat['name']}  —  {strat['badge']}"
        with st.expander(title, expanded=is_rec):
            col_l, col_r = st.columns([3, 1])
            with col_l:
                st.markdown(f"**{strat['short']}**")
                st.markdown(f"*{strat['book']}*")
                st.markdown("**Konstruktion:**")
                st.code(strat["construction"], language=None)
                st.markdown(f"**Wann einsetzen:** {strat['when']}")
                st.markdown(f"**Kosten:** {strat['cost']}")
            with col_r:
                st.markdown(
                    f"<div style='background:{strat['badge_color']}22;"
                    f"border:2px solid {strat['badge_color']};border-radius:10px;"
                    f"padding:12px;text-align:center;margin-top:8px;'>"
                    f"<div style='color:{strat['badge_color']};font-weight:700;font-size:14px;'>"
                    f"{strat['cost_label']}</div></div>",
                    unsafe_allow_html=True,
                )
                if st.button(
                    "Konfigurieren",
                    key=f"phc_strat_btn_{strat['key']}",
                    use_container_width=True,
                ):
                    st.session_state["phc_selected_strategy"] = strat["name"]
                    st.info(f"Wechsle zum Tab **Konkrete Absicherung** um {strat['name']} zu konfigurieren.")


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 4 — Konkrete Absicherung
# ═══════════════════════════════════════════════════════════════════════════════

def _render_konkrete_absicherung(spreads: list[dict], profile: dict) -> None:
    st.markdown("### Konkrete Absicherung")

    put_spreads    = [s for s in spreads if s.get("put_call") == "P"]
    total_put_risk = sum(s["max_risk"] for s in put_spreads)

    # Strategie-Selektor
    strat_names = [s["name"] for s in _STRATEGIES]
    default_strat = st.session_state.get("phc_selected_strategy", "Long Put (Eichhorn)")
    # Long Put ist kein Eintrag in _STRATEGIES — separat
    all_options = ["Long Put — Eichhorn (Teenie OTM)"] + strat_names
    default_idx = 0
    if default_strat in all_options:
        default_idx = all_options.index(default_strat)
    elif default_strat in strat_names:
        default_idx = strat_names.index(default_strat) + 1

    selected = st.selectbox(
        "Welche Strategie konfigurieren?",
        all_options,
        index=default_idx,
        key="phc_strat_select",
    )

    # Parameter (für alle relevant)
    with st.container(border=True):
        st.markdown("**Parameter**")
        p1, p2, p3 = st.columns(3)
        with p1:
            cover_pct = st.slider(
                "Absicherungsgrad", 10, 100, 50, 5,
                format="%d%%", key="phc_cover_pct",
                help="Anteil des Put-Downside-Risikos absichern",
            ) / 100
        with p2:
            dte_hedge = st.select_slider(
                "Laufzeit (DTE)", [30, 45, 60, 90, 120, 150],
                value=120, key="phc_dte",
                help="Ludwig: ≥120 DTE für niedrigen Theta-Verlust",
            )
        with p3:
            hedge_etf = st.selectbox(
                "Basiswert",
                ["SPY", "QQQ"],
                format_func=lambda k: f"{k} ({_HEDGE_ETFS.get(k, k)})",
                key="phc_etf",
                help=f"Auto-Empfehlung: {profile['recommended_hedge']}",
            )

    index_price  = _fetch_price(hedge_etf, 560.0 if hedge_etf == "SPY" else 480.0)
    vix          = _phc_load_vix()
    target_cover = total_put_risk * cover_pct

    # Metriken
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Put-Spread Max-Risiko", f"${total_put_risk:,.0f}")
    m2.metric(f"Abzusichern ({cover_pct*100:.0f}%)", f"${target_cover:,.0f}")
    m3.metric(f"{hedge_etf} Kurs", f"${index_price:.2f}")
    if vix:
        vt, vc = _vix_verdict(vix)
        m4.metric("VIX", f"{vix:.1f}", delta=vt,
                  delta_color="normal" if vc in ("success", "info") else "inverse")

    st.divider()

    # ── Long Put (Eichhorn) ───────────────────────────────────────────────────
    if selected.startswith("Long Put"):
        chain = _fetch_put_chain(hedge_etf, dte_hedge - 15, dte_hedge + 20)
        picks = _pick_long_puts(chain, index_price, dte_hedge)
        if not picks:
            st.warning(f"Keine {hedge_etf}-Put-Kette für DTE ≈ {dte_hedge} in DB. DTE anpassen.")
            return
        st.caption(
            f"{hedge_etf} ${index_price:.2f} · Verfall {picks[0]['expiry']} ({picks[0]['dte']} DTE) · "
            f"**Reiner Long Put** — Max-Verlust = Prämie."
        )
        for pick in picks:
            payout_20   = _long_put_value_at_drop(pick["strike"], pick["iv"], pick["dte"], index_price, -0.20)
            n_contracts = max(1, round(target_cover / payout_20)) if payout_20 > 0 else 1
            total_cost  = pick["premium"] * 100 * n_contracts
            cost_pct    = total_cost / max(total_put_risk, 1) * 100
            with st.container(border=True):
                st.markdown(f"**{pick['name']}** — {pick['desc']}")
                a1, a2, a3, a4 = st.columns(4)
                a1.metric("Put kaufen", f"${pick['strike']:.0f}", f"{pick['otm_pct']:.1f}% OTM")
                a2.metric("Delta", f"{pick['delta']:.3f}")
                a3.metric("Kontrakte", n_contracts)
                a4.metric("Prämie gesamt", f"${total_cost:,.0f}")
                st.code(
                    f"BUY {n_contracts}× {hedge_etf} PUT {pick['strike']:.0f} "
                    f"EXP {pick['expiry']}  @ ~${pick['premium']:.2f}/Kontrakt",
                    language=None,
                )
                tbl = []
                for label, drop in _SCENARIOS:
                    pay = _long_put_value_at_drop(pick["strike"], pick["iv"], pick["dte"], index_price, drop) * n_contracts
                    tbl.append({"Szenario": label, "Auszahlung": f"${pay:,.0f}",
                                "Ziel": f"${target_cover:,.0f}",
                                "Deckung %": f"{pay/max(target_cover,1)*100:.0f}%",
                                "Netto": f"${pay-total_cost:+,.0f}"})
                st.dataframe(pd.DataFrame(tbl), hide_index=True, use_container_width=True)
                st.caption(f"Kosten: ${total_cost:,.0f} = {cost_pct:.1f}% des Put-Risikos · {dte_hedge} Monate Schutz")
                st.plotly_chart(_chart_hedge_payoff(pick, n_contracts, index_price, target_cover),
                                use_container_width=True)

    # ── Bear Put Spread / Zorro-Hedge ─────────────────────────────────────────
    elif selected in ("Bear Put Spread", "Zorro-Hedge"):
        factor = 2 if selected == "Zorro-Hedge" else 1
        if factor == 2:
            st.info("**Zorro-Hedge:** 2× Kontrakte des Bear Put Spreads — das Zick-Zack-Profil schützt stärker.")
        chain = _phc_load_bear_put_chain(hedge_etf, dte_hedge - 15, dte_hedge + 20)
        if chain.empty:
            st.warning(f"Keine {hedge_etf} Put-Kette in DB. DTE anpassen.")
            return
        chain = chain.copy()
        for col in ["strike_price", "premium", "delta", "dte"]:
            chain[col] = pd.to_numeric(chain[col], errors="coerce")
        chain = chain.dropna(subset=["strike_price", "premium", "delta"])
        chain["dte_dist"] = (chain["dte"] - dte_hedge).abs()
        best_exp = chain.sort_values("dte_dist").iloc[0]["expiration_date"]
        leg = chain[chain["expiration_date"] == best_exp].copy()
        if len(leg) < 2:
            st.warning("Zu wenige Strikes in der Put-Kette.")
            return
        leg = leg.sort_values("strike_price", ascending=False)
        candidates = []
        for i in range(len(leg) - 1):
            buy_row  = leg.iloc[i]
            sell_row = leg.iloc[i + 1]
            buy_s    = float(buy_row["strike_price"])
            sell_s   = float(sell_row["strike_price"])
            if buy_s <= index_price * 0.85:
                break
            cost = (float(buy_row["premium"]) - float(sell_row["premium"])) * 100 * factor
            width = (buy_s - sell_s) * factor
            max_gain = width * 100 - cost
            if max_gain <= 0 or cost <= 0:
                continue
            cost_ratio = cost / max_gain * 100
            if 8 <= cost_ratio <= 25:
                otm = (index_price - buy_s) / index_price * 100
                candidates.append({
                    "Buy Put":    f"${buy_s:.0f}",
                    "Sell Put":   f"${sell_s:.0f}",
                    "Kosten $":   round(cost, 0),
                    "Max-Gewinn $": round(max_gain, 0),
                    "Kosten %":   round(cost_ratio, 1),
                    "OTM %":      round(otm, 1),
                    "DTE":        int(buy_row["dte"]),
                })
            if len(candidates) >= 3:
                break
        if not candidates:
            st.info("Keine passenden Bear Put Spread Kandidaten im Bereich 8–25% Kosten/Max-Gewinn.")
            return
        st.caption(
            f"{hedge_etf} ${index_price:.2f} · Verfall {best_exp} · "
            f"Faustregel: Kosten = 12–20% des Max-Gewinns"
        )
        df_cand = pd.DataFrame(candidates)
        st.dataframe(
            df_cand.style.format({
                "Kosten $": "${:.0f}", "Max-Gewinn $": "${:.0f}",
                "Kosten %": "{:.1f}%", "OTM %": "{:.1f}%",
            }),
            hide_index=True, use_container_width=True,
        )
        st.caption(
            f"Stop-Loss bei 50% der Kosten empfohlen. "
            f"{'Zorro: beide Kontrakte mit ×2 handeln.' if factor == 2 else ''}"
        )

    # ── Grizzly-Hedge ─────────────────────────────────────────────────────────
    elif selected == "Grizzly-Hedge":
        st.info(
            "**Grizzly = Bear Put Spread + Short Call.** "
            "Wähle zuerst deinen Bear Put Spread (aus der Tabelle unten), "
            "dann einen Short Call dessen Prämie ≥ 50% der Spread-Kosten deckt."
        )
        chain = _phc_load_bear_put_chain(hedge_etf, dte_hedge - 15, dte_hedge + 20)
        if not chain.empty:
            chain = chain.copy()
            for col in ["strike_price", "premium", "delta", "dte"]:
                chain[col] = pd.to_numeric(chain[col], errors="coerce")
            chain = chain.dropna(subset=["strike_price", "premium", "delta"])
            chain["dte_dist"] = (chain["dte"] - dte_hedge).abs()
            best_exp = chain.sort_values("dte_dist").iloc[0]["expiration_date"]
            leg = chain[chain["expiration_date"] == best_exp].copy()
            leg = leg.sort_values("strike_price", ascending=False)
            rows = []
            for i in range(min(len(leg) - 1, 5)):
                b  = leg.iloc[i]
                s  = leg.iloc[i + 1]
                bs = float(b["strike_price"])
                ss = float(s["strike_price"])
                if bs <= index_price * 0.85:
                    break
                cost     = (float(b["premium"]) - float(s["premium"])) * 100
                max_gain = (bs - ss) * 100 - cost
                if max_gain > 0 and cost > 0:
                    min_call_prem = cost * 0.50 / 100
                    rows.append({
                        "Bear Put Spread":    f"Long {bs:.0f} / Short {ss:.0f}",
                        "Spread-Kosten $":    round(cost, 0),
                        "Call-Prämie ≥":      f"${min_call_prem:.2f} nötig",
                        "Max-Gewinn $":       round(max_gain, 0),
                    })
            if rows:
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
                st.caption(
                    "Short Call: Basispreis knapp über letztem relativem Hoch, "
                    "Delta ~16 oder Projektion der Ø-Tagesrendite über 100 Tage. "
                    "MAX 1 Call pro 100 Aktien!"
                )

    # ── VXX Time-Straddle ─────────────────────────────────────────────────────
    elif selected == "VXX Time-Straddle":
        st.markdown("#### Die 6 Regelwerk-Regeln (Eric Ludwig)")
        rules = [
            ("Regel 1 — Eröffnung", "Nur wenn VIX < 25. Eröffnung Montag oder Dienstag. 3 Straddles (je 1 Put + 1 Call ATM, ≥120 DTE) + 1 Weekly Short Call."),
            ("Regel 2 — Neuzentrierung (alle 6 Wochen)", "Straddles glattstellen & neu eröffnen wenn: VXX > 10% vom Basispreis entfernt ODER Restlaufzeit < 60 Tage. Neue Straddles immer ≥120 DTE."),
            ("Regel 3 — Weekly Call-Management (Do/Fr)", "VXX unter Call-Strike → verfallen lassen, neuen ATM-Call für Folgewoche eröffnen. VXX über Call-Strike → Call rollen (Prämie des neuen Calls ≥ Schließungskosten)."),
            ("Regel 4 — VIX > 30", "Keine Neuzentrierung! Straddle laufen lassen. Short Call weiter rollen. Tritt historisch nur an ~9% aller Handelstage auf."),
            ("Regel 5 — Ausstieg", "Glattstellung ALLER Positionen am Tag nach: (1) VIX hat >30 überschritten UND (2) MACD auf VIX generiert Verkaufssignal (Histogramm fällt unter 0)."),
            ("Regel 6 — Wiedereinstieg", "Erst wenn VIX wieder < 25 (= Regel 1)."),
        ]
        for title, text in rules:
            with st.expander(title):
                st.markdown(text)

        st.divider()
        st.markdown("#### Sizing-Richtwerte (aus dem Buch)")
        sizing_data = [
            {"Depotgröße": "$30.000", "Straddle-Kosten ~$750": "4 Straddles + 1 Call", "Straddle-Kosten ~$1.500": "2 Straddles + 1 Call"},
            {"Depotgröße": "$50.000", "Straddle-Kosten ~$750": "6 Straddles + 2 Calls", "Straddle-Kosten ~$1.500": "3 Straddles + 1 Call"},
            {"Depotgröße": "$100.000","Straddle-Kosten ~$750": "12 Straddles + 4 Calls","Straddle-Kosten ~$1.500": "6 Straddles + 2 Calls"},
        ]
        st.dataframe(pd.DataFrame(sizing_data), hide_index=True, use_container_width=True)
        st.caption(
            "Verhältnis immer 3 Straddles : 1 Short Call. "
            "Emittentenrisiko beachten: VXX von Barclays, UVXY von ProShares."
        )
        if vix and vix >= 25:
            st.warning(f"VIX = {vix:.1f} ≥ 25 — Regel 1 verletzt. **Jetzt NICHT einsteigen.**")
        elif vix:
            st.success(f"VIX = {vix:.1f} < 25 — Einstieg möglich (Regel 1 erfüllt).")

    # ── Collar ────────────────────────────────────────────────────────────────
    elif selected == "Collar / Open Collar":
        st.info(
            "Collar ist für **einzelne Aktienpositionen** — gib das Symbol ein "
            "für das du einen Collar aufsetzen möchtest."
        )
        col_sym = st.text_input("Aktien-Symbol", value="AAPL", key="phc_collar_sym").upper().strip()
        if col_sym:
            col_price = _fetch_price(col_sym, 0.0)
            if col_price > 0:
                st.metric(f"{col_sym} Kurs", f"${col_price:.2f}")
                st.markdown(f"""
**Collar-Konstruktion für {col_sym} @ ${col_price:.2f}:**
- **Long Put** (OTM, ca. 5% unter Kurs): Strike ~${col_price*0.95:.0f}
- **Short Call** (OTM, ca. 5% über Kurs): Strike ~${col_price*1.05:.0f}
- Gleiche Laufzeit, idealerweise Zero-Cost

**Maximaler Verlust:** `(Aktienkurs - Put-Strike) × 100 - Prämie`
**Maximaler Gewinn:** `(Call-Strike - Aktienkurs) × 100 + Prämie`
**1 Call pro 100 Aktien — niemals überhedgen!**
""")
            else:
                st.warning(f"Kein Kurs für {col_sym} in DB gefunden.")

    # ── Butterfly-Hedge ───────────────────────────────────────────────────────
    elif selected == "Butterfly-Hedge":
        st.warning("**Nur für ~10% Korrektur geeignet — KEIN Schutz bei echtem Crash!**")
        otm_a  = index_price * 0.95
        otm_b  = index_price * 0.88
        otm_c  = index_price * 0.81
        st.markdown(f"""
**Butterfly-Hedge auf {hedge_etf} @ ${index_price:.2f}:**

| Leg | Aktion | Strike | Stück |
|-----|--------|--------|-------|
| Long Put A | Kaufen | ${otm_a:.0f} (~5% OTM) | 1× |
| Short Put B | Verkaufen | ${otm_b:.0f} (~12% OTM) | 2× |
| Long Put C | Kaufen | ${otm_c:.0f} (~19% OTM) | 1× |

**Alle gleiche Laufzeit, mind. 45 Tage.**
Max-Gewinn wenn {hedge_etf} genau bei ${otm_b:.0f} am Verfallstag.
**Gewinn-Exit: 30% des Max-Gewinns. Stop-Loss: 50% der Kosten. IMMER vor Verfall schließen!**
""")

    # ── Protective Put ────────────────────────────────────────────────────────
    elif selected == "Protective Put":
        st.error(
            "**Warnung — Pyrrhussieg-Gefahr!** Der Protective Put kostet über die Zeit sehr viel. "
            "Langfristig fressen die kumulierten Prämienkosten die Schutzwirkung auf. "
            "Nur bei VIX < 20 und als kurzfristige Maßnahme sinnvoll."
        )
        if vix and vix < 20:
            st.success(f"VIX = {vix:.1f} < 20 — Einstieg akzeptabel.")
        elif vix:
            st.warning(f"VIX = {vix:.1f} ≥ 20 — Warten auf VIX < 20.")
        st.markdown(f"""
**Protective Put auf {hedge_etf} @ ${index_price:.2f}:**
- Long Put ATM oder leicht OTM (~2–5% unter Kurs)
- **Mindestens 6 Monate Laufzeit** (sonst zu schneller Zeitwertverfall)
- 1 Kontrakt pro 100 Anteile/Aktien
- Stop-Loss bei 50% der Prämie
- Bei Restlaufzeit < 90 Tage: rollen
""")


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 5 — Ausstiegs-Timing
# ═══════════════════════════════════════════════════════════════════════════════

def _render_ausstieg() -> None:
    st.markdown("### Das Licht am Ende des Tunnels")
    st.caption(
        "Wann Hedging-Positionen reduzieren? Das Doppelsignal aus Eric Ludwigs Buch "
        "*(Kapitel 'Das Licht am Ende des Tunnels')*"
    )

    vix = _phc_load_vix()

    # ── Das Doppelsignal ──────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**Das Doppelsignal — beide Bedingungen müssen erfüllt sein:**")
        col1, col2 = st.columns(2)
        with col1:
            vix_hoch30 = st.checkbox(
                "Bedingung 1: VIX hat Hoch > 30 erreicht?",
                key="phc_vix_hoch30",
                help="Der VIX muss zuvor über 30 geschossen sein (Panik war am Markt)",
            )
        with col2:
            macd_signal = st.checkbox(
                "Bedingung 2: MACD auf VIX zeigt Verkaufssignal?",
                key="phc_macd_signal",
                help="MACD-Histogramm auf dem VIX fällt unter 0 (nach dem Spike über 30)",
            )

        if vix:
            st.markdown(_vix_ampel_html(vix), unsafe_allow_html=True)

        st.divider()
        if vix_hoch30 and macd_signal:
            st.success(
                "**BEIDE Bedingungen erfüllt — Hedges jetzt reduzieren!**  \n"
                "Gewinne aus Hedging-Positionen mitnehmen. "
                "Nicht ALLE Hedges auflösen — kleine Restabsicherung (Bear Put Spread oder Zorro-Hedge) behalten."
            )
        elif vix_hoch30 and not macd_signal:
            st.warning(
                "**Bedingung 1 erfüllt — auf MACD-Signal warten.**  \n"
                "VIX war über 30. Noch kein MACD-Verkaufssignal. Hedges laufen lassen."
            )
        elif not vix_hoch30 and macd_signal:
            st.info(
                "MACD-Signal aktiv, aber VIX hat noch kein Hoch > 30 gebildet.  \n"
                "MACD-Signal nur relevant wenn es von einem Niveau ÜBER 30 kommt."
            )
        else:
            st.info("Noch kein Ausstiegssignal. Hedging-Positionen beibehalten.")

        st.link_button(
            "VIX MACD auf TradingView prüfen",
            "https://www.tradingview.com/chart/?symbol=CBOE%3AVIX",
        )

    st.caption("MACD-Konfiguration: 12/26 EMA + 9-Tage-Signallinie (Standardkonfiguration)")

    # ── Historische Signale ───────────────────────────────────────────────────
    st.markdown("#### Historische Ausstiegssignale (aus dem Buch)")
    hist = pd.DataFrame([
        {"Ereignis": "COVID-Crash 2020",    "Signal-Datum": "24.03.2020", "Methode": "MACD (23.03.2020 VIX-MA)", "Bemerkung": "Effektiv — Hedge-Gewinne gesichert"},
        {"Ereignis": "Crash Ende 2018",     "Signal-Datum": "02.01.2019", "Methode": "MACD",                     "Bemerkung": "Korrekt"},
        {"Ereignis": "Korrektur Feb 2018",  "Signal-Datum": "14.02.2018", "Methode": "MACD",                     "Bemerkung": "Korrekt"},
        {"Ereignis": "Korrektur Sommer 2015","Signal-Datum":"03.09.2015", "Methode": "MACD",                     "Bemerkung": "Korrekt"},
        {"Ereignis": "Finanzkrise 2008",    "Signal-Datum": "20.10.2008", "Methode": "MACD",                     "Bemerkung": "Zu früh — S&P 500 fiel danach nochmals −30%"},
    ])
    st.dataframe(hist, hide_index=True, use_container_width=True)
    st.caption(
        "Einschränkung: Bei der Finanzkrise 2008 kam das Signal zu früh (erster Boden, nicht der finale). "
        "Deshalb: nach Ausstieg NICHT alle Hedges auflösen — kleine Restabsicherung behalten."
    )

    # ── Nach dem Ausstieg ─────────────────────────────────────────────────────
    st.markdown("#### Nach dem Ausstieg — was dann?")
    with st.container(border=True):
        st.markdown("""
1. **Nicht alle Hedges komplett auflösen** — Bear Put Spread oder Zorro-Hedge als Restabsicherung behalten
2. **Wiedereinstieg VXX Time-Straddle:** Erst wenn VIX wieder < 25 (Regel 1)
3. **Licht am Ende des Tunnels ≠ alles vorbei** — manche Crashs haben mehrere Boden (2008!)

*"Das Bessere ist der Feind des Guten." (Voltaire) — Ein gut genugter Ausstieg ist besser als der perfekte.*
""")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    st.title("Portfolio Hedge Calculator")
    st.caption(
        "Portfolio analysieren → Frühwarnzeichen prüfen → passende Strategie wählen → "
        "konkrete Kontrakte finden  ·  *Basierend auf Eric Ludwig: Hedging mit Optionen*"
    )

    # ── CSV Upload (vor den Tabs) ─────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**Portfolio laden — IBKR / CapTrader CSV**")
        st.caption("Flex Query Position Report oder Trades_Report")
        uploaded = st.file_uploader(
            "CSV hochladen", type=["csv"],
            key="phc_csv", label_visibility="collapsed",
        )
        if uploaded:
            content = uploaded.read().decode("utf-8", errors="ignore")
            positions, spreads = _parse_csv_full(content)
            if spreads:
                st.session_state["phc_positions"] = positions
                st.session_state["phc_spreads"]   = spreads
                syms = sorted({p["symbol"] for p in positions or spreads})
                st.success(
                    f"{len(spreads)} Spreads erkannt · "
                    f"{len([p for p in positions if p.get('type')=='stock'])} Aktien · "
                    f"Symbole: {', '.join(syms[:10])}{'...' if len(syms) > 10 else ''}"
                )
            else:
                st.error(
                    "Keine Positionen erkannt. Unterstützte Formate: "
                    "Flex Query Position Report (ClientAccountID-Format) oder Trades_Report."
                )

    positions: list[dict] = st.session_state.get("phc_positions", [])
    spreads:   list[dict] = st.session_state.get("phc_spreads",   [])

    if not spreads and not positions:
        st.info("Bitte CSV hochladen um fortzufahren.")
        # Tabs trotzdem anzeigen (Kanarienvögel + Ausstieg brauchen kein Portfolio)
        tab_k, tab_a = st.tabs(["Kanarienvögel", "Ausstiegs-Timing"])
        with tab_k:
            _render_kanarienvoegel()
        with tab_a:
            _render_ausstieg()
        return

    # Portfolio-Profil berechnen (wird von mehreren Tabs genutzt)
    profile = _phc_portfolio_profile(positions, spreads)

    # ── 5 Tabs ────────────────────────────────────────────────────────────────
    tab_analyse, tab_kana, tab_strat, tab_konkret, tab_exit = st.tabs([
        "Portfolio-Analyse",
        "Kanarienvögel",
        "Strategie-Wahl",
        "Konkrete Absicherung",
        "Ausstiegs-Timing",
    ])

    with tab_analyse:
        _render_portfolio_analyse(positions, spreads, profile)

    with tab_kana:
        _render_kanarienvoegel()

    with tab_strat:
        _render_strategie_wahl(profile)

    with tab_konkret:
        _render_konkrete_absicherung(spreads, profile)

    with tab_exit:
        _render_ausstieg()


if __name__ == "__main__":
    main()
