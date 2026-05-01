# Analyse: Universal Monte Carlo Simulation in Skuld

## 1. Verständnis der Datei `monte_carlo_simulation.py`

Die Datei implementiert den `UniversalOptionsMonteCarloSimulator`, ein zentrales Werkzeug im Skuld-Projekt zur Bewertung von Optionsstrategien. Anders als klassische Black-Scholes-Modelle, die oft auf einzelne Optionen oder einfache Spreads beschränkt sind, ermöglicht dieser Simulator die Analyse beliebiger Multi-Leg-Strategien durch numerische Simulation.

### Kernfunktionalität
- **Geometrische Brownsche Bewegung (GBM):** Der Simulator modelliert den Aktienpreis am Verfallstag basierend auf der aktuellen Volatilität, der Laufzeit (DTE) und dem risikofreien Zinssatz.
- **Risikoneutrale Bewertung:** Die Simulation nutzt den risikofreien Zinssatz (abzüglich Dividendenrendite) als Drift, was die Grundlage für die Optionspreisbewertung nach der modernen Finanztheorie ist.
- **IV-Korrektur (Auto-Modus):** Ein besonderes Merkmal ist die systematische Korrektur der impliziten Volatilität (IV). Basierend auf Forschungsergebnissen zur Volatilitätsrisikoprämie (VRP) und dem "Contango"-Effekt der VIX-Terminstruktur wird die Markt-IV reduziert, um realistischere Erwartungswerte zu erhalten.
- **Transaktionskosten:** Diese werden pro Kontrakt (100 Aktien) berücksichtigt, was für eine realistische Netto-Profit-Berechnung unerlässlich ist.
- **Vielseitigkeit:** Jede Strategie wird als Liste von "Legs" (Optionen) definiert, wodurch komplexe Gebilde wie Iron Condors, Butterflies oder benutzerdefinierte Spreads einheitlich bewertet werden können.

### Rolle im Skuld-Ökosystem
- **`options_utils.py`:** Fungiert als Brücke. Hier wird der Simulator instanziiert, um den `expected_value` und andere Metriken für die UI zu berechnen.
- **`spreads_calculation.py` & `spreads.py`:** Diese nutzen die berechneten Werte, um dem Nutzer profitable Trades (z. B. mit positivem Erwartungswert) anzuzeigen und zu filtern.

---

## 2. Mögliche Verbesserungen & Refactoring

Trotz der soliden Basis gibt es Bereiche, die optimiert werden können, um Performance, Genauigkeit und Wartbarkeit zu steigern.

### A. Performance & Vektorisierung
- **Vektorisierung der Payoff-Berechnung:** In `_calculate_strategy_payoffs` wird über die Legs iteriert und für jedes Leg `calculate_single_option_payoff` aufgerufen. Während die Simulation selbst vektorisiert ist, könnte die gesamte Strategie-Matrix (Simulations x Legs) noch effizienter in einem einzigen NumPy-Block verarbeitet werden.
- **NumPy Random Generator:** Die Verwendung von `np.random.seed` und `np.random.standard_normal` ist zwar funktional, aber veraltet. Der neuere `np.random.default_rng()` ist schneller und bietet eine bessere statistische Qualität.

### B. Mathematische & Fachliche Erweiterungen (Geplante Features)
- **Pfadabhängige Simulation:** Um Stop-Loss (SL) und Take-Profit (TP) während der Laufzeit zu bewerten, wird von einer reinen Endpreis-Simulation auf eine Pfad-Simulation (z.B. tägliche Schritte) umgestellt.
- **Stop-Loss & Take-Profit:** Implementierung einer Logik, die Optionen schließt, sobald die Prämie einen Schwellenwert erreicht (z.B. TP bei 50% der Prämie, SL bei 200%).
- **Leg-spezifische Parameter:** Unterstützung für unterschiedliche DTEs pro Leg und die Möglichkeit, für jedes Leg einen geplanten Schließtag ("planned close day") festzulegen.
- **Fester DTE Close:** Globale oder Leg-spezifische Einstellung, um Positionen bei Erreichen eines bestimmten DTE-Werts (z.B. 21 DTE) glattzustellen.
- **Griechische Variablen (Greeks):** Monte-Carlo-basierte Schätzung von Delta, Gamma und Vega durch kleine Preis- und Volatilitäts-Shifts in der Simulation.
- **Realtime-Performance:** Sicherstellung, dass die Pfad-Simulation durch effiziente NumPy-Vektorisierung flüssig bleibt.

