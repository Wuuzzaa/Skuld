def get_spreads_documentation() -> str:
    """
    Returns markdown documentation explaining all calculated fields in the spreads view.
    """
    return """
## 📊 Spreads Berechnung - Feldübersicht

### Grundlegende Informationen

**Symbol** - Ticker des Basiswerts

**Earnings Date** - Nächster Quartalsbericht-Termin

**Earnings Warning** ⚠️ - Warnung wenn Earnings innerhalb von 7 Tagen vor Ablauf stattfinden

**Close** - Aktueller Kurs des Basiswerts

**Analyst Mean Target** - Durchschnittliches Kursziel der Analysten

**Days to Earnings** - Tage bis zum nächsten Earnings Report

---

### Sell Option (Short Leg)

**Sell Strike** - Strike der verkauften Option (Short Position)

**Sell Last Option Price** - Aktueller Preis der verkauften Option

**Sell Delta** - Delta der verkauften Option (Ziel: ~0.20 = 20% Wahrscheinlichkeit ITM)

**Sell IV** - Implizite Volatilität der verkauften Option

**Sell Expected Move** - Erwartete Kursbewegung basierend auf IV

**% OTM** - Prozentualer Abstand des Sell-Strikes zum aktuellen Kurs
```
% OTM = |Sell Strike - Close| / Close × 100
```
*Höherer Wert = größerer Sicherheitspuffer, aber niedrigere Prämie*

---

### Buy Option (Long Leg - Protection)

**Buy Strike** - Strike der gekauften Option (Long Position als Absicherung)

**Buy Last Option Price** - Preis der gekauften Schutzoption

**Buy Delta** - Delta der gekauften Option

---

### Spread Metriken

**Max Profit** - Maximaler Gewinn des Spreads in $ (bei Verfall OTM)
```
Max Profit = (Sell Premium - Buy Premium) × 100
```

**BPR (Buying Power Reduction)** - Erforderliche Margin/Kapitalbindung
```
BPR = (Spread Width × 100) - Max Profit
```

**Profit to BPR** - Verhältnis von maximalem Gewinn zur Kapitalbindung
```
Profit to BPR = Max Profit / BPR
```
*Höhere Werte bedeuten effizientere Kapitalnutzung*

**Expected Value (Static)** - Erwarteter Gewinn basierend auf Monte-Carlo-Simulation bei Halten bis zum Verfall.
- Berücksichtigt alle möglichen Kursverläufe.
- Realistischer als Max Profit.

**EV (Managed)** - Erwarteter Gewinn unter Berücksichtigung von Management-Regeln.
- Simuliert das Schließen der Position bei Erreichen von:
    - **Take Profit %** (z.B. 50% des Max Profits)
    - **Stop Loss %** (z.B. 200% des Max Profits)
    - **DTE Close** (Schließen X Tage vor Verfall)
- Dies ist oft die wichtigste Kennzahl, da sie den tatsächlichen Trading-Stil widerspiegelt.

---

### Simulation Greeks

Die Greeks werden mittels der Monte-Carlo-Simulation berechnet, indem der Preis und die Volatilität leicht verschoben werden (Finite-Differenzen-Methode).

**Delta** - Richtungsrisiko der Strategie.
- Gibt an, um wie viel sich der Wert des Spreads ändert, wenn der Basiswert um $1 steigt.
- Positives Delta (Bullish): Spread gewinnt bei steigenden Kursen.
- Negatives Delta (Bearish): Spread gewinnt bei fallenden Kursen.

**Gamma** - Stabilität des Deltas.
- Gibt an, wie stark sich das Delta ändert, wenn der Basiswert um $1 steigt.
- Ein hohes Gamma bedeutet, dass das Richtungsrisiko (Delta) bei Kursbewegungen schnell zunimmt.

**Vega** - Volatilitätsrisiko.
- Gibt an, um wie viel sich der Wert des Spreads ändert, wenn die implizite Volatilität um 1%-Punkt steigt.
- Negatives Vega (Short Vega): Profitabel bei sinkender Volatilität (typisch für Credit Spreads).
- Positives Vega (Long Vega): Profitabel bei steigender Volatilität (typisch für Debit Spreads).

---

### Performance Kennzahlen

**APDI (Annualized Profit per Dollar Invested)** - Annualisierte Rendite auf Max Profit Basis
```
APDI = (Max Profit / Days to Expiration / BPR) × 36,500
```
*Zeigt theoretische Jahresrendite bei perfektem Ausgang*

**APDI_EV (APDI mit Expected Value)** - Annualisierte Rendite auf Basis des **Managed Expected Value** (wenn vorhanden, sonst Static EV).
```
APDI_EV = (EV / Days to Expiration / BPR) × 36,500
```
*Realistischere Renditekennzahl basierend auf Simulation und Management-Regeln.*

---

### Strategien & Typen

**Credit Spreads** (Verkauf von Premium)
- **Bull Put Spread**: Verkaufe Put mit höherem Strike, kaufe Put mit niedrigerem Strike als Schutz. Profitiert von steigenden/stabilen Kursen.
- **Bear Call Spread**: Verkaufe Call mit niedrigerem Strike, kaufe Call mit höherem Strike als Schutz. Profitiert von fallenden/stabilen Kursen.
- Ziel: Zeitwertverfall (Theta) und Erhalt der Prämie.

**Debit Spreads** (Kauf von Premium)
- **Bull Call Spread**: Kaufe Call mit niedrigerem Strike, verkaufe Call mit höherem Strike zur Kostenreduktion. Profitiert von steigenden Kursen.
- **Bear Put Spread**: Kaufe Put mit höherem Strike, verkaufe Put mit niedrigerem Strike zur Kostenreduktion. Profitiert von fallenden Kursen.
- Ziel: Richtungsbewegung des Basiswerts.

---

### Berechnung Credit vs. Debit

**Credit Spread**:
- **Max Profit**: Erhaltene Prämie (Net Credit)
- **BPR (Risiko)**: (Spread Width × 100) - Max Profit
- **Theta**: Positiv (profitiert von Zeitablauf)

**Debit Spread**:
- **Max Profit**: (Spread Width × 100) - Gezahlte Prämie (Net Debit)
- **BPR (Risiko)**: Gezahlte Prämie (Net Debit)
- **Theta**: Negativ (leidet unter Zeitablauf)

---

### Filter & Parameter

**Delta Target** - Ziel-Delta für die Sell-Option (Standard: 0.20)
- Niedrigeres Delta = höhere Erfolgswahrscheinlichkeit, niedrigere Prämie
- Höheres Delta = niedrigere Erfolgswahrscheinlichkeit, höhere Prämie

**Spread Width** - Abstand zwischen Strikes in $
- Breiterer Spread = höheres Risiko, höhere Kapitalbindung
- Engerer Spread = niedrigeres Risiko, niedrigere Kapitalbindung

**Min Open Interest** - Mindest-Open-Interest für Liquidität (Standard: 100)

---

### Quick Actions (Tabellen-Icons)

**📊 TradingView** - TradingView Symbol-Übersicht mit Fundamentaldaten

**📈 Chart** - TradingView Superchart für technische Analyse

**🤖 Claude** - Claude AI mit vorgefertigtem Analyse-Prompt
- Fundamentalanalyse des Unternehmens
- Aktuelle News und Events
- Bewertung der konkreten Spread-Strategie
- Gewinnwahrscheinlichkeit und Risiken

**🎯 OptionStrat** - Visuelle Strategie-Analyse
- Interaktive Gewinn/Verlust-Diagramme
- Griechen-Analyse
- Break-Even-Punkte

---

### Wichtige Hinweise

⚠️ **Risiko**: Der maximale Verlust bei Spreads ist die Differenz zwischen Max Profit und BPR (eigentlich ist BPR das Risiko, Max Profit ist das Ziel).

📊 **Monte Carlo**: Die Expected Value Berechnung verwendet eine stochastische Simulation mit Tausenden von Pfaden.

💡 **APDI vs APDI_EV**: APDI_EV ist deutlich aussagekräftiger, da es die Gewinnwahrscheinlichkeit und Management-Regeln einpreist.

---

### Wichtige Hinweise zum Expected Value (EV)

📊 **Monte Carlo Simulation**: Der Expected Value wird mittels einer stochastischen Simulation berechnet. 

⚠️ **IV Correction (Implied Volatility Correction)**:
- Standardmäßig wird die Implizite Volatilität (IV) des Marktes um ca. 8-15% nach unten korrigiert.
- Dies basiert auf historischer Forschung, die zeigt, dass die IV die tatsächliche Schwankung meist überschätzt.
- **Folge**: Dies begünstigt **Credit Spreads** (Verkauf) und führt bei **Debit Spreads** (Kauf) häufig zu negativen Expected Values, da die Wahrscheinlichkeit für starke Kursbewegungen geringer eingeschätzt wird. Managed EV zeigt oft noch bessere Werte für Credit Spreads, da Gewinne früh mitgenommen und Verluste begrenzt werden.

💡 **Debit Spreads & Delta**:
- Bei Debit Spreads (Bull Call / Bear Put) ist ein **Delta Target von 0.60 bis 0.70** oft sinnvoller. 
- Man kauft dabei eine Option, die bereits "im Geld" (ITM) ist, was die Erfolgswahrscheinlichkeit und den Expected Value erhöht.
- Ein Delta von 0.20 (Out-of-the-Money) führt bei Debit Spreads fast immer zu einem negativen EV, da die Kosten (Prämie + Transaktionskosten) die statistische Gewinnwahrscheinlichkeit übersteigen.

🔗 **Quick Actions**: Nutze die Icons in der Tabelle für schnellen Zugriff auf Analysetools
"""