"""
CSP-Einstiegs-Screener — Scoring nach "Optionen unschlagbar handeln", Kap. 4+5.

Reine Python-Logik auf einem DataFrame (keine DB, kein Streamlit).
Harte Filter (Preis 15-80$, Options-Liquidität OI/Vol >= 100) übernimmt die SQL
(db/SQL/query/put_screener.sql); hier wird je Kriterium 1 Punkt vergeben.

Ehrlichkeit: Die Kriterien 1/2/5 (Umsatz-/EPS-/Cashflow-"Trend") sind mangels
Mehrjahres-Daten nur als AKTUELLE Werte abgebildet ("(aktuell)"), nicht als
10-Jahres-Verlauf. Siehe Design-Spec, Abschnitt "Warum nur aktuell".
"""
from __future__ import annotations

import pandas as pd

# KGV-Schwelle als konfigurierbarer Default (Buch-Zahl nicht eindeutig; User: "egal").
DEFAULT_PE_MAX = 40.0

# RSI gilt ab hier als überkauft (Kap. 5, Timing).
RSI_OVERBOUGHT = 70.0

# Sektoren, die das Buch ausschließt (Kap. 4, Punkt 13).
EXCLUDED_SECTORS = {"cannabis"}

# Die Scoring-Kriterien: (Ergebnis-Spalte, Beschriftung, Prüf-Funktion).
# Jede Prüf-Funktion bekommt (row, pe_max) und gibt True/False.
def _is_pos(v) -> bool:
    return pd.notna(v) and float(v) > 0


def _le(v, threshold) -> bool:
    return pd.notna(v) and float(v) <= threshold


_CRITERIA = [
    ("crit_revenue_growth", "Umsatzwachstum (aktuell)",     lambda r, pe: _is_pos(r.get("revenue_growth_pct")),                                     "revenue_growth_pct", "aktuell"),
    ("crit_eps_growth",     "EPS-Wachstum (aktuell)",        lambda r, pe: _is_pos(r.get("eps_growth_pct")),                                         "eps_growth_pct",     "aktuell"),
    ("crit_payout",         "Payout <= 60 %",                lambda r, pe: _le(r.get("payout_ratio_pct"), 60.0),                                      "payout_ratio_pct",   ""),
    ("crit_cashflow",       "Cashflow positiv (aktuell)",    lambda r, pe: _is_pos(r.get("operating_cashflow")) and _is_pos(r.get("free_cashflow")),  "operating_cashflow", "aktuell"),
    ("crit_pe",             "KGV moderat",                   lambda r, pe: _le(r.get("trailing_pe"), pe),                                             "trailing_pe",        ""),
    ("crit_not_volatile",   "Nicht hochvolatil (IV-Rank)",   lambda r, pe: _le(r.get("iv_rank"), 60.0),                                               "iv_rank",            ""),
    ("crit_rsi",            "RSI nicht überkauft",           lambda r, pe: pd.notna(r.get("rsi_14")) and float(r.get("rsi_14")) < RSI_OVERBOUGHT,     "rsi_14",             ""),
    ("crit_macd",           "MACD steigend",                 lambda r, pe: _is_pos(r.get("macd_histogram")),                                          "macd_histogram",     ""),
    ("crit_sector",         "Kein Cannabis/Nischen-Sektor",  lambda r, pe: _sector_ok(r.get("sector")),                                               "sector",             ""),
]

SCORE_MAX = len(_CRITERIA)


def _sector_ok(sector) -> bool:
    if sector is None or (isinstance(sector, float) and pd.isna(sector)):
        return True  # unbekannter Sektor wird nicht bestraft
    return str(sector).strip().lower() not in EXCLUDED_SECTORS


def score_candidates(df: pd.DataFrame, pe_max: float = DEFAULT_PE_MAX) -> pd.DataFrame:
    """Vergibt je erfülltem Kriterium 1 Punkt und sortiert absteigend nach Score.

    Args:
        df:     Kandidaten-DataFrame (eine Zeile je Aktie), Spalten siehe put_screener.sql.
        pe_max: KGV-Obergrenze (Default 40). Tech-Ausnahme regelt der Aufrufer via höherem pe_max.

    Returns:
        DataFrame mit zusätzlichen Spalten crit_* (bool), score (int) und score_max (int),
        absteigend nach score sortiert.
    """
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()

    out = df.copy()
    for col, _label, fn, *_rest in _CRITERIA:
        out[col] = out.apply(lambda r, f=fn: bool(f(r, pe_max)), axis=1)

    crit_cols = [c for c, *_ in _CRITERIA]
    out["score"] = out[crit_cols].sum(axis=1).astype(int)
    out["score_max"] = SCORE_MAX

    return out.sort_values("score", ascending=False).reset_index(drop=True)


