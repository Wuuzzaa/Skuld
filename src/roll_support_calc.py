"""
Roll-Kalkulation für Cash-Secured Puts und nackte Short Calls —
reine Rechenlogik, keine DB, kein Streamlit.

Grundlage: "Optionen unschlagbar handeln", Kap. 3 (Rollen), am Originaltext
verifiziert 2026-07-11 (Buch 27. Juni 2026.pdf, S. 71-99).

Die 3 verbindlichen Roll-Stufen (Buch S. 71-73):
    Stufe 1: niedrigerer Basispreis (K2 < K), gleiche Kontrakte, 30-60 (max 90) Tage.
    Stufe 2: gleicher Basispreis  (K2 = K), gleiche Kontrakte, 30-60 Tage.
    Stufe 3: niedrigerer Basispreis (K2 < K), Kontrakte verdoppelt (2n), 30-60 Tage.
Oberstes Ziel ist immer, den Basispreis (die Gewinnschwelle) zu senken.

Kernformeln (buchverifiziert, alle Prämien absolut in $/Kontrakt):

    Saldo/Netto-Prämie   netto = P_eroeffnung + n*P_neu - P_heute
    PUT  Neue GS          GS    = K2 - netto / (n * 100)   GS senken = besser
    CALL Neue GS          GS    = K2 + netto / (n * 100)   GS heben  = besser
    Kapital nötig        cap   = K2 * n * 100

Short-Call-Spezifika:
    Innerer Wert  = max(0, S - K)   (ITM wenn Kurs ÜBER Strike)
    Breakeven     = K + Prämie/Aktie
    Roll-Ziel: Strike höher (weiter OTM), GS heben
    Ampel: GS verbessert = breakeven_new > breakeven_old

Alle Kernberechnungen werden bewusst NICHT gecacht (immer frisch gerechnet).
"""
from __future__ import annotations


def ampel(netto: float, breakeven_new: float, breakeven_old: float) -> str:
    """Bewertet einen Roll-Kandidaten nach der Buch-Logik (Put: GS senken).

    ✅  Netto-Prämie > 0 UND neue Gewinnschwelle < alte Gewinnschwelle
    ⚠️  Netto-Prämie > 0 ABER Gewinnschwelle nicht verbessert
    ❌  Netto-Prämie <= 0 (der Roll kostet unterm Strich drauf)
    """
    if netto <= 0:
        return "❌"
    if breakeven_new < breakeven_old:
        return "✅"
    return "⚠️"


def ampel_call(netto: float, breakeven_new: float, breakeven_old: float) -> str:
    """Bewertet einen Roll-Kandidaten für Short Calls (GS heben = besser).

    ✅  Netto-Prämie > 0 UND neue Gewinnschwelle > alte Gewinnschwelle
    ⚠️  Netto-Prämie > 0 ABER Gewinnschwelle nicht verbessert
    ❌  Netto-Prämie <= 0 (der Roll kostet unterm Strich drauf)
    """
    if netto <= 0:
        return "❌"
    if breakeven_new > breakeven_old:
        return "✅"
    return "⚠️"


def position_status(K: float, S: float, P_eroeffnung: float,
                    P_heute: float, n: int,
                    option_type: str = "put") -> dict:
    """Kennzahlen für den Block "Aktuelle Position".

    Args:
        K:            Strike der bestehenden Option.
        S:            Aktueller Aktienkurs.
        P_eroeffnung: Ursprünglich vereinnahmte Prämie, absolut $/Kontrakt.
        P_heute:      Aktueller Optionspreis (Schließungskosten), absolut $/Kontrakt.
        n:            Anzahl Kontrakte.
        option_type:  "put" (default) oder "call".

    Returns:
        dict mit pnl_pct, pnl_abs, inner_value, time_value, breakeven_old.

    Hinweis: Zeitwert kann theoretisch nicht negativ sein (Arbitrage-Gesetz).
    Falls Daten fehlerhaft → max(0, TV) sichert Realismus.
    """
    if option_type == "call":
        inner_value = max(0.0, S - K) * 100.0         # Call ITM wenn Kurs > Strike
        breakeven_old = K + P_eroeffnung / 100.0      # Call BE = Strike + Prämie
    else:
        inner_value = max(0.0, K - S) * 100.0         # Put ITM wenn Kurs < Strike
        breakeven_old = K - P_eroeffnung / 100.0      # Put BE = Strike - Prämie

    time_value = max(0.0, P_heute - inner_value)      # Restzeitwert (min. 0!)
    pnl_abs = (P_eroeffnung - P_heute) * n            # G/V absolut (identisch für put/call)
    pnl_pct = (P_eroeffnung - P_heute) / P_eroeffnung * 100.0

    return {
        "inner_value": inner_value,
        "time_value": time_value,
        "breakeven_old": breakeven_old,
        "pnl_abs": pnl_abs,
        "pnl_pct": pnl_pct,
    }


