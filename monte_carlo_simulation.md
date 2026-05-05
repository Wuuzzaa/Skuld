# Monte Carlo Simulation für Optionsstrategien

Dieses Dokument beschreibt die Implementierung, die theoretischen Hintergründe und die Management-Strategien des `MonteCarloSimulator` in Skuld.

---

## 1. Überblick & Architektur

Das Modul `src/monte_carlo_simulation.py` stellt den `MonteCarloSimulator` zur Verfügung. Er bewertet beliebige Multi-Leg-Optionsstrategien (z.B. Iron Condor, Spreads, Straddles) durch numerische Simulation.

### Kernfunktionalitäten
- **Preis-Modelle**: 
    - **GBM (Geometrische Brownsche Bewegung)**: Standardmodell mit konstanter Volatilität für risikoneutrale Bewertung.
    - **IV-Shock / Heston**: Unterstützung für stochastische Volatilität und Mean-Reversion (Vola-Crush), um reale Markteffekte abzubilden.
- **Risikoneutrale Bewertung**: Nutzung des risikofreien Zinssatzes als Drift.
- **IV-Korrektur**: Systematische Reduktion der Markt-IV basierend auf der Volatilitätsrisikoprämie (VRP).
- **Vektorisierung**: Massive Nutzung von NumPy zur parallelen Berechnung von tausenden Pfaden und Black-Scholes-Preisen.
- **Greeks**: Berechnung von Delta, Gamma und Vega mittels finiter Differenzen unter Verwendung von *Common Random Numbers (CRN)* zur Rauschreduzierung.

---

## 2. Tastytrade-Style Management (50/200/21)

Der Simulator unterstützt aktives Trade-Management nach den Prinzipien von Tastytrade. Ziel ist es, das Gamma-Risiko am Ende der Laufzeit zu reduzieren und die Kapitalumschlagsgeschwindigkeit zu erhöhen.

### Komponenten des Managements
- **Take Profit (TP) - Ziel 50%**: 
    - **Beschreibung**: Schließt die Position, sobald 50% des maximal möglichen Gewinns (bei Credit-Spreads das eingenommene Premium) erreicht sind.
    - **Ziel**: Gewinne sichern, bevor Preisschwankungen sie zunichtemachen.
- **Stop Loss (SL) - Ziel 200%**:
    - **Beschreibung**: Schließt die Position, wenn der Verlust das Zweifache des eingenommenen Premiums erreicht (3x das ursprüngliche Risiko bei manchen Definitionen, hier meist 200% des Premiums als Verlust-Trigger).
    - **Ziel**: Vermeidung von "Tail-Risk" und extremen Ausreißern.
- **DTE Close - Ziel 21 Tage**:
    - **Beschreibung**: Schließt den Trade spätestens 21 Tage vor dem Verfall (bei einer ursprünglichen Laufzeit von ca. 45 DTE).
    - **Ziel**: Eliminierung des Gamma-Risikos. In den letzten 21 Tagen reagiert der Optionspreis extrem empfindlich auf kleine Preisbewegungen des Basiswerts.

### Der "Edge" (Vorteil)
1. **Volatilitäts-Mean-Reversion (Vola-Crush)**: In der Realität ist IV oft "mean-reverting". Nach einem Anstieg (IV-Spike) fällt sie meist schnell zurück. Das TP-Ziel wird dadurch oft viel früher erreicht, als es der reine Zeitwertverfall (Theta) vermuten lässt.
2. **Höherer annualisierter EV**: Durch das frühe Schließen wird Kapital frei, das sofort in neue Trades mit hoher Wahrscheinlichkeit reinvestiert werden kann. 
3. **Verbesserte Sharpe-Ratio**: Die Varianz der PnL wird reduziert, da die "hässlichen" Verluste am Ende der Laufzeit (Gamma-Explosion) vermieden werden.

---

## 3. Analyse & Metriken

Der Simulator liefert nicht nur den Erwartungswert (EV), sondern eine umfassende Risikoanalyse:

- **EV (Static)**: Erwartungswert beim Halten bis zum Verfall.
- **EV (Managed)**: Erwartungswert unter Anwendung der TP/SL/DTE-Regeln.
- **EV/Tag & EV annualisiert**: Entscheidende Metriken für den Vergleich von Strategien mit unterschiedlichen Haltedauern.
- **CVaR (Conditional Value at Risk)**: Der durchschnittliche Verlust in den schlimmsten 5% der Fälle (Tail-Risk).
- **Win-Probability**: Wahrscheinlichkeit für einen positiven Ausgang.

---

## 4. Technische Implementierung & Refactoring-Notizen

### Aktueller Stand (Refactoring 2024)
- **RNG**: Umstellung auf `np.random.default_rng()` für bessere Performance und Thread-Sicherheit.
- **Pfad-Cache**: Optimierte Speicherung von Preispfaden, um redundante Simulationen bei der Greeks-Berechnung zu vermeiden.
- **Black-Scholes**: Vektorisierte Implementierung mit schneller `norm.cdf` Approximation (Abramowitz & Stegun).
- **Breakevens**: Numerische Suche nach Nullstellen in der geglätteten Payoff-Funktion.

### Bekannte Einschränkungen im GBM-Modell
In einem rein theoretischen GBM-Modell mit konstantem Sigma hat "Hold-to-Expiration" mathematisch immer einen höheren oder gleichen EV wie ein gemanagter Trade (Optional Stopping Theorem). Der reale Vorteil des Tastytrade-Styles wird erst durch **stochastische Volatilität** (Heston-Modell) oder **IV-Shocks** im Simulator sichtbar.

---

## 5. Anwendung in Skuld
Die Simulationsergebnisse fließen direkt in die UI (`spreads.py`, `iron_condors.py`) ein, um dem Nutzer einen objektiven Vergleich zwischen passiven und aktiven Strategien zu ermöglichen.