### C. Technische Details der Umsetzung (Konzept)
- **Pfad-Simulation:** Nutzung von geometrischer Brownscher Bewegung (GBM) über mehrere Zeitschritte.
- **Zwischenbewertung:** Da SL/TP auf dem aktuellen Optionspreis basieren, wird während der Pfad-Simulation an jedem Schritt der Black-Scholes-Preis für jedes Leg berechnet.
- **Greeks-Berechnung:**
  - **Delta:** `(EV(S+ds) - EV(S)) / ds`
  - **Vega:** `(EV(vol+dv) - EV(vol)) / dv`
  - **Gamma:** Zweite Ableitung via Preis-Shifts.
  Dies erfordert zusätzliche Simulationsläufe mit leicht veränderten Startparametern.

## 4. SL/TP Strategie-Optimierung & UI-Feedback

Um die profitabelste Strategie zu finden, bietet das System einen direkten Vergleich zwischen der klassischen "Hold-to-Expiration"-Variante und der aktiven Management-Strategie (SL/TP).

### A. Bestimmung der optimalen Parameter
Die optimale SL/TP-Strategie wird durch den Vergleich des Erwartungswerts (EV) ermittelt:
- **Baseline EV:** Erwarteter Gewinn ohne vorzeitiges Schließen.
- **Managed EV:** Erwarteter Gewinn unter Berücksichtigung der SL/TP-Trigger und Pfad-Simulation.
- **Feedback-Metrik:** Die Differenz (`Managed EV - Baseline EV`) zeigt den "Management-Alpha" an. Wenn dieser negativ ist, wäre statistisch gesehen das Halten bis zum Verfall profitabler.

### B. UI-Integration (Spreads & Iron Condor)
In den Seiten `spreads.py` und `iron_condors.py` werden im Konfigurations-Bereich folgende Felder ergänzt:
- **Take Profit (% der Prämie):** Standardmäßig oft 50%. Definiert, bei wie viel Gewinn die Position glattgestellt wird.
- **Stop Loss (% der Prämie):** Standardmäßig oft 200%. Definiert die Verlusttoleranz.
- **Planned Close DTE:** Ermöglicht das Schließen der Position X Tage vor Verfall (z.B. bei 21 DTE), um Gamma-Risiken zu reduzieren.
- **Leg-spezifische DTEs:** (Besonders für Iron Condors) Option, die Put- und Call-Seite mit unterschiedlichen Laufzeiten zu simulieren.

### C. Feedback in der Ergebnisliste
Für jeden gefundenen Trade wird neben dem Standard-EV auch der "Managed EV" angezeigt:
- **Status-Indikator:** Ein Icon (z.B. 🎯) signalisiert, ob die gewählten SL/TP-Einstellungen den EV verbessern oder verschlechtern.
- **Optimaler TP/SL Vorschlag:** Basierend auf der Simulation kann das System einen Korridor vorschlagen (z.B. "Für diesen Spread ist ein TP von 40% optimal").

---

## 5. Performance-Ziele & Optimierung

Durch die Umstellung auf eine Pfad-Simulation und die Berechnung der Greeks steigt die Rechenlast erheblich (Faktor 200x bis 500x). Um die "Realtime"-Usability der Streamlit-Anwendung zu erhalten, werden folgende Optimierungen implementiert:

### A. Massive Vektorisierung
- Nutzung von 3D-NumPy-Arrays `(Simulationen, Tage, Legs)`.
- Black-Scholes-Berechnungen werden als Matrix-Operationen ausgeführt, um tausende Optionen gleichzeitig auf CPU-Vektorebene zu bewerten.

### B. Effiziente Greeks-Berechnung
- Verwendung von **Common Random Numbers (CRN)**: Dieselbe Zufallsmatrix wird für die Basis-Simulation und die verschobenen Läufe (Delta/Vega-Shifts) genutzt. Dies reduziert das statistische Rauschen und erlaubt eine hohe Präzision bei geringerer Simulationsanzahl.

### C. Zielwert
- Trotz des Mehraufwands soll die Berechnung einer komplexen Strategie (z. B. Iron Condor mit SL/TP und Greeks) unter **0,5 Sekunden** bleiben.

---

## 6. Nächste Schritte
Sobald dieses Konzept bestätigt ist, werden folgende Änderungen im Code vorgenommen:
1.  **Erweiterung der `OptionLeg` Struktur** (Dataclass) um SL/TP, Custom DTE und Schließtag.
2.  **Anpassung von `spreads.py` und `iron_condors.py` UI:** Integration der SL/TP-Eingabefelder im Konfigurations-Expander.
3.  **Anpassung von `simulate_stock_prices`** für Pfad-Generierung.
4.  **Implementierung der SL/TP/Close-Logik** in der Payoff-Berechnung unter Verwendung von Black-Scholes für Zwischenpreise.
5.  **Hinzufügen einer Greeks-Berechnungsmethode** in den Simulator.
6.  **Erweiterung der UI-Anzeige:** Vergleich von Baseline-EV und Managed-EV in den Ergebnislisten.
