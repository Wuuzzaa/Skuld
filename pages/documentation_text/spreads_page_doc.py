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

**Expected Value** - Erwarteter Gewinn basierend auf Monte-Carlo-Simulation
- Berücksichtigt alle möglichen Kursverläufe
- Realistischer als Max Profit

---

### Performance Kennzahlen

**APDI (Annualized Profit per Dollar Invested)** - Annualisierte Rendite auf Max Profit Basis
```
APDI = (Max Profit / Days to Expiration / BPR) × 36,500
```
*Zeigt theoretische Jahresrendite bei perfektem Ausgang*

**APDI_EV (APDI mit Expected Value)** - Annualisierte Rendite auf Expected Value Basis
```
APDI_EV = (Expected Value / Days to Expiration / BPR) × 36,500
```
*Realistischere Renditekennzahl basierend auf Simulation*

---

### Strategien

**Bull Put Spread** (Put-Optionen)
- Verkaufe Put mit höherem Strike
- Kaufe Put mit niedrigerem Strike als Schutz
- Profitiert von steigenden/stabilen Kursen

**Bear Call Spread** (Call-Optionen)
- Verkaufe Call mit niedrigerem Strike
- Kaufe Call mit höherem Strike als Schutz
- Profitiert von fallenden/stabilen Kursen

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

⚠️ **Risiko**: Der maximale Verlust bei Spreads ist die Differenz zwischen Max Profit und BPR

📊 **Monte Carlo**: Die Expected Value Berechnung verwendet eine stochastische Simulation

💡 **APDI vs APDI_EV**: APDI_EV ist konservativer und realistischer als APDI

🔗 **Quick Actions**: Nutze die Icons in der Tabelle für schnellen Zugriff auf Analysetools
"""