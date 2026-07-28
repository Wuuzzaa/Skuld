"""
Vertikale Spreads rollen — reine Rechenlogik, keine DB, kein Streamlit.

Unterstützt 4 vertikale Spread-Arten (2026-07-27 generalisiert; vorher nur Bull-Put):

    key         Kontrakt  Strategie  primär (Klick 1)  2. Bein       Breakeven
    ---------   --------  ---------  ----------------  ------------  --------------
    bull_put    put       credit     Short (höher)     Long tiefer   short − credit
    bear_call   call      credit     Short (tiefer)    Long höher    short + credit
    bull_call   call      debit      Long (tiefer)     Short höher   long  + debit
    bear_put    put       debit      Long (höher)      Short tiefer  long  − debit

Prämien überall ABSOLUT in $/Kontrakt (z.B. 120.0 = $1,20/Aktie × 100), Breite in
$/Aktie. Beim Rollen wandern beide Beine gemeinsam; die Breite bleibt konstant.

CREDIT-Spreads (bull_put, bear_call): du nimmst beim Öffnen Prämie ein.
    Max-Risiko = (Breite − Credit/Aktie) × 100 × n.  Ein "guter" Roll hält den
    Netto-Credit positiv und senkt die Gewinnschwelle (Ampel = spread_ampel).

DEBIT-Spreads (bull_call, bear_put): du ZAHLST beim Öffnen Prämie.
    Max-Risiko = gezahlter Debit (begrenzt, KEIN Breite-Term).  Max-Gewinn =
    (Breite − Debit/Aktie) × 100 × n.  Ein "guter" Roll erhöht das Gesamt-Risiko
    nicht (Ampel = spread_ampel_debit, risiko-basiert).

WICHTIG (Namens-Konvention aus der Bull-Put-Historie, aus Rückwärtskompat NICHT
umbenannt): die Parameter `credit_open` / `debit_now` / `debit_close` / `credit_new`
tragen bei DEBIT-Spreads eine gespiegelte Bedeutung:
    credit_open  → beim Öffnen BEZAHLTER Debit ($/Kontrakt)
    debit_now    → aktueller Schließungs-CREDIT (was das Schließen heute einbringt)
    debit_close  → Schließungs-Credit des alten Spreads
    credit_new   → beim Öffnen des NEUEN Spreads zu zahlender Debit
Die Return-Dicts liefern zusätzlich NEUTRALE Aliase (`breakeven`, `risk`, `net_cash`)
sowie debit-spezifische Keys (`added_debit_abs`, `risk_new`, `breakeven_new`).
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Katalog der 4 vertikalen Spread-Arten
# ---------------------------------------------------------------------------
# contract:  Optionsseite, auf der beide Beine liegen ('put' oder 'call').
# strategy:  'credit' (Prämie erhalten) oder 'debit' (Prämie gezahlt).
# primary:   welches Bein zuerst geklickt wird ('short' bei Credit, 'long' bei Debit).
# second_dir:Richtung des 2. Beins relativ zum ersten ('below' = tieferer Strike,
#            'above' = höherer Strike).
# label:     UI-Anzeigename.
# be_dir:    Breakeven relativ zum primären Strike: +1 = darüber, -1 = darunter.
SPREAD_TYPES: dict[str, dict] = {
    "bull_put": {
        "contract": "put", "strategy": "credit", "primary": "short",
        "second_dir": "below", "be_dir": -1, "label": "Bull-Put (Credit)",
        "opposite": "bear_call",
    },
    "bear_call": {
        "contract": "call", "strategy": "credit", "primary": "short",
        "second_dir": "above", "be_dir": +1, "label": "Bear-Call (Credit)",
        "opposite": "bull_put",
    },
    "bull_call": {
        "contract": "call", "strategy": "debit", "primary": "long",
        "second_dir": "above", "be_dir": +1, "label": "Bull-Call (Debit)",
        "opposite": "bear_put",
    },
    "bear_put": {
        "contract": "put", "strategy": "debit", "primary": "long",
        "second_dir": "below", "be_dir": -1, "label": "Bear-Put (Debit)",
        "opposite": "bull_call",
    },
}


def _is_credit(spread_type: str) -> bool:
    """True für Credit-Spreads (bull_put, bear_call)."""
    return SPREAD_TYPES.get(spread_type, SPREAD_TYPES["bull_put"])["strategy"] == "credit"


# ---------------------------------------------------------------------------
# Ampel
# ---------------------------------------------------------------------------
def spread_ampel(netto: float, gs_new: float, gs_old: float) -> str:
    """Bewertet einen CREDIT-Spread-Roll (Netto-Credit + Gewinnschwelle)."""
    if netto <= 0:
        return "❌"
    if gs_new < gs_old:
        return "✅"
    return "⚠️"


def spread_ampel_debit(added_debit: float, risk_new: float, risk_old: float) -> str:
    """Bewertet einen DEBIT-Spread-Roll risiko-basiert (User-Entscheidung 2026-07-27).

    ✅ wenn der Roll KEIN zusätzliches Geld kostet (added_debit ≤ 0) ODER das
       Gesamt-Risiko nicht steigt (risk_new ≤ risk_old).
    ⚠️ bei kleiner Risiko-Erhöhung (bis +10 %).
    ❌ bei deutlicher Risiko-Erhöhung.

    Args:
        added_debit: zusätzlich zu zahlender Netto-Debit für den Roll ($ gesamt);
                     ≤ 0 = der Roll bringt per Saldo Geld ein.
        risk_new:    Max-Risiko der NEUEN Position ($ gesamt).
        risk_old:    Max-Risiko der ALTEN Position ($ gesamt).
    """
    if added_debit <= 0 or risk_new <= risk_old:
        return "✅"
    if risk_new <= risk_old * 1.10:
        return "⚠️"
    return "❌"


def spread_ampel_for(spread_type: str, *, netto=None, gs_new=None, gs_old=None,
                     added_debit=None, risk_new=None, risk_old=None) -> str:
    """Dispatcht auf die richtige Ampel je Spread-Art."""
    if _is_credit(spread_type):
        return spread_ampel(netto, gs_new, gs_old)
    return spread_ampel_debit(added_debit, risk_new, risk_old)


# ---------------------------------------------------------------------------
# Bestehende Position
# ---------------------------------------------------------------------------
def spread_position_status(short_strike: float, width: float, credit_open: float,
                           debit_now: float, n: int, spread_type: str = "bull_put",
                           long_strike: float | None = None) -> dict:
    """Kennzahlen der bestehenden Spread-Position.

    Args:
        short_strike: Strike des Short-Beins (verkauft).
        width:        Spread-Breite in $/Aktie (|Short − Long|).
        credit_open:  CREDIT: bei Eröffnung vereinnahmter Netto-Credit ($/Kontrakt).
                      DEBIT:  bei Eröffnung BEZAHLTER Netto-Debit ($/Kontrakt).
        debit_now:    CREDIT: aktueller Schließungs-Debit ($/Kontrakt).
                      DEBIT:  aktueller Schließungs-Credit / Wert heute ($/Kontrakt).
        n:            Anzahl Spreads (Kontrakte).
        spread_type:  eine der Keys aus SPREAD_TYPES (Default bull_put).
        long_strike:  Strike des Long-Beins — nur für DEBIT-Breakeven nötig.

    Returns:
        dict mit gs_old, breakeven (Alias), max_loss_open, pnl_abs, pnl_pct, spread_type.
    """
    meta = SPREAD_TYPES.get(spread_type, SPREAD_TYPES["bull_put"])

    if meta["strategy"] == "credit":
        # Breakeven relativ zum Short-Strike (bull_put: darunter, bear_call: darüber).
        gs_old = short_strike + meta["be_dir"] * (credit_open / 100.0)
        max_loss_open = max(0.0, (width - credit_open / 100.0)) * 100.0 * n
        pnl_abs = (credit_open - debit_now) * n
        base = credit_open
    else:
        # DEBIT: credit_open = gezahlter Debit, debit_now = Wert/Credit heute.
        debit_paid = credit_open
        value_now = debit_now
        long_k = long_strike if long_strike is not None else short_strike
        gs_old = long_k + meta["be_dir"] * (debit_paid / 100.0)
        max_loss_open = debit_paid * n                 # Risiko = gezahlter Debit, begrenzt
        pnl_abs = (value_now - debit_paid) * n
        base = debit_paid

    pnl_pct = (pnl_abs / (base * n) * 100.0) if base else 0.0
    return {
        "gs_old": gs_old,
        "breakeven": gs_old,
        "max_loss_open": max_loss_open,
        "pnl_abs": pnl_abs,
        "pnl_pct": pnl_pct,
        "spread_type": spread_type,
    }


def spread_pnl_breakdown(short_strike: float, width: float, credit_open: float,
                         debit_now: float, n: int, spread_type: str = "bull_put",
                         long_strike: float | None = None) -> dict:
    """Kontobuch-Herleitung des G/V der bestehenden Spread-Position (Anzeige-Hilfe).

    Nutzt spread_position_status(); ändert keine Zahlen. Einheiten explizit.
    Returns dict mit pnl_abs, pnl_pct, gs_old, max_loss_open, im_gewinn, grund, lines.
    lines: [{label, formel, wert, einheit, summe}]. summe=True → Zwischensumme.
    """
    pos = spread_position_status(short_strike=short_strike, width=width,
                                 credit_open=credit_open, debit_now=debit_now, n=n,
                                 spread_type=spread_type, long_strike=long_strike)
    im_gewinn = pos["pnl_abs"] >= 0

    if _is_credit(spread_type):
        credit_share = credit_open / 100.0
        debit_share = debit_now / 100.0
        einnahme = credit_open * n
        schliessen = -(debit_now * n)
        diff_share = credit_share - debit_share
        if im_gewinn:
            grund = (f"Im Gewinn: der Spread lässt sich für ${abs(diff_share):.2f}/Aktie "
                     f"billiger schließen als du beim Öffnen eingenommen hast "
                     f"(Zeitwert-Verfall / Kurs über Short-Strike).")
        else:
            grund = (f"Im Verlust: das Schließen kostet ${abs(diff_share):.2f}/Aktie mehr "
                     f"als der Eröffnungs-Credit (Kurs Richtung Short-Strike gefallen).")
        lines = [
            {"label": "Beim Öffnen eingenommen (Credit)",
             "formel": f"{credit_share:.2f} $/Aktie × 100 × {n}",
             "wert": einnahme, "einheit": "$ gesamt", "summe": False},
            {"label": "Schließen kostet heute (Debit)",
             "formel": f"{debit_share:.2f} $/Aktie × 100 × {n}",
             "wert": schliessen, "einheit": "$ gesamt", "summe": False},
            {"label": "G/V wenn du JETZT schließt",
             "formel": f"{einnahme:.0f} − {abs(schliessen):.0f}",
             "wert": pos["pnl_abs"], "einheit": "$ gesamt", "summe": True},
            {"label": "Alte Gewinnschwelle",
             "formel": f"Short {short_strike:.2f} {'−' if SPREAD_TYPES[spread_type]['be_dir'] < 0 else '+'} Credit {credit_share:.2f}",
             "wert": pos["gs_old"], "einheit": "$/Aktie", "summe": False},
            {"label": "Max-Loss (offen)",
             "formel": f"(Breite {width:.2f} − Credit {credit_share:.2f}) × 100 × {n}",
             "wert": pos["max_loss_open"], "einheit": "$ gesamt", "summe": False},
        ]
    else:
        # DEBIT: credit_open = gezahlter Debit, debit_now = Wert/Credit heute.
        debit_paid = credit_open
        value_now = debit_now
        long_k = long_strike if long_strike is not None else short_strike
        debit_share = debit_paid / 100.0
        value_share = value_now / 100.0
        bezahlt = -(debit_paid * n)
        bringt = value_now * n
        diff_share = value_share - debit_share
        if im_gewinn:
            grund = (f"Im Gewinn: der Spread ist heute ${abs(diff_share):.2f}/Aktie mehr "
                     f"wert als der gezahlte Debit (Kurs in die gewünschte Richtung gelaufen).")
        else:
            grund = (f"Im Verlust: der Spread bringt beim Schließen ${abs(diff_share):.2f}/Aktie "
                     f"weniger als der gezahlte Debit (Kurs gegen die Position).")
        lines = [
            {"label": "Beim Öffnen bezahlt (Debit)",
             "formel": f"{debit_share:.2f} $/Aktie × 100 × {n}",
             "wert": bezahlt, "einheit": "$ gesamt", "summe": False},
            {"label": "Schließen bringt heute (Credit)",
             "formel": f"{value_share:.2f} $/Aktie × 100 × {n}",
             "wert": bringt, "einheit": "$ gesamt", "summe": False},
            {"label": "G/V wenn du JETZT schließt",
             "formel": f"{bringt:.0f} − {abs(bezahlt):.0f}",
             "wert": pos["pnl_abs"], "einheit": "$ gesamt", "summe": True},
            {"label": "Alte Gewinnschwelle",
             "formel": f"Long {long_k:.2f} {'+' if SPREAD_TYPES[spread_type]['be_dir'] > 0 else '−'} Debit {debit_share:.2f}",
             "wert": pos["gs_old"], "einheit": "$/Aktie", "summe": False},
            {"label": "Max-Loss (offen)",
             "formel": f"gezahlter Debit {debit_share:.2f} × 100 × {n}",
             "wert": pos["max_loss_open"], "einheit": "$ gesamt", "summe": False},
        ]

    return {
        "pnl_abs": pos["pnl_abs"], "pnl_pct": pos["pnl_pct"], "gs_old": pos["gs_old"],
        "max_loss_open": pos["max_loss_open"], "im_gewinn": im_gewinn,
        "grund": grund, "lines": lines, "spread_type": spread_type,
    }


# ---------------------------------------------------------------------------
# Roll-Kandidat
# ---------------------------------------------------------------------------
# Mapping benannter Roll-Prinzipien auf die alte Stufen-Nummer (Rückwärtskompat).
_ROLL_KIND_TO_STUFE = {"vertikal": 1, "horizontal": 2, "diagonal": 2, "verdoppeln": 3,
                       "kontra": 0}


def spread_roll_candidate(stufe: int, short_old: float, short_new: float, width: float,
                          credit_open: float, debit_close: float, credit_new: float,
                          n: int, spread_type: str = "bull_put",
                          roll_kind: str | None = None,
                          long_old: float | None = None,
                          long_new: float | None = None) -> dict:
    """Berechnet einen konkreten Spread-Roll-Kandidaten.

    Args:
        stufe:       1/2/3 (Rückwärtskompat; UI nutzt jetzt roll_kind).
        short_old:   Alter Short-Strike.
        short_new:   Neuer Short-Strike.
        width:       Spread-Breite (fix, $/Aktie).
        credit_open: CREDIT: ursprünglich vereinnahmter Netto-Credit ($/Kontrakt).
                     DEBIT:  ursprünglich gezahlter Netto-Debit ($/Kontrakt).
        debit_close: CREDIT: Schließungs-Debit des alten Spreads ($/Kontrakt, 1er-Paket).
                     DEBIT:  Schließungs-Credit des alten Spreads (bringt Geld).
        credit_new:  CREDIT: Netto-Credit des NEUEN Spreads ($/Kontrakt).
                     DEBIT:  zu zahlender Netto-Debit des NEUEN Spreads ($/Kontrakt).
        n:           Kontraktzahl des NEUEN Spreads (Verdoppeln: 2n).
        spread_type: eine der Keys aus SPREAD_TYPES (Default bull_put).
        roll_kind:   'vertikal'|'horizontal'|'diagonal'|'kontra'|'verdoppeln' (UI-Label).
        long_old/long_new: Long-Strikes — für DEBIT-Breakeven nötig.

    Returns:
        dict mit stufe, netto_abs, netto_pro_aktie, gs_new, gs_old, max_loss, width,
        ampel, spread_type, roll_kind + neutrale Aliase breakeven/risk/net_cash +
        debit-spezifisch added_debit_abs/risk_new/breakeven_new.
    """
    meta = SPREAD_TYPES.get(spread_type, SPREAD_TYPES["bull_put"])
    if roll_kind is None:
        roll_kind = {1: "vertikal", 2: "horizontal", 3: "verdoppeln"}.get(stufe, "vertikal")

    if meta["strategy"] == "credit":
        # Buch-Analogie: altes 1er-Paket schließen, neues n-Paket eröffnen.
        netto_abs = credit_open + n * credit_new - debit_close
        netto_pro_aktie = netto_abs / (n * 100.0)
        gs_new = short_new + meta["be_dir"] * netto_pro_aktie
        gs_old = short_old + meta["be_dir"] * (credit_open / 100.0)
        max_loss = max(0.0, (width - netto_pro_aktie)) * 100.0 * n
        ampel = spread_ampel(netto_abs, gs_new, gs_old)
        return {
            "stufe": stufe, "netto_abs": netto_abs, "netto_pro_aktie": netto_pro_aktie,
            "gs_new": gs_new, "gs_old": gs_old, "max_loss": max_loss, "width": width,
            "ampel": ampel, "spread_type": spread_type, "roll_kind": roll_kind,
            # neutrale Aliase
            "breakeven": gs_new, "risk": max_loss, "net_cash": netto_abs,
            # debit-Keys (bei Credit nicht sinnvoll → None)
            "added_debit_abs": None, "risk_new": max_loss, "breakeven_new": gs_new,
        }

    # DEBIT: credit_open=Debit gezahlt, debit_close=Credit beim Schließen alt,
    #        credit_new=Debit für neuen Spread.
    debit_new = credit_new
    credit_close = debit_close
    lo_old = long_old if long_old is not None else (short_old - width)
    lo_new = long_new if long_new is not None else (short_new - width)

    # Zusätzlicher Netto-Debit für den Roll: neuen Spread zahlen − alten schließen (Credit).
    added_debit_abs = n * debit_new - credit_close
    debit_new_share = debit_new / 100.0
    risk_new = debit_new * n                       # Risiko der NEUEN Position = Debit
    risk_old = credit_open * 1                      # altes 1er-Paket-Risiko (Debit)
    breakeven_new = lo_new + meta["be_dir"] * debit_new_share
    breakeven_old = lo_old + meta["be_dir"] * (credit_open / 100.0)
    ampel = spread_ampel_debit(added_debit_abs, risk_new, risk_old * n)

    return {
        "stufe": stufe,
        # Für UI-Uniformität die gleichen Keys, aber mit debit-Bedeutung:
        "netto_abs": -added_debit_abs,             # negativ = du zahlst
        "netto_pro_aktie": -added_debit_abs / (n * 100.0),
        "gs_new": breakeven_new, "gs_old": breakeven_old,
        "max_loss": risk_new, "width": width, "ampel": ampel,
        "spread_type": spread_type, "roll_kind": roll_kind,
        # neutrale Aliase
        "breakeven": breakeven_new, "risk": risk_new, "net_cash": -added_debit_abs,
        # debit-spezifisch
        "added_debit_abs": added_debit_abs, "risk_new": risk_new,
        "breakeven_new": breakeven_new,
    }
