def get_iron_condor_documentation() -> str:
    """
    Returns markdown documentation explaining all calculated fields in the iron condors view.
    """
    return """
## 🦅 Iron Condor Berechnung - Feldübersicht

### Grundlegende Informationen

**Symbol** - Ticker des Basiswerts

**Earnings Date** - Nächster Quartalsbericht-Termin

**Earnings Warning** ⚠️ - Warnung wenn Earnings innerhalb von 7 Tagen vor Ablauf stattfinden

**Close** - Aktueller Kurs des Basiswerts (Anzeige der Put-Seite als Referenz)

---

### Strategie-Struktur (Iron Condor)

Ein Iron Condor kombiniert einen **Bull Put Spread** und einen **Bear Call Spread**.

**Sell Strike Put / Call** - Die Strikes der verkauften Optionen. Hier wird die Prämie generiert.
**Buy Strike Put / Call** - Die Strikes der gekauften Optionen zur Absicherung (Long Legs).

**Sell Delta Put / Call** - Das Delta der Short-Optionen. Ein niedrigeres Delta (z.B. 0.15) bedeutet eine höhere Wahrscheinlichkeit, dass die Option wertlos verfällt (Profit).

---

### Spread & Condor Metriken

**Max Profit** - Der maximale Gewinn der gesamten Strategie (Summe der Credits beider Spreads).
```
Max Profit = (Credit Put Spread + Credit Call Spread) × 100
```

**BPR (Buying Power Reduction)** - Erforderliche Margin. Da meist nur eine Seite gleichzeitig verlustreich sein kann, berechnet sie sich aus dem Risiko der "teureren" Seite.
```
BPR = Max(Width Put Spread, Width Call Spread) × 100 - Max Profit
```

**Expected Value (EV)** - Erwarteter Gewinn basierend auf einer kombinierten Monte-Carlo-Simulation aller 4 Legs.
- Berücksichtigt die Korrelation und Wahrscheinlichkeiten beider Seiten gleichzeitig.
- Ein positiver EV ist ein Indikator für einen statistischen Vorteil.

---

### Performance Kennzahlen

**APDI (Annualized Profit per Dollar Invested)** - Annualisierte Rendite auf Max Profit Basis.
```
APDI = (Max Profit / Max Days to Expiration / BPR) × 36,500
```

**APDI_EV (APDI mit Expected Value)** - Annualisierte Rendite auf Basis des simulierten Erwartungswerts.
- Dies ist die realistischste Kennzahl für die langfristige Performance.

---

### Quick Actions (Tabellen-Icons)

**📊 TradingView** - TradingView Symbol-Übersicht.

**📈 Chart** - Direkter Link zum TradingView Superchart.

**🤖 Claude** - Claude AI Analyse der spezifischen Iron Condor Struktur (beide Seiten).

**🎯 OptionStrat** - Visualisierung des Iron Condors im interaktiven G/V-Diagramm.

---

### Wichtige Hinweise

⚠️ **Risiko**: Trotz Absicherung bleibt ein Risiko in Höhe des BPR. Bei starken Kursbewegungen über die Short-Strikes hinaus entstehen Verluste.

📊 **Simulation**: Der Expected Value wird durch tausende Pfad-Simulationen ermittelt und bietet eine statistische Entscheidungsgrundlage.

💡 **Flexibilität**: Skuld erlaubt unterschiedliche Deltas und Breiten für die Call- und Put-Seite, um auf Marktasymmetrien (z.B. Put-Skew) zu reagieren.
"""
