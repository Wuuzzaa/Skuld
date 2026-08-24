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
    Format: ClientAccountID, Symbol, Quantity, MarkPrice, PositionValue,
            CostBasisPrice, CostBasisMoney, FifoPnlUnrealized, CurrencyPrimary, AssetClass, ...
    Direkte offene Positionen — kein Netting nötig.
    Gibt pro Position auch CostBasisPrice + MarkPrice zurück (für Prämienberechnung).
    """
    positions = []
    reader = csv.reader(io.StringIO(content))
    header = []
    for row in reader:
        if not row:
            continue
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

        def _f(key: str) -> float | None:
            v = data.get(key, "").strip()
            try:
                return float(v) if v else None
            except ValueError:
                return None

        cost_basis_price = _f("CostBasisPrice")
        mark_price       = _f("MarkPrice")
        pos_value        = _f("PositionValue")
        currency         = data.get("CurrencyPrimary", "USD").strip()

        if asset_class == "STK":
            positions.append({
                "type":             "stock",
                "symbol":           symbol_raw,
                "qty":              int(abs(qty)),
                "direction":        "Long" if qty > 0 else "Short",
                "cost_basis_price": cost_basis_price,
                "mark_price":       mark_price,
                "currency":         currency,
            })
        elif asset_class == "OPT":
            underlying = _extract_symbol_from_ibkr(symbol_raw)
            if not underlying:
                continue
            # Parse Option-Felder aus Symbol: "AAPL  260925P00295000"
            m = re.match(r"^([A-Z0-9]{1,6})\s+(\d{6})([CP])(\d+)$", symbol_raw.strip())
            strike      = None
            expiry      = None
            option_type = None
            if m:
                try:
                    from datetime import datetime as _dt
                    expiry      = _dt.strptime(m.group(2), "%y%m%d").strftime("%Y-%m-%d")
                    option_type = "call" if m.group(3) == "C" else "put"
                    strike      = float(m.group(4)) / 1000.0
                except Exception:
                    pass
            positions.append({
                "type":             "option",
                "symbol":           underlying,
                "symbol_full":      symbol_raw,
                "qty":              int(abs(qty)),
                "direction":        "Long" if qty > 0 else "Short",
                "strike":           strike,
                "expiry":           expiry,
                "option_type":      option_type,
                "cost_basis_price": cost_basis_price,
                "mark_price":       mark_price,
                "pos_value":        pos_value,
                "currency":         currency,
            })
    return positions


# ── Spread + Prämien-Analyse aus Open Positions CSV ───────────────────────────

def _analyse_portfolio_premium(positions: list[dict]) -> dict:
    """
    Berechnet Prämieneinnahmen, Spreads und Budget-Daten aus geparsten Positionen.

    Returns dict mit:
      total_credit:       Summe aller eingenommenen Prämien (Short-Optionen) in USD
      total_debit:        Summe aller bezahlten Prämien (Long-Optionen) in USD
      net_credit:         total_credit - total_debit
      spreads:            Liste erkannter Spread-Paare
      naked_shorts:       Short-Optionen ohne passendes Long-Leg
      total_max_loss:     Geschätztes max. Risiko aller Spreads
      premium_per_month:  Hochrechnung auf 30 Tage (aus DTE-gewichtetem Credit)
    """
    from datetime import date as _date
    import math

    opts = [p for p in positions if p["type"] == "option"]
    today = _date.today()

    # Alle Short-Legs und Long-Legs nach (Underlying, Expiry, Type) gruppieren
    by_key: dict[tuple, list[dict]] = {}
    for p in opts:
        key = (p["symbol"], p.get("expiry", ""), p.get("option_type", ""))
        by_key.setdefault(key, []).append(p)

    total_credit  = 0.0
    total_debit   = 0.0
    spreads:      list[dict] = []
    naked_shorts: list[dict] = []

    # Alle Short-Positionen durchgehen und versuchen zu einem Spread zu kombinieren
    processed_keys: set = set()
    for (sym, expiry, otype), legs in by_key.items():
        if not legs:
            continue
        shorts = [l for l in legs if l["direction"] == "Short"]
        longs  = [l for l in legs if l["direction"] == "Long"]

        for s in shorts:
            cb_price = s.get("cost_basis_price") or 0.0
            contracts = s.get("qty", 1)
            credit = cb_price * contracts * 100
            total_credit += credit

        for l in longs:
            cb_price = l.get("cost_basis_price") or 0.0
            contracts = l.get("qty", 1)
            debit = cb_price * contracts * 100
            total_debit += debit

    # Spread-Erkennung: gleiches Underlying + Expiry + gleicher Typ
    # Erkenne Bull Put Spreads: Short höherer Strike + Long niedrigerer Strike
    # Erkenne Bear Call Spreads: Short niedrigerer Strike + Long höherer Strike
    by_sym_exp: dict[tuple, dict] = {}
    for p in opts:
        key = (p["symbol"], p.get("expiry", ""), p.get("option_type", ""))
        by_sym_exp.setdefault(key, {"longs": [], "shorts": []})
        if p["direction"] == "Short":
            by_sym_exp[key]["shorts"].append(p)
        else:
            by_sym_exp[key]["longs"].append(p)

    matched_shorts: set[int] = set()
    matched_longs:  set[int] = set()

    for (sym, expiry, otype), grp in by_sym_exp.items():
        for s in grp["shorts"]:
            s_strike = s.get("strike") or 0.0
            best_long = None
            for l in grp["longs"]:
                if id(l) in matched_longs:
                    continue
                l_strike = l.get("strike") or 0.0
                if otype == "put" and l_strike < s_strike:
                    best_long = l
                elif otype == "call" and l_strike > s_strike:
                    best_long = l
            if best_long:
                matched_shorts.add(id(s))
                matched_longs.add(id(best_long))
                s_cb   = s.get("cost_basis_price") or 0.0
                l_cb   = best_long.get("cost_basis_price") or 0.0
                contracts = min(s.get("qty", 1), best_long.get("qty", 1))
                net_cred  = (s_cb - l_cb) * contracts * 100
                s_strike  = s.get("strike") or 0.0
                l_strike  = best_long.get("strike") or 0.0
                width     = abs(s_strike - l_strike)
                max_loss  = width * contracts * 100 - net_cred

                try:
                    exp_date = _date.fromisoformat(expiry)
                    dte = max(0, (exp_date - today).days)
                except Exception:
                    dte = 30

                label = (
                    f"Bull Put {l_strike:.0f}/{s_strike:.0f}"
                    if otype == "put"
                    else f"Bear Call {s_strike:.0f}/{l_strike:.0f}"
                )
                spreads.append({
                    "symbol":    sym,
                    "expiry":    expiry,
                    "dte":       dte,
                    "type":      label,
                    "net_credit":round(net_cred, 2),
                    "width":     round(width, 2),
                    "max_loss":  round(max_loss, 2),
                    "contracts": contracts,
                    "s_strike":  s_strike,
                    "l_strike":  l_strike,
                })
            else:
                naked_shorts.append(s)

    total_max_loss = sum(sp["max_loss"] for sp in spreads if sp["max_loss"] > 0)

    # Prämieneinnahme auf 30 Tage hochrechnen: gewichtet nach DTE
    # Jeder Spread: Credit × (30 / DTE) → was würde man verdienen wenn man jetzt öffnet
    if spreads:
        monthly_est = sum(
            sp["net_credit"] * (30 / max(sp["dte"], 1))
            for sp in spreads
        )
    else:
        monthly_est = total_credit  # Fallback: rohe Summe

    return {
        "total_credit":    round(total_credit, 2),
        "total_debit":     round(total_debit, 2),
        "net_credit":      round(total_credit - total_debit, 2),
        "spreads":         spreads,
        "naked_shorts":    naked_shorts,
        "total_max_loss":  round(total_max_loss, 2),
        "premium_per_month": round(monthly_est, 2),
        "n_spreads":       len(spreads),
    }


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

def _build_candidates(opt_df: pd.DataFrame, corr_map: dict,
                      min_credit: float, min_iv_rank: float,
                      strategies: list[str]) -> list[dict]:
    """
    Baut Hedge-Kandidaten aus Optionsdaten.
    Strategien: "Short Put" und/oder "Bear Call Spread"
    - Short Put: auf Symbole die bei Crash steigen (negativ korreliert) → Put verfällt wertlos
    - Bear Call Spread: auf Symbole die bei Crash steigen → Calls verfallen wertlos, Prämie eingenommen
    """
    results = []

    for col in ["strike_price", "premium", "greeks_delta", "iv", "iv_rank",
                "open_interest", "dte", "stock_price"]:
        opt_df[col] = pd.to_numeric(opt_df[col], errors="coerce")
    opt_df = opt_df.dropna(subset=["premium", "greeks_delta", "iv_rank", "stock_price"])

    puts  = opt_df[opt_df["option_type"] == "put"].copy()
    calls = opt_df[opt_df["option_type"] == "call"].copy()

    for sym, sym_df in opt_df.groupby("symbol"):
        corr     = corr_map.get(sym, 0.0)
        sym_puts  = puts[puts["symbol"] == sym]
        sym_calls = calls[calls["symbol"] == sym]

        for exp_date in sym_df["expiration_date"].unique():
            exp_puts  = sym_puts[sym_puts["expiration_date"] == exp_date].copy()
            exp_calls = sym_calls[sym_calls["expiration_date"] == exp_date].copy()
            if exp_puts.empty and exp_calls.empty:
                continue

            dte = int(sym_df[sym_df["expiration_date"] == exp_date]["dte"].iloc[0])

            # ── Short Put ────────────────────────────────────────────────────
            if "Short Put" in strategies and not exp_puts.empty:
                exp_puts["_dd"] = (exp_puts["greeks_delta"].abs() - 0.30).abs()
                leg = exp_puts.loc[exp_puts["_dd"].idxmin()]
                stock_price = float(leg["stock_price"])
                strike      = float(leg["strike_price"])
                premium     = float(leg["premium"])
                credit      = premium * 100
                risk        = strike * 100
                iv_rank     = float(leg["iv_rank"])
                iv          = float(leg["iv"])
                if credit >= min_credit and risk > 0 and iv_rank >= min_iv_rank:
                    ror         = credit / risk * 100
                    otm         = (stock_price - strike) / stock_price * 100
                    hedge_score = round(abs(corr) * ror, 2)
                    results.append({
                        "Strategie":       "Short Put",
                        "Symbol":          sym,
                        "Verfall":         str(exp_date),
                        "DTE":             dte,
                        "Beine":           f"Sell {strike:.2f}P",
                        "Kredit $":        round(credit, 0),
                        "Max Profit $":    round(credit, 0),
                        "Max Risiko $":    round(risk, 0),
                        "RoR %":           round(ror, 1),
                        "Breakeven":       round(strike - premium, 2),
                        "Delta":           round(float(leg["greeks_delta"]), 2),
                        "IV %":            round(iv * 100, 1),
                        "IV Rank":         round(iv_rank, 0),
                        "OTM %":           round(otm, 1),
                        "Korrelation":     round(corr, 3),
                        "Hedge Score":     hedge_score,
                        "_stock_price":    stock_price,
                        "_company_name":   str(leg.get("company_name") or sym),
                        "_company_sector": str(leg.get("company_sector") or ""),
                        "_legs": [{"type": "Put", "action": "Short",
                                   "strike": strike, "premium": premium, "bs": None,
                                   "delta": float(leg["greeks_delta"]), "iv": iv,
                                   "theta": 0.0, "oi": int(leg.get("open_interest") or 0),
                                   "volume": 0}],
                        "_earnings_warn": False,
                    })

            # ── Bear Call Spread ──────────────────────────────────────────────
            if "Bear Call Spread" in strategies and len(exp_calls) >= 2:
                exp_calls = exp_calls.sort_values("strike_price")
                # Sell-Leg: Delta ~0.30
                exp_calls["_dd"] = (exp_calls["greeks_delta"].abs() - 0.30).abs()
                sell_leg = exp_calls.loc[exp_calls["_dd"].idxmin()]
                # Buy-Leg: höherer Strike (OTM Call)
                buy_cands = exp_calls[exp_calls["strike_price"] > sell_leg["strike_price"]]
                if buy_cands.empty:
                    continue
                buy_cands = buy_cands.copy()
                buy_cands["_dd"] = (buy_cands["greeks_delta"].abs() - 0.15).abs()
                buy_leg = buy_cands.loc[buy_cands["_dd"].idxmin()]

                stock_price = float(sell_leg["stock_price"])
                sell_strike = float(sell_leg["strike_price"])
                buy_strike  = float(buy_leg["strike_price"])
                credit      = (float(sell_leg["premium"]) - float(buy_leg["premium"])) * 100
                width       = buy_strike - sell_strike
                risk        = width * 100 - credit
                iv_rank     = float(sell_leg["iv_rank"])
                iv          = float(sell_leg["iv"])

                if credit >= min_credit and risk > 0 and iv_rank >= min_iv_rank:
                    ror         = credit / risk * 100
                    otm         = (sell_strike - stock_price) / stock_price * 100
                    hedge_score = round(abs(corr) * ror, 2)
                    results.append({
                        "Strategie":       "Bear Call Spread",
                        "Symbol":          sym,
                        "Verfall":         str(exp_date),
                        "DTE":             dte,
                        "Beine":           f"Sell {sell_strike:.2f}C / Buy {buy_strike:.2f}C",
                        "Kredit $":        round(credit, 0),
                        "Max Profit $":    round(credit, 0),
                        "Max Risiko $":    round(risk, 0),
                        "RoR %":           round(ror, 1),
                        "Breakeven":       round(sell_strike + credit / 100, 2),
                        "Delta":           round(float(sell_leg["greeks_delta"]), 2),
                        "IV %":            round(iv * 100, 1),
                        "IV Rank":         round(iv_rank, 0),
                        "OTM %":           round(otm, 1),
                        "Korrelation":     round(corr, 3),
                        "Hedge Score":     hedge_score,
                        "_stock_price":    stock_price,
                        "_company_name":   str(sell_leg.get("company_name") or sym),
                        "_company_sector": str(sell_leg.get("company_sector") or ""),
                        "_legs": [
                            {"type": "Call", "action": "Short",
                             "strike": sell_strike, "premium": float(sell_leg["premium"]),
                             "bs": None, "delta": float(sell_leg["greeks_delta"]),
                             "iv": iv, "theta": 0.0,
                             "oi": int(sell_leg.get("open_interest") or 0), "volume": 0},
                            {"type": "Call", "action": "Long",
                             "strike": buy_strike, "premium": float(buy_leg["premium"]),
                             "bs": None, "delta": float(buy_leg["greeks_delta"]),
                             "iv": float(buy_leg["iv"]), "theta": 0.0,
                             "oi": int(buy_leg.get("open_interest") or 0), "volume": 0},
                        ],
                        "_earnings_warn": False,
                    })

    return results


@st.cache_data(ttl=600, show_spinner=False)
def _load_insurance_candidates(
    symbol: str,
    stock_price: float,
    dte_min: int,
    dte_max: int,
    puffer_min_pct: float,
    puffer_max_pct: float,
) -> pd.DataFrame:
    """
    Lädt Long-Put-Kandidaten für den Hedge-Budget Tab.
    puffer_min_pct / puffer_max_pct = Abstand vom Kurs in % (z.B. 5 = 5% OTM).
    """
    lo = round(stock_price * (1 - puffer_max_pct / 100), 2)
    hi = round(stock_price * (1 - puffer_min_pct / 100), 2)
    df = select_into_dataframe(
        query="""
            SELECT
                symbol,
                strike_price,
                expiration_date,
                days_to_expiration      AS dte,
                ROUND(day_close::numeric, 2)             AS premium,
                ROUND(greeks_delta::numeric, 3)          AS delta,
                ROUND(implied_volatility::numeric * 100, 1) AS iv_pct,
                ROUND(iv_rank::numeric, 1)               AS iv_rank,
                open_interest                            AS oi
            FROM "OptionDataMerged"
            WHERE symbol = :sym
              AND contract_type = 'put'
              AND strike_price BETWEEN :lo AND :hi
              AND days_to_expiration BETWEEN :dmin AND :dmax
              AND open_interest >= 50
              AND day_close > 0
            ORDER BY days_to_expiration, strike_price DESC
        """,
        params={"sym": symbol, "lo": lo, "hi": hi, "dmin": dte_min, "dmax": dte_max},
    )
    return df if df is not None and not df.empty else pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def _load_vix_call_candidates(dte_min: int, dte_max: int) -> pd.DataFrame:
    """Lädt VIX-Call-Kandidaten für den Hedge-Budget Tab."""
    df = select_into_dataframe(
        query="""
            SELECT
                symbol,
                strike_price,
                expiration_date,
                days_to_expiration      AS dte,
                ROUND(day_close::numeric, 2)             AS premium,
                ROUND(greeks_delta::numeric, 3)          AS delta,
                ROUND(implied_volatility::numeric * 100, 1) AS iv_pct,
                open_interest                            AS oi
            FROM "OptionDataMerged"
            WHERE symbol IN ('VIX', '^VIX')
              AND contract_type = 'call'
              AND days_to_expiration BETWEEN :dmin AND :dmax
              AND open_interest >= 20
              AND day_close > 0
            ORDER BY days_to_expiration, strike_price
        """,
        params={"dmin": dte_min, "dmax": dte_max},
    )
    return df if df is not None and not df.empty else pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def _load_spy_price() -> float | None:
    df = select_into_dataframe(
        query='SELECT live_stock_price FROM "OptionDataMerged" WHERE symbol = :s AND live_stock_price IS NOT NULL LIMIT 1',
        params={"s": "SPY"},
    )
    if df is not None and not df.empty:
        return float(df.iloc[0]["live_stock_price"])
    return None


# ── Hedge-Budget Tab ──────────────────────────────────────────────────────────

def _render_hedge_budget(positions: list[dict]):
    """
    Rendert den 'Hedge-Budget' Tab:
    3 Größen nebeneinander: Crash-Risiko / Versicherungskosten / Prämieneinnahme
    + konkrete SPY-Put und VIX-Call Kandidaten aus der DB.
    """
    st.markdown("### 💰 Hedge-Budget — Versicherung vs. Prämieneinnahme")
    st.caption(
        "Wie viel kostet dich eine Absicherung — und wie viel % deiner monatlichen "
        "Prämieneinnahme frisst sie? Die drei Zahlen nebeneinander."
    )

    premium_data = _analyse_portfolio_premium(positions)

    # ── Schritt 1: Prämieneinnahme anzeigen + überschreiben ──────────────────
    with st.container(border=True):
        st.markdown("**Schritt 1 — Prämieneinnahmen aus deinem Portfolio**")
        col_auto, col_man = st.columns([2, 1])
        with col_auto:
            n_sp  = premium_data["n_spreads"]
            cred  = premium_data["total_credit"]
            deb   = premium_data["total_debit"]
            net   = premium_data["net_credit"]
            est_m = premium_data["premium_per_month"]

            if n_sp > 0:
                st.success(
                    f"**{n_sp} Spread{'s' if n_sp != 1 else ''}** erkannt · "
                    f"Eingenommene Prämie (Summe): **${cred:,.2f}** · "
                    f"Bezahlte Prämie (Long-Legs): **${deb:,.2f}** · "
                    f"**Netto-Credit: ${net:,.2f}**"
                )
                st.caption(
                    f"Monatliche Hochrechnung (DTE-gewichtet): ~**${est_m:,.0f}/Monat** "
                    f"— wird verwendet wenn kein manueller Wert eingetragen."
                )
            else:
                st.warning(
                    "Keine Spreads automatisch erkannt. "
                    "Bitte monatliche Prämieneinnahme manuell eingeben."
                )

        with col_man:
            monthly_override = st.number_input(
                "Manuell: monatliche Prämien $",
                min_value=0.0,
                value=float(max(est_m, 0)),
                step=100.0,
                format="%.0f",
                key="hb_monthly_premium",
                help="Überschreibt die automatische Hochrechnung.",
            )

    monthly_income = monthly_override if monthly_override > 0 else max(est_m, 1)

    # ── Schritt 2: Parameter ──────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**Schritt 2 — Absicherungs-Parameter**")
        p1, p2, p3 = st.columns(3)
        with p1:
            insurance_days = st.selectbox(
                "Versicherungszeitraum",
                [30, 45, 60, 90, 120],
                index=1,
                format_func=lambda x: f"{x} Tage",
                key="hb_days",
            )
        with p2:
            crash_pct = st.slider(
                "Crash-Szenario absichern gegen",
                5, 50, 20, 5,
                format="%d%%",
                key="hb_crash_pct",
                help="Wieviel % Marktfall willst du abfedern?",
            )
        with p3:
            cover_pct = st.slider(
                "Wieviel % des Schadens abfedern",
                10, 100, 50, 10,
                format="%d%%",
                key="hb_cover_pct",
                help="50% = Hedge soll die Hälfte des Crashschadens ausgleichen.",
            )

    only_options = st.toggle(
        "Nur Optionen absichern (Aktien-Seite ignorieren)",
        value=True,
        key="hb_only_options",
        help="An: Crash-Risiko nur aus den Spread-Positionen (Max-Loss). "
             "Aus: Beta-gewichteter Aktien-Verlust wird dazugerechnet.",
    )

    # ── Crash-Risiko berechnen ────────────────────────────────────────────────
    total_max_loss = premium_data["total_max_loss"]

    # Beta-gewichtetes Verlustrisiko der Aktien-Seite
    stock_syms = tuple(sorted({p["symbol"] for p in positions if p["type"] == "stock"}))
    opt_syms   = tuple(sorted({p["symbol"] for p in positions if p["type"] == "option"}))
    all_syms   = tuple(sorted(set(stock_syms) | set(opt_syms)))
    betas_hb   = _load_betas(all_syms) if all_syms else {}
    prices_hb  = _load_stock_prices_current(all_syms) if all_syms else {}

    # Beta-gew. Verlust der Aktien bei crash_pct% Rückgang
    beta_weighted_loss = 0.0
    if not only_options:
        for p in positions:
            if p["type"] != "stock" or p.get("direction", "Long") != "Long":
                continue
            sym  = p["symbol"]
            beta = betas_hb.get(sym) or _FALLBACK_BETAS.get(sym) or 1.0
            px   = prices_hb.get(sym) or 0.0
            qty  = p.get("qty", 0)
            beta_weighted_loss += px * qty * beta * (crash_pct / 100)

    # Optionen-Seite: max_loss der Spreads (Worst case: alle Spreads maximal verlieren)
    options_crash_loss = total_max_loss

    total_crash_loss = beta_weighted_loss + options_crash_loss
    target_hedge_value = total_crash_loss * (cover_pct / 100)

    # ── Monatliche Versicherungskosten-Budget ─────────────────────────────────
    months_covered   = insurance_days / 30.0
    income_for_period = monthly_income * months_covered
    budget_30pct     = income_for_period * 0.30
    budget_20pct     = income_for_period * 0.20
    budget_10pct     = income_for_period * 0.10

    # ── Die 3 Zahlen nebeneinander ────────────────────────────────────────────
    st.divider()
    st.markdown("#### Die drei Zahlen")
    kc1, kc2, kc3 = st.columns(3)

    with kc1:
        st.markdown(
            f"<div style='background:#7f1d1d22;border:2px solid #ef4444;border-radius:10px;"
            f"padding:16px;text-align:center;'>"
            f"<div style='color:#9ca3af;font-size:12px;font-weight:600;'>CRASH-RISIKO</div>"
            f"<div style='color:#ef4444;font-size:32px;font-weight:800;'>${total_crash_loss:,.0f}</div>"
            f"<div style='color:#fca5a5;font-size:12px;'>bei −{crash_pct}% Marktfall</div>"
            f"<div style='color:#9ca3af;font-size:11px;margin-top:6px;'>"
            f"Aktien: ${beta_weighted_loss:,.0f} · Spreads: ${options_crash_loss:,.0f}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    with kc2:
        abfed_val = total_crash_loss * cover_pct / 100
        st.markdown(
            f"<div style='background:#78350f22;border:2px solid #f59e0b;border-radius:10px;"
            f"padding:16px;text-align:center;'>"
            f"<div style='color:#9ca3af;font-size:12px;font-weight:600;'>ABSICHERUNGSZIEL</div>"
            f"<div style='color:#f59e0b;font-size:32px;font-weight:800;'>${abfed_val:,.0f}</div>"
            f"<div style='color:#fcd34d;font-size:12px;'>{cover_pct}% des Schadens abfedern</div>"
            f"<div style='color:#9ca3af;font-size:11px;margin-top:6px;'>"
            f"für {insurance_days} Tage Schutz</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    with kc3:
        st.markdown(
            f"<div style='background:#14532d22;border:2px solid #22c55e;border-radius:10px;"
            f"padding:16px;text-align:center;'>"
            f"<div style='color:#9ca3af;font-size:12px;font-weight:600;'>PRÄMIENEINNAHME</div>"
            f"<div style='color:#22c55e;font-size:32px;font-weight:800;'>${monthly_income:,.0f}</div>"
            f"<div style='color:#86efac;font-size:12px;'>pro Monat</div>"
            f"<div style='color:#9ca3af;font-size:11px;margin-top:6px;'>"
            f"in {insurance_days}d = ${income_for_period:,.0f}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── Budget-Ampel ──────────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Versicherungsbudget (empfohlen ≤ 30% der Prämieneinnahme)")
    b1, b2, b3 = st.columns(3)
    b1.metric("30%-Budget (konservativ)", f"${budget_30pct:,.0f}",
              help=f"30% von ${income_for_period:,.0f} für {insurance_days} Tage")
    b2.metric("20%-Budget (empfohlen)", f"${budget_20pct:,.0f}")
    b3.metric("10%-Budget (sparsam)", f"${budget_10pct:,.0f}")

    st.caption(
        f"Wenn eine Versicherung **< ${budget_20pct:,.0f}** kostet und {cover_pct}% des "
        f"${total_crash_loss:,.0f}-Crashs abfedert → **selbstfinanziert**. "
        f"Teurer → frisst deinen Edge."
    )

    # ── SPY Put Kandidaten ────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### SPY Long Put — echte Crash-Versicherung")
    st.caption(
        f"Welcher SPY Put kostet wie viel — und wie viel % deiner {insurance_days}-Tage-"
        f"Prämie frisst er?"
    )

    spy_price = _load_spy_price()
    if spy_price:
        spy_puts = _load_insurance_candidates(
            "SPY", spy_price,
            dte_min=max(insurance_days - 15, 14),
            dte_max=insurance_days + 30,
            puffer_min_pct=crash_pct * 0.4,
            puffer_max_pct=crash_pct * 1.3,
        )
        if not spy_puts.empty:
            spy_puts = spy_puts.copy()
            spy_puts["puffer_%"]     = ((spy_price - spy_puts["strike_price"]) / spy_price * 100).round(1)
            spy_puts["kosten_1kt"]   = (spy_puts["premium"] * 100).round(0).astype(int)

            # Kontraktanzahl um target_hedge_value zu erreichen
            # Grob: Put-Schutz bei max Verlust ≈ (strike - puffer) × 100 × Kontrakte
            # Vereinfacht: Kontrakte = target / (crash% × spy_price × 100)
            est_contracts = max(1, round(target_hedge_value / (crash_pct / 100 * spy_price * 100)))
            spy_puts["kosten_gesamt"] = (spy_puts["premium"] * 100 * est_contracts).round(0).astype(int)
            spy_puts["% der Prämie"] = (spy_puts["kosten_gesamt"] / income_for_period * 100).round(1)

            disp_spy = spy_puts[["strike_price","expiration_date","dte","puffer_%",
                                  "premium","kosten_1kt","kosten_gesamt","% der Prämie",
                                  "delta","iv_pct","iv_rank","oi"]].copy()
            disp_spy.columns = ["Strike","Verfall","DTE","Puffer %","Prämie $",
                                 "Kosten/Kt $","Kosten gesamt $","% der Prämie",
                                 "Delta","IV %","IV Rank","OI"]

            st.caption(
                f"SPY ${spy_price:.2f} · ~{est_contracts} Kontrakte für {cover_pct}%-Schutz "
                f"bei −{crash_pct}% · **Grün = ≤ 20% der Prämie**"
            )

            def _color_pct(col):
                return [
                    "color:#22c55e;font-weight:700" if v <= 20
                    else ("color:#f59e0b;font-weight:700" if v <= 35 else "color:#ef4444;font-weight:700")
                    for v in col
                ]

            sel_spy = st.dataframe(
                disp_spy.style
                .apply(_color_pct, subset=["% der Prämie"])
                .format({
                    "Puffer %":       "{:.1f}%",
                    "Prämie $":       "${:.2f}",
                    "Kosten/Kt $":    "${:.0f}",
                    "Kosten gesamt $":"${:,.0f}",
                    "% der Prämie":   "{:.1f}%",
                    "Delta":          "{:.3f}",
                    "IV %":           "{:.1f}%",
                    "IV Rank":        "{:.0f}",
                }),
                hide_index=True,
                use_container_width=True,
                on_select="rerun",
                selection_mode="single-row",
                key="hb_spy_sel",
                height=min(350, 50 + 38 * len(disp_spy)),
            )
            rows_spy = sel_spy.selection.rows if hasattr(sel_spy, "selection") else []
            if rows_spy:
                r = disp_spy.iloc[rows_spy[0]]
                cost = float(r["Kosten gesamt $"])
                pct_prem = float(r["% der Prämie"])
                color = "#22c55e" if pct_prem <= 20 else ("#f59e0b" if pct_prem <= 35 else "#ef4444")
                verdict = "✅ selbstfinanziert" if pct_prem <= 20 else ("⚠️ akzeptabel" if pct_prem <= 35 else "❌ frisst den Edge")
                st.markdown(
                    f"**SPY Put Strike {r['Strike']:.0f} · Verfall {r['Verfall']} · "
                    f"{est_contracts} Kontrakt{'e' if est_contracts != 1 else ''}**  \n"
                    f"Kosten: **${cost:,.0f}** = "
                    f"<span style='color:{color};font-weight:700;'>{pct_prem:.1f}% der {insurance_days}-Tage-Prämie {verdict}</span>  \n"
                    f"Abfederung bei −{crash_pct}%: ~**{cover_pct}%** des geschätzten Schadens (${target_hedge_value:,.0f})",
                    unsafe_allow_html=True,
                )
        else:
            st.info(f"Keine SPY-Puts in DTE-Fenster {insurance_days - 15}–{insurance_days + 30} gefunden.")
    else:
        st.warning("SPY-Kurs nicht in DB verfügbar.")

    # ── VIX Call Kandidaten ───────────────────────────────────────────────────
    st.divider()
    st.markdown("#### VIX Long Call — Volatilitäts-Versicherung")
    st.caption(
        "VIX-Calls explodieren bei echten Crashes (+300–500%). "
        "Günstig wenn VIX niedrig. Basisrisiko: VIX muss spiken."
    )

    vix_df = select_into_dataframe(
        query='SELECT close FROM "StockPricesYahoo" WHERE symbol = :s LIMIT 1',
        params={"s": "^VIX"},
    )
    vix_level = float(vix_df.iloc[0]["close"]) if vix_df is not None and not vix_df.empty else None

    if vix_level:
        v_color = "#22c55e" if vix_level < 15 else ("#f59e0b" if vix_level < 25 else "#ef4444")
        v_label = "günstig — jetzt kaufen" if vix_level < 15 else ("fair" if vix_level < 25 else "teuer — Crash läuft bereits")
        st.markdown(
            f"VIX aktuell: <b style='color:{v_color};font-size:20px;'>{vix_level:.1f}</b> "
            f"<span style='color:{v_color};'>— {v_label}</span>",
            unsafe_allow_html=True,
        )

    vix_calls = _load_vix_call_candidates(
        dte_min=max(insurance_days - 15, 14),
        dte_max=insurance_days + 30,
    )
    if not vix_calls.empty:
        vix_calls = vix_calls.copy()
        # Schätzung: VIX-Call-Wert bei Crash
        # Historisch: −20% Markt → VIX +150%, −30% → VIX +250%
        vix_mult = {5: 0.5, 10: 0.8, 15: 1.2, 20: 1.5, 25: 2.0, 30: 2.5, 40: 3.5, 50: 4.5}
        mult = next((v for k, v in sorted(vix_mult.items()) if crash_pct <= k), 4.5)
        if vix_level:
            vix_at_crash = vix_level * (1 + mult)
            vix_calls["est_wert_crash"] = (
                (vix_at_crash - vix_calls["strike_price"]).clip(lower=0) * 100
            ).round(0).astype(int)
        else:
            vix_calls["est_wert_crash"] = 0

        vix_calls["kosten_1kt"] = (vix_calls["premium"] * 100).round(0).astype(int)
        vix_n = max(1, round(target_hedge_value / max(vix_calls["est_wert_crash"].max(), 1)))
        vix_calls["kosten_gesamt"] = (vix_calls["kosten_1kt"] * vix_n).astype(int)
        vix_calls["% der Prämie"] = (vix_calls["kosten_gesamt"] / income_for_period * 100).round(1)
        vix_calls["Est. Wert Crash $"] = (vix_calls["est_wert_crash"] * vix_n).astype(int)

        disp_vix = vix_calls[["strike_price","expiration_date","dte","premium",
                               "kosten_1kt","kosten_gesamt","% der Prämie",
                               "Est. Wert Crash $","delta","iv_pct","oi"]].copy()
        disp_vix.columns = ["Strike VIX","Verfall","DTE","Prämie $",
                             "Kosten/Kt $","Kosten gesamt $","% der Prämie",
                             f"Est. Wert bei −{crash_pct}% $",
                             "Delta","IV %","OI"]

        vix_suffix = f"~{vix_n} Kontrakt{'e' if vix_n != 1 else ''}" if vix_n > 0 else ""
        st.caption(
            f"VIX-Calls · {vix_suffix} für {cover_pct}%-Schutzwirkung · "
            f"VIX-Schätzung bei −{crash_pct}%: ~{vix_level * (1 + mult):.0f} (×{1+mult:.1f})"
            if vix_level else f"VIX-Calls · {vix_suffix}"
        )

        def _color_pct_vix(col):
            return [
                "color:#22c55e;font-weight:700" if v <= 10
                else ("color:#f59e0b;font-weight:700" if v <= 25 else "color:#ef4444;font-weight:700")
                for v in col
            ]

        st.dataframe(
            disp_vix.style
            .apply(_color_pct_vix, subset=["% der Prämie"])
            .format({
                "Prämie $":           "${:.2f}",
                "Kosten/Kt $":        "${:.0f}",
                "Kosten gesamt $":    "${:,.0f}",
                "% der Prämie":       "{:.1f}%",
                f"Est. Wert bei −{crash_pct}% $": "${:,.0f}",
                "Delta":              "{:.3f}",
                "IV %":               "{:.1f}%",
            }),
            hide_index=True,
            use_container_width=True,
            height=min(350, 50 + 38 * len(disp_vix)),
        )
        st.caption(
            f"⚠️ VIX-Call-Wert bei Crash ist eine *Schätzung* auf Basis historischer VIX-Reaktionen. "
            f"Basisrisiko: VIX muss wirklich explodieren — bei langsam fallendem Markt kaum Gewinn."
        )
    else:
        st.info("Keine VIX-Calls in der DB für dieses DTE-Fenster.")

    # ── Spread-Detail (Aufklappen) ────────────────────────────────────────────
    if premium_data["spreads"]:
        st.divider()
        with st.expander(f"📋 {premium_data['n_spreads']} erkannte Spreads im Portfolio", expanded=False):
            sp_rows = []
            for sp in sorted(premium_data["spreads"], key=lambda x: x["net_credit"], reverse=True):
                sp_rows.append({
                    "Symbol":      sp["symbol"],
                    "Typ":         sp["type"],
                    "Verfall":     sp["expiry"],
                    "DTE":         sp["dte"],
                    "Net Credit $": sp["net_credit"],
                    "Breite $":    sp["width"] * sp["contracts"] * 100,
                    "Max Verlust $": sp["max_loss"],
                    "Kontrakte":   sp["contracts"],
                })
            df_sp = pd.DataFrame(sp_rows)
            st.dataframe(
                df_sp.style.format({
                    "Net Credit $":   "${:.2f}",
                    "Breite $":       "${:.0f}",
                    "Max Verlust $":  "${:.0f}",
                }),
                hide_index=True,
                use_container_width=True,
            )
            st.caption(
                f"Gesamtes Spread-Risiko: **${premium_data['total_max_loss']:,.0f}** · "
                f"Gesamt-Credit: **${premium_data['net_credit']:,.0f}**"
            )


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
            hedge_strategies = st.multiselect(
                "Strategien",
                ["Short Put", "Bear Call Spread"],
                default=["Short Put", "Bear Call Spread"],
                help="Short Put: Prämie auf negativ-korrelierte Gegenwerte. "
                     "Bear Call Spread: begrenzteres Risiko, Prämie wenn Gegenwert steigt.",
            )

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

    # Hedge-Budget Tab braucht keine Suchergebnisse — nur das Portfolio
    if not run and "chf_results" not in st.session_state:
        st.divider()
        tab_budget_early, = st.tabs(["💰 Hedge-Budget"])
        with tab_budget_early:
            _render_hedge_budget(positions)
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
            # Bekannte Hedge-Symbole nur ergänzen wenn sie tatsächlich negativ korreliert sind
            extra = [s for s in _KNOWN_HEDGES if s not in neg_corr["peer_symbol"].values]
            if extra:
                extra_df = corr_df[
                    corr_df["peer_symbol"].isin(extra) &
                    (corr_df["correlation_mean"] <= 0)
                ]
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

            results = _build_candidates(opt_df, corr_map, min_credit, min_iv_rank,
                                        strategies=hedge_strategies or ["Short Put"])
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

    tab_heatmap, tab_corr, tab_strategies, tab_stress, tab_budget = st.tabs([
        "Portfolio-Matrix", "Negativ-Korrelierte", "Hedge-Strategien", "Stress-Test", "💰 Hedge-Budget"
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

    with tab_budget:
        _render_hedge_budget(positions)


if __name__ == "__main__":
    main()
