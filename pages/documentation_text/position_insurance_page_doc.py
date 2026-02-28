def get_position_insurance_documentation() -> str:
    """
    Returns markdown documentation explaining the Position Insurance Tool
    and all calculated fields.
    """
    return """
## 🛡️ Position Insurance Tool – Dokumentation

### Was ist das?

Das **Position Insurance Tool** hilft Aktienhaltern, bestehende Long-Positionen mit **Protective Puts** abzusichern.
Du gibst dein Aktiensymbol und deinen Einstandskurs (Cost Basis) ein – das Tool lädt verfügbare Put-Optionen
und berechnet für jede Option, wie viel Gewinn **eingesperrt** (locked-in) werden kann und was die Absicherung kostet.

> **Protective Put** = Du besitzt Aktien und kaufst eine Put-Option als Versicherung.
> Falls die Aktie fällt, greift der Put ab dem Strike-Preis und begrenzt deinen Verlust.

---

### Eingabeparameter

| Parameter | Beschreibung |
|---|---|
| **Aktiensymbol** | Ticker der Aktie, die du absichern willst (z.B. NVDA) |
| **Einstandskurs (Cost Basis)** | Dein durchschnittlicher Kaufpreis pro Aktie |

---

### Berechnete Metriken

#### Kosten & Effizienz

**Put Preis** – Aktuelle Prämie der Put-Option (Preis pro Aktie, × 100 für einen Kontrakt)

**Versicherung (%)** – Kosten der Absicherung als Prozent des aktuellen Aktienwerts
```
Versicherung (%) = (Put-Preis / Aktienkurs) × 100
```
*Beispiel: Aktie bei 150$, Put kostet 5$ → Versicherung kostet 3.33% des Positionswerts*

**Zeitwert/Monat** – Monatliche Zeitwert-Kosten (je niedriger, desto effizienter)
```
Zeitwert/Monat = Zeitwert / (Tage bis Verfall / 30)
```

**Kosten p.a. (%)** – Annualisierte Absicherungskosten in % des Aktienwerts
```
Kosten p.a. ($) = (Zeitwert / Tage bis Verfall) × 365
Kosten p.a. (%) = (Kosten p.a. ($) / Aktienkurs) × 100
```
*Macht Optionen mit verschiedenen Laufzeiten direkt vergleichbar*

---

#### Gewinn & Schutz

**Neuer Einstand** – Effektiver Einstandskurs inklusive Put-Prämie
```
Neuer Einstand = Einstandskurs + Put-Preis
```

**Locked-in Profit ($)** – Garantierter Mindestgewinn (oder -verlust) bei Ausübung
```
Locked-in Profit = Strike - Neuer Einstand
```
*Positiv = garantierter Gewinn. Negativ = maximaler Verlust ist begrenzt.*

**Locked-in Profit (%)** – Locked-in Profit relativ zum neuen Einstandskurs
```
Locked-in Profit (%) = (Locked-in Profit / Neuer Einstand) × 100
```

**Absicherungstiefe (%)** – Wie weit die Aktie fallen muss, bevor der Put greift
```
Absicherungstiefe (%) = ((Aktienkurs - Strike) / Aktienkurs) × 100
```
*Negativer Wert = Put ist bereits im Geld (ITM), Schutz ab über dem aktuellen Kurs!*

| Beispiel | Aktienkurs | Strike | Absicherungstiefe |
|---|---|---|---|
| OTM Put | 150$ | 140$ | 6.67% (Aktie muss 6.67% fallen) |
| ITM Put | 150$ | 155$ | -3.33% (Schutz über aktuellem Kurs) |

---

### Empfehlungen

💡 **Effizienz-Tipp** – Die Option mit den niedrigsten Zeitwert-Kosten pro Monat.
Ideal wenn du möglichst günstig absichern willst.

🛡️ **Bester Schutz** – Die Option mit der niedrigsten (negativsten) Absicherungstiefe.
Ideal wenn du den stärksten Schutz willst, auch wenn er teurer ist.

---

### Filter

**Verfallsmonat** – Gruppierung nach Verfallsmonaten zur gezielten Auswahl

**Min. Locked-in Profit (%)** – Nur Optionen anzeigen, die mindestens diesen Gewinn garantieren

**Vorfilter** – Es werden nur Puts mit Strike ≥ Einstandskurs angezeigt
(da nur diese den Einstandskurs absichern und einen positiven Locked-in Profit ermöglichen)

---

### Interpretation & Tipps

| Situation | Empfehlung |
|---|---|
| Hoher unrealisierter Gewinn | Längere Laufzeit wählen (geringere monatliche Kosten) |
| Kurzfristige Absicherung (z.B. vor Earnings) | Kurze Laufzeit, Strike nahe am Kurs |
| Minimale Kosten | Auf niedrige Zeitwert/Monat und Kosten p.a. achten |
| Maximaler Schutz | Absicherungstiefe möglichst negativ (ITM-Puts) |

---

### Hinweise

⚠️ **Die Werte gelten pro Aktie** – Ein Optionskontrakt umfasst 100 Aktien.
Multiply die Kosten × 100 für den tatsächlichen Kontraktpreis.

📊 **Alle Preise sind Schlusskurse** – Live-Preise können abweichen.

💡 **Zeitwert verfällt** – Je näher der Verfall, desto schneller verliert der Put an Zeitwert
(Theta-Verfall). Bei längeren Laufzeiten ist der Zeitwert pro Monat oft günstiger.
"""
