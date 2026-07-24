"""Scoring-Kern des CSP-Screeners — pure Python, keine DB."""
import pandas as pd
from src.put_screener import (
    score_candidates,
    score_breakdown,
    put_metrics,
    SCORE_MAX,
    shortlist_score,
    shortlist_breakdown,
    earnings_ok,
    delta_ok,
)


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


def test_put_metrics_basic():
    m = put_metrics(strike=30.0, premium=1.20, dte=40)
    assert round(m["premium_pct"], 2) == 4.0          # 1.20/30*100
    assert round(m["breakeven"], 2) == 28.80          # 30 - 1.20
    assert round(m["capital_required"], 2) == 3000.0  # 30*100
    assert round(m["annualized_pct"], 1) == 36.5      # 4.0 * 365/40


def test_put_metrics_guards_zero():
    m = put_metrics(strike=0.0, premium=1.0, dte=0)
    assert m["premium_pct"] == 0.0
    assert m["annualized_pct"] == 0.0


# ==========================================================================
# Shortlist-Score (IV + Sektor + Rendite + BS-Edge) — Feature C/D
# ==========================================================================
def test_shortlist_score_preserves_legacy_points():
    # IV>=60 (3) + Leading (2) + ann>=20 (2) = 7, ohne BS-Edge.
    r = {"iv_rank": 65, "sektor_quadrant": "Leading", "annualized_pct": 22.0}
    assert shortlist_score(r) == 7


def test_shortlist_score_mid_tiers():
    # IV 45 (2) + Improving (1) + ann 15 (1) = 4.
    r = {"iv_rank": 45, "sektor_quadrant": "Improving", "annualized_pct": 15.0}
    assert shortlist_score(r) == 4


def test_shortlist_score_adds_bs_edge_points():
    # Basis wie legacy 7, plus positiver BS-Edge > 5% -> +2.
    r = {"iv_rank": 65, "sektor_quadrant": "Leading", "annualized_pct": 22.0, "bs_edge_pct": 8.0}
    assert shortlist_score(r) == 9


def test_shortlist_score_small_bs_edge_one_point():
    r = {"iv_rank": 65, "sektor_quadrant": "Leading", "annualized_pct": 22.0, "bs_edge_pct": 2.0}
    assert shortlist_score(r) == 8  # 7 + 1


def test_shortlist_score_negative_bs_edge_no_points():
    r = {"iv_rank": 65, "sektor_quadrant": "Leading", "annualized_pct": 22.0, "bs_edge_pct": -3.0}
    assert shortlist_score(r) == 7  # unverändert


def test_shortlist_score_missing_bs_edge_is_zero_contribution():
    r = {"iv_rank": 65, "sektor_quadrant": "Leading", "annualized_pct": 22.0}  # kein bs_edge_pct
    assert shortlist_score(r) == 7


def test_shortlist_breakdown_sums_to_score():
    r = {"iv_rank": 45, "sektor_quadrant": "Improving", "annualized_pct": 22.0, "bs_edge_pct": 8.0}
    bd = shortlist_breakdown(r)
    assert sum(item["punkte"] for item in bd) == shortlist_score(r)
    # jede Zeile hat label + punkte
    assert all("label" in i and "punkte" in i for i in bd)


def test_shortlist_breakdown_labels_present():
    r = {"iv_rank": 65, "sektor_quadrant": "Leading", "annualized_pct": 22.0, "bs_edge_pct": 8.0}
    labels = {i["label"] for i in shortlist_breakdown(r)}
    assert any("IV" in l for l in labels)
    assert any("Sektor" in l for l in labels)
    assert any("Rendite" in l for l in labels)
    assert any("BS" in l for l in labels)


# ==========================================================================
# Earnings-Ausschluss (A) + Delta-Filter (B) — reine Prädikate
# ==========================================================================
def test_earnings_ok_no_earnings_in_lifetime():
    # Earnings in 50 Tagen, Put läuft 30 Tage -> ok (Earnings nach Verfall).
    assert earnings_ok({"days_to_earnings": 50, "put_dte": 30}) is True


def test_earnings_ok_earnings_before_expiry_fails():
    assert earnings_ok({"days_to_earnings": 10, "put_dte": 30}) is False


def test_earnings_ok_missing_data_is_permissive():
    # Kein Earnings-Datum bekannt -> nicht ausschließen (wie covered_call_scanner: IS NULL).
    assert earnings_ok({"days_to_earnings": None, "put_dte": 30}) is True
    assert earnings_ok({"put_dte": 30}) is True


def test_delta_ok_within_limit():
    # Put-Delta negativ; |Delta| 0.18 <= 0.20 -> ok.
    assert delta_ok({"put_delta": -0.18}, max_abs_delta=0.20) is True


def test_delta_ok_exceeds_limit():
    assert delta_ok({"put_delta": -0.35}, max_abs_delta=0.20) is False


def test_delta_ok_missing_is_permissive():
    assert delta_ok({}, max_abs_delta=0.20) is True