def pnl_breakdown(K: float, S: float, P_eroeffnung: float,
                  P_heute: float, n: int,
                  option_type: str = "put") -> dict:
    """Kontobuch-Herleitung des G/V der bestehenden Position (reine Anzeige-Hilfe).

    Verändert keine Zahlen — nutzt position_status() und macht die
    ×100/×n-Schritte als einzelne Zeilen sichtbar. Einheiten explizit.

    Returns:
        dict mit pnl_abs, pnl_pct, breakeven_old, im_gewinn, grund, lines.
        lines: [{label, formel, wert, einheit, summe}]. summe=True → Zwischensumme.
    """
    pos = position_status(K=K, S=S, P_eroeffnung=P_eroeffnung, P_heute=P_heute,
                          n=n, option_type=option_type)
    p_open_share = P_eroeffnung / 100.0
    p_today_share = P_heute / 100.0
    einnahme = P_eroeffnung * n          # was beim Verkauf aufs Konto kam
    rueckkauf = -(P_heute * n)           # was der Rückkauf heute kostet
    im_gewinn = pos["pnl_abs"] >= 0
    diff_share = p_open_share - p_today_share

    opt_label = "Call" if option_type == "call" else "Put"
    if im_gewinn:
        grund = (f"Im Gewinn, weil der {opt_label} seit dem Verkauf um "
                 f"${abs(diff_share):.2f}/Aktie billiger geworden ist "
                 f"(Zeitwert-Verfall und/oder günstige Kursentwicklung).")
    else:
        grund = (f"Im Verlust, weil der {opt_label} seit dem Verkauf um "
                 f"${abs(diff_share):.2f}/Aktie teurer geworden ist "
                 f"(ungünstige Kursentwicklung und/oder Volatilität gestiegen).")

    if option_type == "call":
        be_formel = f"Strike {K:.2f} + Prämie {p_open_share:.2f}"
    else:
        be_formel = f"Strike {K:.2f} − Prämie {p_open_share:.2f}"

    lines = [
        {
            "label": "Beim Verkauf eingenommen",
            "formel": f"{p_open_share:.2f} $/Aktie × 100 × {n}",
            "wert": einnahme,
            "einheit": "$ gesamt",
            "summe": False,
        },
        {
            "label": "Rückkauf kostet heute",
            "formel": f"{p_today_share:.2f} $/Aktie × 100 × {n}",
            "wert": rueckkauf,
            "einheit": "$ gesamt",
            "summe": False,
        },
        {
            "label": "G/V wenn du JETZT schließt",
            "formel": f"{einnahme:.0f} − {abs(rueckkauf):.0f}",
            "wert": pos["pnl_abs"],
            "einheit": "$ gesamt",
            "summe": True,
        },
        {
            "label": "Gewinnschwelle",
            "formel": be_formel,
            "wert": pos["breakeven_old"],
            "einheit": "$/Aktie",
            "summe": False,
        },
    ]
    return {
        "pnl_abs": pos["pnl_abs"],
        "pnl_pct": pos["pnl_pct"],
        "breakeven_old": pos["breakeven_old"],
        "im_gewinn": im_gewinn,
        "grund": grund,
        "lines": lines,
    }


