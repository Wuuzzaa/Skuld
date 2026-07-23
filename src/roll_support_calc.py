"""
Roll-Kalkulation für Cash-Secured Puts — reine Rechenlogik, keine DB, kein Streamlit.

Grundlage: "Optionen unschlagbar handeln", Kap. 3 (Rollen), am Originaltext
verifiziert 2026-07-11 (Buch 27. Juni 2026.pdf, S. 71-99).

Die 3 verbindlichen Roll-Stufen (Buch S. 71-73):
    Stufe 1: niedrigerer Basispreis (K2 < K), gleiche Kontrakte, 30-60 (max 90) Tage.
    Stufe 2: gleicher Basispreis  (K2 = K), gleiche Kontrakte, 30-60 Tage.
    Stufe 3: niedrigerer Basispreis (K2 < K), Kontrakte verdoppelt (2n), 30-60 Tage.
Oberstes Ziel ist immer, den Basispreis (die Gewinnschwelle) zu senken.

Kernformeln (buchverifiziert, alle Prämien absolut in $/Kontrakt):

    Saldo/Netto-Prämie   netto = P_eroeffnung + n*P_neu - P_heute
    Neue Gewinnschwelle  GS    = K2 - netto / (n * 100)
    Kapital nötig        cap   = K2 * n * 100

Hinweis zur Design-Spec: Die Spec verkürzte die Netto-Definition an einer Stelle
auf "P_neu - P_heute". Das ergibt jedoch nicht die Buch-Salden (Szenario 1-3:
+110/+190/+170 $). Maßgeblich ist die obige Buch-Formel — die zugehörigen
Unit-Tests (tests/test_roll_support_calc.py) prüfen exakt diese Buch-Zahlen.

Alle Kernberechnungen werden bewusst NICHT gecacht (immer frisch gerechnet).
"""
from __future__ import annotations


def ampel(netto: float, breakeven_new: float, breakeven_old: float) -> str:
    """Bewertet einen Roll-Kandidaten nach der Buch-Logik.

    ✅  Netto-Prämie > 0 UND neue Gewinnschwelle < alte Gewinnschwelle
    ⚠️  Netto-Prämie > 0 ABER Gewinnschwelle nicht verbessert
    ❌  Netto-Prämie <= 0 (der Roll kostet unterm Strich drauf)
    """
    if netto <= 0:
        return "❌"
    if breakeven_new < breakeven_old:
        return "✅"
    return "⚠️"


def position_status(K: float, S: float, P_eroeffnung: float,
                    P_heute: float, n: int) -> dict:
    """Kennzahlen für den Block "Aktuelle Position".

    Args:
        K:            Strike des bestehenden Puts.
        S:            Aktueller Aktienkurs.
        P_eroeffnung: Ursprünglich vereinnahmte Prämie, absolut $/Kontrakt.
        P_heute:      Aktueller Put-Preis (Schließungskosten), absolut $/Kontrakt.
        n:            Anzahl Kontrakte.

    Returns:
        dict mit pnl_pct, pnl_abs, inner_value, time_value, breakeven_old.
    
    Hinweis: Zeitwert kann theoretisch nicht negativ sein (Arbitrage-Gesetz).
    Falls Daten fehlerhaft → max(0, TV) sichert Realismus.
    """
    inner_value = max(0.0, K - S) * 100.0          # innerer Wert pro Kontrakt in $
    time_value = max(0.0, P_heute - inner_value)   # Restzeitwert (min. 0!)
    breakeven_old = K - P_eroeffnung / 100.0       # alte Gewinnschwelle je Aktie
    pnl_abs = (P_eroeffnung - P_heute) * n         # G/V absolut
    pnl_pct = (P_eroeffnung - P_heute) / P_eroeffnung * 100.0  # G/V in %

    return {
        "inner_value": inner_value,
        "time_value": time_value,
        "breakeven_old": breakeven_old,
        "pnl_abs": pnl_abs,
        "pnl_pct": pnl_pct,
    }


def roll_candidate(stufe: int, K: float, K2: float, P_eroeffnung: float,
                   P_heute: float, P_neu: float, n: int) -> dict:
    """Berechnet einen konkreten Roll-Kandidaten einer Stufe.

    Args:
        stufe:        1, 2 oder 3 (nur zur Zuordnung in der UI).
        K:            Alter Strike (für alte Gewinnschwelle).
        K2:           Neuer Strike.
        P_eroeffnung: Ursprüngliche Prämie, absolut $/Kontrakt.
        P_heute:      Schließungskosten des alten Puts, absolut $/Kontrakt (n=alt).
        P_neu:        Prämie des neuen Puts, absolut $/Kontrakt.
        n:            Kontraktanzahl des NEUEN Puts (Stufe 3: verdoppelt).

    Returns:
        dict mit stufe, netto_abs, netto_pro_aktie, breakeven_new,
        breakeven_old, kapital_noetig, ampel.
    """
    # Saldo inkl. Eröffnungsprämie (Buch): das alte 1er-Paket wird geschlossen,
    # das neue n-Paket eröffnet.
    netto_abs = P_eroeffnung + n * P_neu - P_heute
    netto_pro_aktie = netto_abs / (n * 100.0)

    breakeven_new = K2 - netto_abs / (n * 100.0)
    breakeven_old = K - P_eroeffnung / 100.0
    kapital_noetig = K2 * n * 100.0

    return {
        "stufe": stufe,
        "netto_abs": netto_abs,
        "netto_pro_aktie": netto_pro_aktie,
        "breakeven_new": breakeven_new,
        "breakeven_old": breakeven_old,
        "kapital_noetig": kapital_noetig,
        "ampel": ampel(netto_abs, breakeven_new, breakeven_old),
    }


def roll_candidate_explained(stufe: int, K: float, K2: float, P_eroeffnung: float,
                             P_heute: float, P_neu: float, n: int) -> dict:
    """Wie roll_candidate(), plus 'steps': Klartext-Herleitung für die UI.

    Verändert keine Zahlen — reine Zusatz-Transparenz (Formel + eingesetzte Werte).
    """
    base = roll_candidate(stufe=stufe, K=K, K2=K2, P_eroeffnung=P_eroeffnung,
                          P_heute=P_heute, P_neu=P_neu, n=n)
    steps = [
        {
            "label": "Netto-Prämie",
            "formel": f"Eröffnung {P_eroeffnung:.0f} + {n}×{P_neu:.0f} (neu) − {P_heute:.0f} (Rückkauf)",
            "wert": base["netto_abs"],
        },
        {
            "label": "Neue Gewinnschwelle",
            "formel": f"K2 {K2:.2f} − Netto {base['netto_abs']:.0f} / ({n}×100)",
            "wert": base["breakeven_new"],
        },
        {
            "label": "Alte Gewinnschwelle",
            "formel": f"K {K:.2f} − Eröffnung {P_eroeffnung:.0f} / 100",
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
