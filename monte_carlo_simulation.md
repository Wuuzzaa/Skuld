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
-   **Take Profit (TP) - Ziel 50%**: 
    -   **Beschreibung**: Schließt die Position, sobald 50% des maximal möglichen Gewinns (bei Credit-Spreads das eingenommene Premium) erreicht sind.
    -   **Ziel**: Gewinne sichern, bevor Preisschwankungen sie zunichtemachen.
-   **Stop Loss (SL) - Ziel 200%**:
    -   **Beschreibung**: Schließt die Position, wenn der Verlust das Zweifache des eingenommenen Premiums erreicht (3x das ursprüngliche Risiko bei manchen Definitionen, hier meist 200% des Premiums als Verlust-Trigger).
    -   **Ziel**: Vermeidung von "Tail-Risk" und extremen Ausreißern.
-   **DTE Close - Ziel 21 Tage**:
    -   **Beschreibung**: Schließt den Trade spätestens 21 Tage vor dem Verfall (bei einer ursprünglichen Laufzeit von ca. 45 DTE).
    -   **Ziel**: Eliminierung des Gamma-Risikos. In den letzten 21 Tagen reagiert der Optionspreis extrem empfindlich auf kleine Preisbewegungen des Basiswerts.
-   **Planned DTE (optional)**:
    -   **Beschreibung**: Ermöglicht das Erzwingen eines Exits nach einer festen Anzahl von Tagen (z.B. Schließen nach genau 14 Tagen, unabhängig von TP/SL).

### Der "Edge" (Vorteil)
1.  **Volatilitäts-Mean-Reversion (Vola-Crush)**: In der Realität ist IV oft "mean-reverting". Nach einem Anstieg (IV-Spike) fällt sie meist schnell zurück. Das TP-Ziel wird dadurch oft viel früher erreicht, als es der reine Zeitwertverfall (Theta) vermuten lässt.
2.  **Höherer annualisierter EV**: Durch das frühe Schließen wird Kapital frei, das sofort in neue Trades mit hoher Wahrscheinlichkeit reinvestiert werden kann. 
3.  **Verbesserte Sharpe-Ratio**: Die Varianz der PnL wird reduziert, da die "hässlichen" Verluste am Ende der Laufzeit (Gamma-Explosion) vermieden werden.

### Realitätsnahe Simulation (Tastytrade-Style)
In der aktuellen Version (2024/2025) wurde die Simulation massiv verbessert, um den "Tastytrade-Edge" realistisch abzubilden:

1.  **Vola-Crush (IV Mean-Reversion)**: 
    -   Wenn der **IV Rank (IVR)** über 50 liegt, wird automatisch das `IVShockModel` aktiviert (in `spreads_calculation.py`).
    -   Dieses simuliert, dass eine hohe implizite Volatilität dazu neigt, während der Laufzeit des Trades auf ein normales Niveau zurückzufallen (Mean-Reversion).
    -   Dies führt dazu, dass das **Take Profit (TP) Ziel von 50%** statistisch deutlich häufiger und schneller erreicht wird, als es ein reines Zeitwertverfall-Modell (GBM) vorhersagen würde.

2.  **Berücksichtigung von Skew & Smile**:
    -   Der Simulator akzeptiert nun für jedes einzelne Leg eine eigene **implizite Volatilität (IV)** sowie die Greeks (**Delta, Gamma, Vega, Theta**).
    -   Dadurch werden Preisunterschiede zwischen OTM-Puts und OTM-Calls (Skew) in der Pfad-Simulation korrekt berücksichtigt. Der Simulator skaliert die Volatilität entlang des Preispfades proportional, um die ursprüngliche Skew-Struktur beizubehalten.

3.  **Greeks & Validierung**:
    -   Der Simulator nutzt nun die vom Markt gelieferten Greeks der einzelnen Legs für eine präzisere Initialisierung der Black-Scholes-Modelle für die Zwischenbewertungen während der Simulation.
    -   Greeks für die Gesamtstrategie werden mittels finiter Differenzen unter Verwendung von *Common Random Numbers (CRN)* berechnet, um Rauschen zu minimieren.

4.  **Batch-Simulationen**:
    -   Unterstützung für effiziente Massen-Simulationen (`calculate_expected_value_batch`), was besonders für die Optimierung von Scans nützlich ist.

---

## 3. Analyse & Metriken

Der Simulator liefert nicht nur den Erwartungswert (EV), sondern eine umfassende Risikoanalyse:

-   **EV (Static)**: Erwartungswert beim Halten bis zum Verfall.
-   **EV (Managed)**: Erwartungswert unter Anwendung der TP/SL/DTE-Regeln.
-   **EV/Tag & EV annualisiert**: Entscheidende Metriken für den Vergleich von Strategien mit unterschiedlichen Haltedauern (basierend auf i.i.d. Re-Deployment).
-   **CVaR (Conditional Value at Risk)**: Der durchschnittliche Verlust in den schlimmsten 5% der Fälle (Tail-Risk).
-   **Win-Probability**: Wahrscheinlichkeit für einen positiven Ausgang.
-   **95% Konfidenzintervalle**: Berechnet via Bootstrapping für den Erwartungswert.
-   **Exit-Statistiken**: Aufschlüsselung, wie oft der Trade durch TP, SL, DTE oder Verfall beendet wurde.

---

## 4. Technische Implementierung & Refactoring-Notizen

### Aktueller Stand (Refactoring 2024/2025)
- **RNG**: Umstellung auf `np.random.default_rng()` für bessere Performance und Thread-Sicherheit.
- **Pfad-Cache**: Optimierte Speicherung von Preispfaden, um redundante Simulationen bei der Greeks-Berechnung zu vermeiden.
- **Black-Scholes**: Vektorisierte Implementierung mit schneller `norm.cdf` Approximation (Abramowitz & Stegun).
- **Breakevens**: Numerische Suche nach Nullstellen in der geglätteten Payoff-Funktion.
- **Backwards Compatibility**: Einführung des `UniversalOptionsMonteCarloSimulator` Alias zur Unterstützung älterer API-Aufrufe mit Dictionary-Listen statt `OptionLeg`-Objekten.

### Bekannte Einschränkungen im GBM-Modell
In einem rein theoretischen GBM-Modell mit konstantem Sigma hat "Hold-to-Expiration" mathematisch immer einen höheren oder gleichen EV wie ein gemanagter Trade (Optional Stopping Theorem). Der reale Vorteil des Tastytrade-Styles wird erst durch **stochastische Volatilität** (Heston-Modell) oder **IV-Shocks** im Simulator sichtbar.

---

## 5. Anwendung in Skuld
Die Simulationsergebnisse fließen direkt in die UI (`spreads.py`, `iron_condors.py`) ein, um dem Nutzer einen objektiven Vergleich zwischen passiven und aktiven Strategien zu ermöglichen.