def roll_candidate(stufe: int, K: float, K2: float, P_eroeffnung: float,
                   P_heute: float, P_neu: float, n: int,
                   option_type: str = "put") -> dict:
    """Berechnet einen konkreten Roll-Kandidaten einer Stufe.

    Args:
        stufe:        1, 2 oder 3 (nur zur Zuordnung in der UI).
        K:            Alter Strike (für alte Gewinnschwelle).
        K2:           Neuer Strike.
        P_eroeffnung: Ursprüngliche Prämie, absolut $/Kontrakt.
        P_heute:      Schließungskosten der alten Option, absolut $/Kontrakt (n=alt).
        P_neu:        Prämie der neuen Option, absolut $/Kontrakt.
        n:            Kontraktanzahl des NEUEN Kontrakts (Stufe 3: verdoppelt).
        option_type:  "put" (default) oder "call".

    Returns:
        dict mit stufe, netto_abs, netto_pro_aktie, breakeven_new,
        breakeven_old, kapital_noetig, ampel.
    """
    netto_abs = P_eroeffnung + n * P_neu - P_heute
    netto_pro_aktie = netto_abs / (n * 100.0)

    if option_type == "call":
        # Call: GS = Strike + Netto/Aktie — höhere GS ist besser (weiter vom Kurs weg)
        breakeven_new = K2 + netto_abs / (n * 100.0)
        breakeven_old = K + P_eroeffnung / 100.0
        ampel_val = ampel_call(netto_abs, breakeven_new, breakeven_old)
    else:
        breakeven_new = K2 - netto_abs / (n * 100.0)
        breakeven_old = K - P_eroeffnung / 100.0
        ampel_val = ampel(netto_abs, breakeven_new, breakeven_old)

    kapital_noetig = K2 * n * 100.0

    return {
        "stufe": stufe,
        "netto_abs": netto_abs,
        "netto_pro_aktie": netto_pro_aktie,
        "breakeven_new": breakeven_new,
        "breakeven_old": breakeven_old,
        "kapital_noetig": kapital_noetig,
        "ampel": ampel_val,
    }


def roll_candidate_explained(stufe: int, K: float, K2: float, P_eroeffnung: float,
                             P_heute: float, P_neu: float, n: int,
                             option_type: str = "put") -> dict:
    """Wie roll_candidate(), plus 'steps': Klartext-Herleitung für die UI.

    Verändert keine Zahlen — reine Zusatz-Transparenz (Formel + eingesetzte Werte).
    """
    base = roll_candidate(stufe=stufe, K=K, K2=K2, P_eroeffnung=P_eroeffnung,
                          P_heute=P_heute, P_neu=P_neu, n=n, option_type=option_type)
    if option_type == "call":
        gs_formel = f"K2 {K2:.2f} + Netto {base['netto_abs']:.0f} / ({n}×100)"
    else:
        gs_formel = f"K2 {K2:.2f} − Netto {base['netto_abs']:.0f} / ({n}×100)"

    steps = [
        {
            "label": "Netto-Prämie",
            "formel": f"Eröffnung {P_eroeffnung:.0f} + {n}×{P_neu:.0f} (neu) − {P_heute:.0f} (Rückkauf)",
            "wert": base["netto_abs"],
        },
        {
            "label": "Neue Gewinnschwelle",
            "formel": gs_formel,
            "wert": base["breakeven_new"],
        },
        {
            "label": "Alte Gewinnschwelle",
            "formel": f"K {K:.2f} {'+ ' if option_type == 'call' else '− '}Eröffnung {P_eroeffnung:.0f} / 100",
            "wert": base["breakeven_old"],
        },
        {
            "label": "Kapital nötig",
            "formel": f"K2 {K2:.2f} × {n} × 100",
            "wert": base["kapital_noetig"],
        },
    ]
    return {**base, "steps": steps}


