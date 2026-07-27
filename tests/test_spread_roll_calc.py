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


# ==========================================================================
# 4 Spread-Arten (Credit + Debit) — Generalisierung 2026-07-27
# ==========================================================================
from src.spread_roll_calc import (
    SPREAD_TYPES,
    spread_ampel_debit,
    spread_ampel_for,
)


# ── SPREAD_TYPES-Katalog ───────────────────────────────────────────────────
def test_spread_types_katalog_vollstaendig():
    assert set(SPREAD_TYPES) == {"bull_put", "bear_call", "bull_call", "bear_put"}
    assert SPREAD_TYPES["bull_put"]["strategy"] == "credit"
    assert SPREAD_TYPES["bear_call"]["strategy"] == "credit"
    assert SPREAD_TYPES["bull_call"]["strategy"] == "debit"
    assert SPREAD_TYPES["bear_put"]["strategy"] == "debit"
    assert SPREAD_TYPES["bull_put"]["contract"] == "put"
    assert SPREAD_TYPES["bear_call"]["contract"] == "call"
    assert SPREAD_TYPES["bull_call"]["contract"] == "call"
    assert SPREAD_TYPES["bear_put"]["contract"] == "put"


# ── Debit-Ampel (risiko-basiert) ────────────────────────────────────────────
def test_ampel_debit_bringt_geld_ist_gruen():
    # Roll bringt per Saldo Geld (added_debit <= 0) -> bestes Ergebnis.
    assert spread_ampel_debit(added_debit=-20.0, risk_new=300.0, risk_old=280.0) == "✅"


def test_ampel_debit_risiko_nicht_gestiegen_ist_gruen():
    # Kostet Geld, aber Gesamt-Risiko sinkt/gleich -> ok.
    assert spread_ampel_debit(added_debit=30.0, risk_new=280.0, risk_old=300.0) == "✅"


def test_ampel_debit_kleine_risiko_erhoehung_ist_gelb():
    # +8 % Risiko (<=10 %) -> ⚠️.
    assert spread_ampel_debit(added_debit=30.0, risk_new=324.0, risk_old=300.0) == "⚠️"


def test_ampel_debit_grosse_risiko_erhoehung_ist_rot():
    # +20 % Risiko -> ❌.
    assert spread_ampel_debit(added_debit=30.0, risk_new=360.0, risk_old=300.0) == "❌"


def test_ampel_for_dispatch_credit_vs_debit():
    # Credit -> alte Logik; Debit -> neue Logik.
    assert spread_ampel_for("bull_put", netto=15.0, gs_new=27.5, gs_old=28.0) == "✅"
    assert spread_ampel_for("bull_call", added_debit=-5.0, risk_new=300.0, risk_old=300.0) == "✅"


# ── Rückwärtskompatibilität: Default == Legacy Bull-Put ─────────────────────
def test_default_spread_type_matches_legacy_bull_put_position():
    legacy = spread_position_status(short_strike=30.0, width=5.0, credit_open=120.0,
                                    debit_now=180.0, n=1)
    typed = spread_position_status(short_strike=30.0, width=5.0, credit_open=120.0,
                                   debit_now=180.0, n=1, spread_type="bull_put")
    assert round(typed["gs_old"], 2) == round(legacy["gs_old"], 2) == 28.80
    assert round(typed["max_loss_open"], 2) == round(legacy["max_loss_open"], 2) == 380.0
    assert round(typed["pnl_abs"], 2) == round(legacy["pnl_abs"], 2) == -60.0


def test_default_spread_type_matches_legacy_bull_put_candidate():
    legacy = spread_roll_candidate(stufe=1, short_old=30.0, short_new=28.0, width=5.0,
                                   credit_open=120.0, debit_close=180.0, credit_new=150.0, n=1)
    typed = spread_roll_candidate(stufe=1, short_old=30.0, short_new=28.0, width=5.0,
                                  credit_open=120.0, debit_close=180.0, credit_new=150.0, n=1,
                                  spread_type="bull_put")
    assert round(typed["netto_abs"], 2) == round(legacy["netto_abs"], 2) == 90.0
    assert round(typed["gs_new"], 2) == round(legacy["gs_new"], 2) == 27.10
    assert typed["ampel"] == legacy["ampel"] == "✅"


# ── Bear-Call (Credit, Call): Breakeven ÜBER dem Short-Strike ────────────────
def test_bear_call_breakeven_ueber_short():
    pos = spread_position_status(short_strike=100.0, width=5.0, credit_open=120.0,
                                 debit_now=80.0, n=1, spread_type="bear_call")
    # Bear-Call GS = Short + Credit/Aktie = 100 + 1.20 = 101.20
    assert round(pos["gs_old"], 2) == 101.20
    assert round(pos["max_loss_open"], 2) == 380.0        # (5 - 1.20)*100
    assert round(pos["pnl_abs"], 2) == 40.0               # (120-80)*1


