"""Scoring-Kern des CSP-Screeners — pure Python, keine DB."""
import pandas as pd
from src.put_screener import score_candidates, score_breakdown, SCORE_MAX


def _sample_row():
    # Eine Aktie, die die meisten Kriterien erfüllt.
    return {
        "symbol": "TEST",
        "revenue_growth_pct": 8.3,     # > 0 -> erfüllt (aktuell)
        "eps_growth_pct": 5.0,         # > 0 -> erfüllt (aktuell)
        "payout_ratio_pct": 40.0,      # <= 60 -> erfüllt
        "operating_cashflow": 1000.0,  # > 0
        "free_cashflow": 500.0,        # > 0 -> Cashflow erfüllt (aktuell)
        "trailing_pe": 25.0,           # <= 40 -> erfüllt
        "iv_rank": 30.0,               # <= 60 -> erfüllt
        "rsi_14": 58.0,                # < 70 -> erfüllt
        "macd_histogram": 0.2,         # > 0 -> erfüllt
        "sector": "Technology",        # kein Cannabis -> erfüllt
    }


def test_score_breakdown_alle_kriterien_erfuellt():
    bd = score_breakdown(_sample_row(), pe_max=40.0)
    assert len(bd) == SCORE_MAX
    assert all(item["erreicht"] for item in bd)
    assert all(item["moeglich"] == 1 for item in bd)


def test_score_breakdown_kgv_zu_hoch_faellt_raus():
    row = _sample_row()
    row["trailing_pe"] = 80.0  # > 40
    bd = score_breakdown(row, pe_max=40.0)
    pe = next(i for i in bd if i["key"] == "crit_pe")
    assert pe["erreicht"] is False
    assert pe["ist_wert"] == 80.0


def test_score_breakdown_markiert_annahme_aktuell():
    bd = score_breakdown(_sample_row(), pe_max=40.0)
    rev = next(i for i in bd if i["key"] == "crit_revenue_growth")
    assert rev["annahme"] == "aktuell"
    pe = next(i for i in bd if i["key"] == "crit_pe")
    assert pe["annahme"] == ""  # KGV ist keine Näherung


def test_breakdown_summe_gleich_score():
    df = pd.DataFrame([_sample_row()])
    scored = score_candidates(df, pe_max=40.0)
    score = int(scored.iloc[0]["score"])
    bd = score_breakdown(_sample_row(), pe_max=40.0)
    assert sum(1 for i in bd if i["erreicht"]) == score