# ---------------------------------------------------------------------------
# Eric Ludwig Hints: Zeitwert, Theta-Gamma, Roll-Trigger-Score
# ---------------------------------------------------------------------------
def time_value_percentage(P_heute: float, P_eroeffnung: float) -> float:
    """Berechnet den Restzeitwert als % der ursprünglichen Prämie.
    
    Nach Eric Ludwig: Roll triggern, wenn TV ≤ 10–15 % der Eröffnungsprämie.
    
    Args:
        P_heute:      Aktueller Put-Preis (absolut $/Kontrakt).
        P_eroeffnung: Ursprüngliche Prämie (absolut $/Kontrakt).
    
    Returns:
        Prozentsatz (0–100). Bei P_eroeffnung=0 → 0.
    """
    if P_eroeffnung == 0:
        return 0.0
    # Restzeitwert = aktueller Preis (enthält inneren Wert + Zeitwert)
    # Approximation: TV% = (P_heute / P_eroeffnung) * 100
    return (P_heute / P_eroeffnung) * 100.0


def theta_gamma_score(dte: int) -> tuple[float, str]:
    """Bewertet das Rollzeitfenster nach Theta-Gamma-Balance (Eric Ludwig).
    
    Optimales Fenster: 7–14 Tage vor Verfall (Theta hoch, Gamma noch nicht explosiv).
    Zu früh: Zeitwert noch zu hoch.
    Zu spät (< 3 Tage): Gamma-Explosion, volatile Bewegungen.
    
    Args:
        dte: Days to Expiration (Restlaufzeit).
    
    Returns:
        (score: 0.0–1.0, label: "Optimal"/"Früh"/"Spät"/"Sehr spät")
        Score 1.0 = ideales Fenster, 0.0 = ungünstig.
    """
    if dte >= 14:
        return 0.3, "Noch früh — Zeitwert höher"
    elif 7 <= dte < 14:
        return 1.0, "✅ Optimales Rollzeitfenster (7–14 DTE)"
    elif 3 <= dte < 7:
        return 0.7, "⚠️ Bald zu spät — Gamma steigt"
    else:
        return 0.2, "🔴 Zu spät — Gamma-Explosion unmittelbar"


def roll_trigger_score(P_heute: float, P_eroeffnung: float, dte: int) -> dict:
    """Kombinierter Score zur Roll-Empfehlung (Eric Ludwig Insights).
    
    Bewertet, wie sehr ein aktiver Roll empfohlen ist, basierend auf:
    - Zeitwert % (Hauptfaktor): < 10 % → sehr empfohlen
    - DTE-Fenster (Sekundär): 7–14 Tage ideal
    
    Args:
        P_heute:      Aktueller Put-Preis.
        P_eroeffnung: Ursprüngliche Prämie.
        dte:          Days to Expiration.
    
    Returns:
        dict mit 'score', 'trigger', 'tv_pct', 'dte_label', 'empfehlung'.
    """
    tv_pct = time_value_percentage(P_heute, P_eroeffnung)
    dte_score, dte_label = theta_gamma_score(dte)
    
    # Zeitwert-Stufen (Hauptregel von Ludwig)
    if tv_pct <= 10:
        tv_score = 1.0
        tv_label = "🟢 Sehr hoch — ROLL TRIGGERN"
    elif tv_pct <= 15:
        tv_score = 0.85
        tv_label = "🟡 Hoch — Roll sinnvoll"
    elif tv_pct <= 25:
        tv_score = 0.6
        tv_label = "⚠️ Mittel — Optional"
    else:
        tv_score = 0.3
        tv_label = "🔴 Niedrig — Warten"
    
    # Kombinierter Score (70 % Zeitwert, 30 % DTE-Fenster)
    combined = (tv_score * 0.7) + (dte_score * 0.3)
    
    return {
        "score": combined,
        "trigger": combined >= 0.7,
        "tv_pct": tv_pct,
        "tv_label": tv_label,
        "dte": dte,
        "dte_label": dte_label,
        "dte_score": dte_score,
        "empfehlung": (
            f"{tv_label} | {dte_label}" if combined >= 0.7
            else f"{tv_label} — noch warten"
        ),
    }