# ── Bull-Call (Debit, Call): Risiko = Debit, Breakeven aus Long ──────────────
def test_bull_call_position_risiko_gleich_debit():
    # Long 140 (gekauft) / Short 150 (verkauft), Breite 10. Debit 400$ gezahlt.
    # Aktueller Schließungs-Credit (Wert heute) 250$ -> Verlust.
    pos = spread_position_status(short_strike=150.0, long_strike=140.0, width=10.0,
                                 credit_open=400.0, debit_now=250.0, n=1,
                                 spread_type="bull_call")
    assert round(pos["max_loss_open"], 2) == 400.0        # = gezahlter Debit, KEIN width-Term
    assert round(pos["gs_old"], 2) == 144.0               # Long 140 + Debit 4.00
    assert round(pos["pnl_abs"], 2) == -150.0             # (250 - 400)*1  (Wert heute - Debit)


# ── Bear-Put (Debit, Put): Breakeven aus Long, abwärts ──────────────────────
def test_bear_put_position_breakeven_aus_long():
    # Long 150 (gekauft, höher) / Short 140 (verkauft, tiefer), Breite 10, Debit 400$.
    pos = spread_position_status(short_strike=140.0, long_strike=150.0, width=10.0,
                                 credit_open=400.0, debit_now=500.0, n=1,
                                 spread_type="bear_put")
    assert round(pos["max_loss_open"], 2) == 400.0        # = Debit
    assert round(pos["gs_old"], 2) == 146.0               # Long 150 - Debit 4.00
    assert round(pos["pnl_abs"], 2) == 100.0              # (500 - 400)*1  (im Gewinn)


# ── Debit-Roll-Kandidat: Zusatz-Debit + Breakeven + risiko-basierte Ampel ────
def test_bull_call_roll_candidate_added_debit():
    # Alt Bull-Call Long 140/Short 150, Debit 400 gezahlt. Schließen bringt heute 250 (Credit).
    # Neu Long 138/Short 148, neuer Debit 380$/Kontrakt.
    r = spread_roll_candidate(
        stufe=1, short_old=150.0, short_new=148.0, long_old=140.0, long_new=138.0,
        width=10.0, credit_open=400.0, debit_close=250.0, credit_new=380.0, n=1,
        spread_type="bull_call", roll_kind="vertikal",
    )
    # Zusatz-Debit = n*debit_new - credit_close(alt schließen) = 380 - 250 = 130 (zahlst du)
    assert round(r["added_debit_abs"], 2) == 130.0
    assert round(r["risk_new"], 2) == 380.0               # neuer Debit = neues Risiko
    assert round(r["breakeven_new"], 2) == 141.80         # Long 138 + 3.80
    assert r["roll_kind"] == "vertikal"
    assert r["spread_type"] == "bull_call"


def test_debit_roll_candidate_ampel_risiko_basiert():
    # Neuer Debit (Risiko) niedriger als alter -> trotz Zusatz-Debit grün.
    r = spread_roll_candidate(
        stufe=1, short_old=150.0, short_new=148.0, long_old=140.0, long_new=138.0,
        width=10.0, credit_open=400.0, debit_close=250.0, credit_new=380.0, n=1,
        spread_type="bull_call",
    )
    # risk_new 380 vs risk_old 400 -> gesunken -> ✅
    assert r["ampel"] == "✅"


# ── Debit-Kontoauszug: invertierte Zeilen-Labels ────────────────────────────
def test_spread_pnl_breakdown_debit_labels():
    b = spread_pnl_breakdown(short_strike=150.0, long_strike=140.0, width=10.0,
                             credit_open=400.0, debit_now=250.0, n=1,
                             spread_type="bull_call")
    labels = [l["label"] for l in b["lines"]]
    assert any("bezahlt" in l.lower() for l in labels)     # "Beim Öffnen bezahlt (Debit)"
    assert any("bringt heute" in l.lower() for l in labels)  # "Schließen bringt heute (Credit)"
    assert round(b["pnl_abs"], 2) == -150.0                # (250 - 400)


# ── Neutrale Alias-Keys im Return ───────────────────────────────────────────
def test_candidate_hat_neutrale_alias_keys():
    r = spread_roll_candidate(stufe=1, short_old=30.0, short_new=28.0, width=5.0,
                              credit_open=120.0, debit_close=180.0, credit_new=150.0, n=1,
                              spread_type="bull_put", roll_kind="vertikal")
    assert "breakeven" in r and "risk" in r and "net_cash" in r
    assert "roll_kind" in r and "spread_type" in r
    assert round(r["breakeven"], 2) == round(r["gs_new"], 2)