def score_breakdown(row, pe_max: float = DEFAULT_PE_MAX) -> list:
    """Pro Kriterium: erreicht/möglich/ist-wert/annahme. Single Source of Truth für UI-Detail.

    Args:
        row:    eine Kandidaten-Zeile (pd.Series oder dict) mit den Spalten aus put_screener.sql.
        pe_max: KGV-Obergrenze.

    Returns:
        Liste von dicts {key, label, erreicht, moeglich, ist_wert, annahme}.
        Summe der erreicht == score aus score_candidates für dieselbe Zeile.
    """
    def _get(r, k):
        return r.get(k) if hasattr(r, "get") else r[k]
    out = []
    for col, label, fn, ist_key, annahme in _CRITERIA:
        out.append({
            "key": col,
            "label": label,
            "erreicht": bool(fn(row, pe_max)),
            "moeglich": 1,
            "ist_wert": _get(row, ist_key),
            "annahme": annahme,
        })
    return out


def criterion_labels() -> dict:
    """Mapping crit_-Spalte -> menschenlesbare Beschriftung (für die UI)."""
    return {col: label for col, label, *_ in _CRITERIA}


# ==========================================================================
# Shortlist-Score — reiht die qualifizierten Kandidaten für die Top-Liste.
# Nicht der Buch-Score (score_candidates), sondern ein Timing-/Attraktivitäts-
# Ranking: IV-Rank + Sektor-Rotation + Rendite + Black-Scholes-Edge.
# Wird von der Screener-Seite genutzt; hier als reine, testbare Funktion.
# ==========================================================================
def _num(v, default=0.0) -> float:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def shortlist_breakdown(row) -> list:
    """Punkte-Aufschlüsselung des Shortlist-Scores (Single Source für Score + Transparenz-UI).

    Returns: Liste von {label, punkte}. Summe == shortlist_score(row).
    """
    def _get(r, k):
        return r.get(k) if hasattr(r, "get") else r[k]

    iv = _num(_get(row, "iv_rank"))
    if iv >= 60:
        iv_pts = 3
    elif iv >= 40:
        iv_pts = 2
    elif iv >= 20:
        iv_pts = 1
    else:
        iv_pts = 0

    q = _get(row, "sektor_quadrant") or ""
    sektor_pts = 2 if q == "Leading" else 1 if q == "Improving" else 0

    ann = _num(_get(row, "annualized_pct"))
    ann_pts = 2 if ann >= 20 else 1 if ann >= 12 else 0

    # Black-Scholes-Edge: Markt-Prämie über fairem BS-Wert = strukturell teuer = gut.
    edge = _get(row, "bs_edge_pct")
    edge = _num(edge, default=0.0)
    bs_pts = 2 if edge > 5 else 1 if edge > 0 else 0

    return [
        {"label": f"IV-Rank ({iv:.0f})", "punkte": iv_pts},
        {"label": f"Sektor ({q or '—'})", "punkte": sektor_pts},
        {"label": f"Rendite ({ann:.0f} %)", "punkte": ann_pts},
        {"label": f"BS-Edge ({edge:+.1f} %)", "punkte": bs_pts},
    ]


def shortlist_score(row) -> int:
    """Summe der Shortlist-Punkte (IV + Sektor + Rendite + BS-Edge)."""
    return int(sum(item["punkte"] for item in shortlist_breakdown(row)))


# ==========================================================================
# Optionale Filter-Prädikate (Ludwig) — UI schaltet sie per Toggle zu.
# ==========================================================================
def earnings_ok(row) -> bool:
    """True, wenn KEIN Earnings-Termin innerhalb der Put-Laufzeit liegt.

    Muster wie covered_call_scanner.sql: fehlendes Earnings-Datum ist permissiv
    (nicht ausschließen). Earnings NACH Verfall = ok.
    """
    def _get(r, k):
        return r.get(k) if hasattr(r, "get") else (r[k] if k in r else None)

    dte_earn = _get(row, "days_to_earnings")
    if dte_earn is None or (isinstance(dte_earn, float) and pd.isna(dte_earn)):
        return True  # unbekannt -> nicht bestrafen
    dte_put = _num(_get(row, "put_dte"), default=0.0)
    return _num(dte_earn) > dte_put


