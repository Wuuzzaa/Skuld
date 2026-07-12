"""Buch-verifizierte Roll-Formeln — Szenarien aus 'Optionen unschlagbar handeln', Kap. 3."""
from src.roll_support_calc import position_status, roll_candidate, ampel


def test_ampel_gruen_wenn_netto_positiv_und_gs_gesenkt():
    assert ampel(netto=10.0, breakeven_new=27.90, breakeven_old=29.00) == "✅"


def test_ampel_gelb_wenn_netto_positiv_aber_gs_nicht_besser():
    assert ampel(netto=10.0, breakeven_new=29.50, breakeven_old=29.00) == "⚠️"


def test_ampel_rot_wenn_netto_nicht_positiv():
    assert ampel(netto=-5.0, breakeven_new=27.0, breakeven_old=29.0) == "❌"


def test_position_status_verlust():
    # Put mit K=30 eröffnet für 100$, heute 210$ wert -> Verlust.
    pos = position_status(K=30.0, S=28.0, P_eroeffnung=100.0, P_heute=210.0, n=1)
    assert round(pos["breakeven_old"], 2) == 29.00      # 30 - 100/100
    assert round(pos["pnl_abs"], 2) == -110.00          # (100 - 210) * 1
    assert round(pos["inner_value"], 2) == 200.00       # max(0, 30-28)*100
    assert round(pos["time_value"], 2) == 10.00         # 210 - 200


def test_roll_candidate_szenario1_stufe1_gruen():
    # Buch-Szenario 1: K=30, Eröffnung 100$, heute 210$, Stufe1 K2=29, P_neu=220$.
    r = roll_candidate(stufe=1, K=30.0, K2=29.0,
                       P_eroeffnung=100.0, P_heute=210.0, P_neu=220.0, n=1)
    assert round(r["netto_abs"], 2) == 110.00           # 100 + 1*220 - 210
    assert round(r["breakeven_new"], 2) == 27.90        # 29 - 110/100
    assert r["ampel"] == "✅"


def test_roll_candidate_szenario3_stufe3_zwei_kontrakte():
    # Stufe3 K2=27.50, P_neu=285$, 2 Kontrakte, Eröffnung 100$, heute 400$.
    # Buch-Netto-Formel: P_eroeffnung + n*P_neu - P_heute = 100 + 2*285 - 400 = 270.
    r = roll_candidate(stufe=3, K=30.0, K2=27.50,
                       P_eroeffnung=100.0, P_heute=400.0, P_neu=285.0, n=2)
    assert round(r["netto_abs"], 2) == 270.00           # 100 + 2*285 - 400
    assert round(r["breakeven_new"], 2) == 26.15        # 27.50 - 270/(2*100)
    assert round(r["kapital_noetig"], 2) == 5500.00     # 27.50 * 2 * 100
    assert r["ampel"] == "✅"
