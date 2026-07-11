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
    ("crit_revenue_growth",  "Umsatzwachstum (aktuell)",       lambda r, pe: _is_pos(r.get("revenue_growth_pct"))),
    ("crit_eps_growth",      "EPS-Wachstum (aktuell)",         lambda r, pe: _is_pos(r.get("eps_growth_pct"))),
    ("crit_payout",          "Payout <= 60 %",                 lambda r, pe: _le(r.get("payout_ratio_pct"), 60.0)),
    ("crit_cashflow",        "Cashflow positiv (aktuell)",     lambda r, pe: _is_pos(r.get("operating_cashflow")) and _is_pos(r.get("free_cashflow"))),
    ("crit_pe",              "KGV moderat",                    lambda r, pe: _le(r.get("trailing_pe"), pe)),
    ("crit_not_volatile",    "Nicht hochvolatil (IV-Rank)",    lambda r, pe: _le(r.get("iv_rank"), 60.0)),
    ("crit_rsi",             "RSI nicht überkauft",            lambda r, pe: pd.notna(r.get("rsi_14")) and float(r.get("rsi_14")) < RSI_OVERBOUGHT),
    ("crit_macd",            "MACD steigend",                  lambda r, pe: _is_pos(r.get("macd_histogram"))),
    ("crit_sector",          "Kein Cannabis/Nischen-Sektor",   lambda r, pe: _sector_ok(r.get("sector"))),
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
    for col, _label, fn in _CRITERIA:
        out[col] = out.apply(lambda r, f=fn: bool(f(r, pe_max)), axis=1)

    crit_cols = [c for c, _, _ in _CRITERIA]
    out["score"] = out[crit_cols].sum(axis=1).astype(int)
    out["score_max"] = SCORE_MAX

    return out.sort_values("score", ascending=False).reset_index(drop=True)


def criterion_labels() -> dict:
    """Mapping crit_-Spalte -> menschenlesbare Beschriftung (für die UI)."""
    return {col: label for col, label, _ in _CRITERIA}