def delta_ok(row, max_abs_delta: float) -> bool:
    """True, wenn |Put-Delta| <= max_abs_delta. Fehlendes Delta ist permissiv."""
    def _get(r, k):
        return r.get(k) if hasattr(r, "get") else (r[k] if k in r else None)

    d = _get(row, "put_delta")
    if d is None or (isinstance(d, float) and pd.isna(d)):
        return True
    return abs(_num(d)) <= max_abs_delta


def put_metrics(strike: float, premium: float, dte: int) -> dict:
    """Kennzahlen eines verkaufbaren Puts. Reine Arithmetik, keine DB.

    premium_pct      = Prämie / Strike * 100
    annualized_pct   = premium_pct * 365 / dte
    breakeven        = Strike - Prämie
    capital_required = Strike * 100  (Cash-Secured)
    """
    strike = float(strike or 0)
    premium = float(premium or 0)
    dte = int(dte or 0)
    premium_pct = (premium / strike * 100.0) if strike > 0 else 0.0
    annualized_pct = (premium_pct * 365.0 / dte) if dte > 0 else 0.0
    return {
        "premium_pct": premium_pct,
        "annualized_pct": annualized_pct,
        "breakeven": strike - premium,
        "capital_required": strike * 100.0,
    }


# ---------------------------------------------------------------------------
# Ampel-Bewertung für verkaufbare Puts (genutzt von roll_and_screen.py)
# ---------------------------------------------------------------------------
DEFAULT_MIN_PUFFER_PCT = 10.0
MIN_ANNUAL_RETURN_PCT = 12.0
_RISK_FREE_RATE_EVAL = 0.03


def _f(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (ValueError, TypeError):
        return None
    return None if f != f else f


def put_evaluation(kurs, strike, praemie, dte, iv, delta, bs_preis,
                   min_puffer_pct: float = DEFAULT_MIN_PUFFER_PCT) -> dict:
    """Bewertet einen verkaufbaren Put mit fester Ampel-Logik.

    ✅  annualisierte Rendite >= 12% UND Puffer >= min_puffer_pct UND BS-Edge > 0
    ⚠️  Rendite >= 12%, aber Puffer ODER BS-Edge verletzt
    ❌  Rendite < 12%
    """
    from src.black_scholes import ProbLessThan  # lokaler Import verhindert Zirkel

    kurs, strike, praemie = _f(kurs), _f(strike), _f(praemie)
    iv, delta, bs_preis = _f(iv), _f(delta), _f(bs_preis)
    dte = int(dte) if dte not in (None, "") and _f(dte) is not None else 0

    puffer_pct = ((kurs - strike) / kurs * 100.0) if kurs and kurs > 0 else 0.0
    annualized_pct = put_metrics(strike or 0, praemie or 0, dte)["annualized_pct"]
    bs_edge_pct = ((praemie - bs_preis) / bs_preis * 100.0) if (praemie is not None and bs_preis and bs_preis > 0) else None

    prob_assignment_pct, prob_source = None, "none"
    if kurs and kurs > 0 and iv and iv > 0 and dte > 0 and strike and strike > 0:
        try:
            prob_assignment_pct = ProbLessThan(strike, kurs, iv, dte, _RISK_FREE_RATE_EVAL) * 100.0
            prob_source = "bs"
        except (ValueError, ZeroDivisionError):
            pass
    if prob_assignment_pct is None and delta is not None:
        prob_assignment_pct = abs(delta) * 100.0
        prob_source = "delta"

    if annualized_pct < MIN_ANNUAL_RETURN_PCT:
        ampel = "❌"
    else:
        puffer_ok = puffer_pct >= min_puffer_pct
        bs_ok = (bs_edge_pct is not None and bs_edge_pct > 0)
        ampel = "✅" if (puffer_ok and bs_ok) else "⚠️"

    return {
        "puffer_pct": puffer_pct,
        "annualized_pct": annualized_pct,
        "bs_edge_pct": bs_edge_pct,
        "prob_assignment_pct": prob_assignment_pct,
        "prob_source": prob_source,
        "ampel": ampel,
    }
