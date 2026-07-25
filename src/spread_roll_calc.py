"""
Bull-Put-Spread rollen — reine Rechenlogik, keine DB, kein Streamlit.

Ein Bull-Put-Spread = Short-Put (verkauft, Strike K_short) + Long-Put (gekauft,
Strike K_short − Breite). Der Long-Put begrenzt den Verlust. Beim Rollen werden
BEIDE Beine gemeinsam auf eine neue Laufzeit/neue Strikes gerollt; die Breite
bleibt konstant (Design-Entscheidung 2026-07-24).

Buch-Analogie (CSP, src/roll_support_calc.py), aber auf den NETTO-CREDIT des
ganzen Spreads bezogen — alle Prämien absolut in $/Kontrakt, Breite in $/Aktie:

    Netto-Credit   netto = credit_open + n*credit_new - debit_close
    Neue GS        gs_new = short_new - netto / (n * 100)
    Max-Loss       max_loss = (width - netto/(n*100)) * 100 * n   (>=0-Realismus)

Ampel wie Buch:
    ✅ netto > 0 UND gs_new < gs_old
    ⚠️ netto > 0 aber gs_new >= gs_old
    ❌ netto <= 0

Ludwig-Trigger (Restzeitwert/Theta-Gamma) wird aus roll_support_calc
wiederverwendet — der arbeitet auf Netto-Preis + DTE und ist beinunabhängig.
"""
from __future__ import annotations


def spread_ampel(netto: float, gs_new: float, gs_old: float) -> str:
    """Bewertet einen Spread-Roll-Kandidaten (Netto-Credit + Gewinnschwelle)."""
    if netto <= 0:
        return "❌"
    if gs_new < gs_old:
        return "✅"
    return "⚠️"


def spread_position_status(short_strike: float, width: float, credit_open: float,
                           debit_now: float, n: int) -> dict:
    """Kennzahlen der bestehenden Spread-Position.

    Args:
        short_strike: Strike des Short-Puts.
        width:        Spread-Breite in $/Aktie (Short − Long).
        credit_open:  Bei Eröffnung vereinnahmter Netto-Credit, absolut $/Kontrakt.
        debit_now:    Aktueller Schließungs-Debit des Spreads, absolut $/Kontrakt.
        n:            Anzahl Spreads (Kontrakte).

    Returns:
        dict mit gs_old, max_loss_open, pnl_abs, pnl_pct.
    """
    gs_old = short_strike - credit_open / 100.0
    max_loss_open = max(0.0, (width - credit_open / 100.0)) * 100.0 * n
    pnl_abs = (credit_open - debit_now) * n
    pnl_pct = (credit_open - debit_now) / credit_open * 100.0 if credit_open else 0.0
    return {
        "gs_old": gs_old,
        "max_loss_open": max_loss_open,
        "pnl_abs": pnl_abs,
        "pnl_pct": pnl_pct,
    }


def spread_pnl_breakdown(short_strike: float, width: float, credit_open: float,
                         debit_now: float, n: int) -> dict:
    """Kontobuch-Herleitung des G/V der bestehenden Spread-Position (Anzeige-Hilfe).

    Nutzt spread_position_status(); ändert keine Zahlen. Einheiten explizit.
    Returns dict mit pnl_abs, pnl_pct, gs_old, max_loss_open, im_gewinn, grund, lines.
    lines: [{label, formel, wert, einheit, summe}]. summe=True → Zwischensumme.
    """
    pos = spread_position_status(short_strike=short_strike, width=width,
                                 credit_open=credit_open, debit_now=debit_now, n=n)
    credit_share = credit_open / 100.0
    debit_share = debit_now / 100.0
    einnahme = credit_open * n
    schliessen = -(debit_now * n)
    im_gewinn = pos["pnl_abs"] >= 0
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
         "formel": f"Short {short_strike:.2f} − Credit {credit_share:.2f}",
         "wert": pos["gs_old"], "einheit": "$/Aktie", "summe": False},
        {"label": "Max-Loss (offen)",
         "formel": f"(Breite {width:.2f} − Credit {credit_share:.2f}) × 100 × {n}",
         "wert": pos["max_loss_open"], "einheit": "$ gesamt", "summe": False},
    ]
    return {
        "pnl_abs": pos["pnl_abs"], "pnl_pct": pos["pnl_pct"], "gs_old": pos["gs_old"],
        "max_loss_open": pos["max_loss_open"], "im_gewinn": im_gewinn,
        "grund": grund, "lines": lines,
    }


def spread_roll_candidate(stufe: int, short_old: float, short_new: float, width: float,
                          credit_open: float, debit_close: float, credit_new: float,
                          n: int) -> dict:
    """Berechnet einen konkreten Spread-Roll-Kandidaten einer Stufe.

    Args:
        stufe:       1, 2 oder 3 (nur zur Zuordnung in der UI).
        short_old:   Alter Short-Strike (für alte Gewinnschwelle).
        short_new:   Neuer Short-Strike.
        width:       Spread-Breite (fix, $/Aktie).
        credit_open: Ursprünglich vereinnahmter Netto-Credit, absolut $/Kontrakt.
        debit_close: Schließungs-Debit des alten Spreads, absolut $/Kontrakt (1er-Paket).
        credit_new:  Netto-Credit des NEUEN Spreads, absolut $/Kontrakt.
        n:           Kontraktzahl des NEUEN Spreads (Stufe 3: verdoppelt).

    Returns:
        dict mit stufe, netto_abs, netto_pro_aktie, gs_new, gs_old,
        max_loss, width, ampel.
    """
    # Buch-Analogie: altes 1er-Paket schließen, neues n-Paket eröffnen.
    netto_abs = credit_open + n * credit_new - debit_close
    netto_pro_aktie = netto_abs / (n * 100.0)

    gs_new = short_new - netto_pro_aktie
    gs_old = short_old - credit_open / 100.0
    # Max-Loss = (Breite − Gesamt-Credit/Aktie) über alle n Spreads, min. 0.
    max_loss = max(0.0, (width - netto_pro_aktie)) * 100.0 * n

    return {
        "stufe": stufe,
        "netto_abs": netto_abs,
        "netto_pro_aktie": netto_pro_aktie,
        "gs_new": gs_new,
        "gs_old": gs_old,
        "max_loss": max_loss,
        "width": width,
        "ampel": spread_ampel(netto_abs, gs_new, gs_old),
    }
