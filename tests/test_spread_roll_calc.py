"""Bull-Put-Spread-Roll-Formeln — reine Rechenlogik, keine DB/Streamlit.

Spread = Short-Put (verkauft) + Long-Put (gekauft) bei Short-Breite, Breite fix.
Rollen = beide Beine gemeinsam auf neue Laufzeit/Strikes; Breite bleibt konstant.

Ampel wie Buch-CSP, aber auf den NETTO-CREDIT des ganzen Spreads bezogen:
    ✅ Netto-Credit > 0 UND neue Gewinnschwelle < alte
    ⚠️ Netto-Credit > 0 aber Gewinnschwelle nicht besser
    ❌ Netto-Credit <= 0
Max-Loss (= Risiko) als Kennzahl daneben: (Breite − Gesamt-Credit/Aktie) · n · 100.
"""
from src.spread_roll_calc import (
    spread_ampel,
    spread_position_status,
    spread_roll_candidate,
)


# --------------------------------------------------------------------------
# Ampel
# --------------------------------------------------------------------------
def test_ampel_gruen_credit_positiv_und_gs_gesenkt():
    assert spread_ampel(netto=15.0, gs_new=27.5, gs_old=28.0) == "✅"


def test_ampel_gelb_credit_positiv_gs_nicht_besser():
    assert spread_ampel(netto=15.0, gs_new=28.5, gs_old=28.0) == "⚠️"


def test_ampel_rot_credit_nicht_positiv():
    assert spread_ampel(netto=-5.0, gs_new=27.0, gs_old=28.0) == "❌"


# --------------------------------------------------------------------------
# Position-Status (bestehender Spread)
# --------------------------------------------------------------------------
def test_position_status_basic():
    # Short 30 / Long 25 (Breite 5), Eröffnungs-Credit 1.20/Aktie = 120$/Kontrakt.
    # Aktueller Schließungs-Debit 1.80/Aktie = 180$ -> Verlust.
    pos = spread_position_status(
        short_strike=30.0, width=5.0, credit_open=120.0,
        debit_now=180.0, n=1,
    )
    assert round(pos["gs_old"], 2) == 28.80          # 30 - 120/100
    assert round(pos["max_loss_open"], 2) == 380.0   # (5 - 1.20)*100*1
    assert round(pos["pnl_abs"], 2) == -60.0         # (120 - 180)*1


# --------------------------------------------------------------------------
# Roll-Kandidat
# --------------------------------------------------------------------------
def test_roll_candidate_stufe1_credit_and_gs():
    # Alt: Short 30 / Breite 5, Eröffnung 120$. Rückkauf (Debit) 180$.
    # Neu Stufe 1: Short 28 / Breite 5, neuer Credit 150$/Kontrakt.
    r = spread_roll_candidate(
        stufe=1, short_old=30.0, short_new=28.0, width=5.0,
        credit_open=120.0, debit_close=180.0, credit_new=150.0, n=1,
    )
    # Netto = 120 + 150 - 180 = 90 (Buch-Analogie: credit_open + n*credit_new - debit_close)
    assert round(r["netto_abs"], 2) == 90.0
    # GS_neu = Short_neu 28 - netto/(n*100) = 28 - 0.90 = 27.10
    assert round(r["gs_new"], 2) == 27.10
    assert round(r["gs_old"], 2) == 28.80            # 30 - 1.20
    # Max-Loss neu = (Breite - netto/(n*100)) * 100 * n = (5 - 0.90)*100 = 410
    assert round(r["max_loss"], 2) == 410.0
    assert r["ampel"] == "✅"                          # Credit>0 und GS gesenkt (27.10 < 28.80)


def test_roll_candidate_stufe3_doubles_contracts():
    # Stufe 3: 2n Kontrakte. n hier = neue Kontraktzahl (2).
    r = spread_roll_candidate(
        stufe=3, short_old=30.0, short_new=28.0, width=5.0,
        credit_open=120.0, debit_close=180.0, credit_new=150.0, n=2,
    )
    # Netto = 120 + 2*150 - 180 = 240 (Eröffnung 1x geschlossen, 2x neu eröffnet)
    assert round(r["netto_abs"], 2) == 240.0
    # Max-Loss skaliert mit n: (5 - credit/Aktie)*100*2
    assert r["max_loss"] > 0
    assert r["stufe"] == 3


def test_roll_candidate_negative_credit_is_rot():
    # Rückkauf teurer als neuer Credit + Eröffnung -> Netto negativ.
    r = spread_roll_candidate(
        stufe=1, short_old=30.0, short_new=28.0, width=5.0,
        credit_open=100.0, debit_close=400.0, credit_new=120.0, n=1,
    )
    assert r["netto_abs"] < 0
    assert r["ampel"] == "❌"


# ── spread_pnl_breakdown (Kontoauszug der bestehenden Spread-Position) ──────
from src.spread_roll_calc import spread_pnl_breakdown


def test_spread_pnl_breakdown_gewinn_summe():
    # Short 50 / Long 45 (Breite 5), Credit 150$ vereinnahmt, heute Debit 60$, 1 Spread.
    b = spread_pnl_breakdown(short_strike=50.0, width=5.0, credit_open=150.0, debit_now=60.0, n=1)
    assert b["im_gewinn"] is True
    assert round(b["pnl_abs"], 2) == 90.00          # (150 - 60) * 1
    assert round(b["gs_old"], 2) == 48.50           # 50 - 150/100
    einnahme = next(l for l in b["lines"] if l["label"] == "Beim Öffnen eingenommen (Credit)")
    schliessen = next(l for l in b["lines"] if l["label"] == "Schließen kostet heute (Debit)")
    assert round(einnahme["wert"], 2) == 150.00
    assert round(schliessen["wert"], 2) == -60.00
    assert round(einnahme["wert"] + schliessen["wert"], 2) == round(b["pnl_abs"], 2)


def test_spread_pnl_breakdown_verlust_grund():
    b = spread_pnl_breakdown(short_strike=50.0, width=5.0, credit_open=100.0, debit_now=180.0, n=1)
    assert b["im_gewinn"] is False
    assert round(b["pnl_abs"], 2) == -80.00
    assert "teurer" in b["grund"].lower() or "verlust" in b["grund"].lower()


def test_spread_pnl_breakdown_skaliert_mit_n():
    b = spread_pnl_breakdown(short_strike=50.0, width=5.0, credit_open=150.0, debit_now=60.0, n=3)
    assert round(b["pnl_abs"], 2) == 270.00         # (150-60)*3
    einnahme = next(l for l in b["lines"] if l["label"] == "Beim Öffnen eingenommen (Credit)")
    assert round(einnahme["wert"], 2) == 450.00     # 150*3


def test_spread_pnl_breakdown_hat_maxloss_zeile():
    b = spread_pnl_breakdown(short_strike=50.0, width=5.0, credit_open=150.0, debit_now=60.0, n=1)
    ml = next(l for l in b["lines"] if l["label"] == "Max-Loss (offen)")
    assert round(ml["wert"], 2) == 350.00           # (5 - 150/100) * 100 * 1
    assert ml["einheit"] == "$ gesamt"
