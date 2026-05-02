# Anwenderhandbuch: Monte Carlo Debug Seite

Diese Seite ermöglicht es, komplexe Optionsstrategien manuell zu konfigurieren und mittels einer Monte-Carlo-Simulation zu bewerten. Sie dient zur Validierung von Handelsideen und zur Überprüfung der mathematischen Modelle in Skuld.

## 1. Konfiguration der Marktparameter (Sidebar)

In der linken Seitenleiste ("Global Settings") werden die Rahmenbedingungen für die Simulation festgelegt:

*   **Underlying Price**: Der aktuelle Kurs der Aktie oder des Index.
*   **Implied Volatility (IV)**: Die vom Markt erwartete Schwankungsbreite (annualisiert). Ein Wert von 0.30 entspricht 30%.
*   **Days to Expiration (DTE)**: Die Restlaufzeit der Strategie in Tagen.
*   **Risk Free Rate**: Der aktuelle risikofreie Zinssatz (wichtig für die Abzinsung).
*   **Dividend Yield**: Die erwartete Dividendenrendite des Basiswerts.

### Simulationseinstellungen
*   **Number of Simulations**: Standardmäßig 10.000. Mehr Simulationen erhöhen die Genauigkeit, verlängern aber die Rechenzeit.
*   **IV Correction Mode**: 
    *   `auto`: Verwendet ein internes Modell zur Korrektur der IV (berücksichtigt die Volatilitätsrisikoprämie).
    *   `none`: Keine automatische Korrektur. Es kann ein manueller Faktor (0.0 bis 1.0) angegeben werden.
*   **Transaction Cost**: Fixkosten pro Kontrakt für den gesamten Trade (Öffnen und Schließen).

## 2. Strategie-Erstellung (Main Area)

Hier werden die einzelnen Bestandteile (Legs) der Optionsstrategie definiert.

*   **Type**: Call oder Put.
*   **Action**: Long (Kauf) oder Short (Verkauf).
*   **Strike**: Der Ausübungspreis der Option.
*   **Premium**: Die Prämie pro Aktie (z.B. 1.50 für einen Kontraktwert von 150$).

### Strategie-Management (Zentral)
Über der Liste der Legs können globale Regeln für die gesamte Strategie festgelegt werden. Die Bedingungen werden in der Simulation täglich geprüft:
*   **Strategy Take Profit %**: Schließt die gesamte Strategie, wenn der Gesamtgewinn diesen Prozentsatz der eingenommenen/gezahlten Prämie erreicht.
    - Beispiel Credit: Bei $1.00 Credit und 50% TP wird die Position geschlossen, wenn der Rückkaufwert auf $0.50 fällt.
    - Beispiel Debit: Bei $1.00 Debit und 50% TP wird die Position geschlossen, wenn der Marktwert auf $1.50 steigt.
*   **Strategy Stop Loss %**: Schließt die gesamte Strategie bei entsprechendem Verlust.
    - **Besonderheit Credit-Spreads**: Ein Stop Loss von 200% bedeutet, dass die Position geschlossen wird, wenn der *Verlust* das Doppelte der eingenommenen Prämie beträgt. 
    - Beispiel Credit: Bei $1.00 Credit und 200% SL wird die Position geschlossen, wenn der Rückkaufwert $3.00 erreicht (Kauf für 3.00 - Erhalt von 1.00 = 2.00 Netto-Verlust).
    - Beispiel Debit: Bei $1.00 Debit und 50% SL wird die Position geschlossen, wenn der Marktwert auf $0.50 fällt (Verlust = $0.50 = 50% von $1.00).
*   **Strategy DTE Close**: Schließt alle Positionen automatisch, wenn die angegebene Anzahl an Resttagen erreicht ist (z.B. Exit bei 21 DTE). Diese Regel hat am entsprechenden Tag Priorität vor TP/SL.

## 3. Analyse-Ergebnisse

Nach Klick auf **Run Simulation** werden folgende Daten berechnet:

### Kennzahlen (Metrics)
*   **Expected Value (EV)**: Der durchschnittlich zu erwartende Gewinn/Verlust pro Trade unter Berücksichtigung aller Szenarien und des Managements.
*   **Prob. Profit / Loss**: Die statistische Wahrscheinlichkeit, mit einem Gewinn oder Verlust abzuschließen.
*   **Max Profit / Loss**: Die extremsten Ergebnisse, die in der Simulation aufgetreten sind.
*   **Net Cashflow**: Die beim Öffnen der Strategie gezahlte oder erhaltene Prämie.

### Exit-Statistiken (🛡️ Exit Statistics)
Wenn Management-Regeln aktiv sind, zeigt dieser Bereich, wie oft welche Bedingung zum Ausstieg geführt hat:
*   **Take Profit**: Anzahl/Prozent der Simulationen, die das Gewinnziel erreicht haben.
*   **Stop Loss**: Anzahl/Prozent der Simulationen, die im Stop-Loss gelandet sind.
*   **DTE Close**: Ausstiege aufgrund der Restlaufzeit.
*   **Expiration**: Trades, die bis zum Ende (0 DTE) gehalten wurden.
*   **Planned Exit**: Ausstiege, die zum geplanten Zeitpunkt erfolgten (falls keine anderen Trigger griffen).

### Simulation Greeks
Diese Werte zeigen die Sensitivität der *gesamten Strategie* (inkl. Management):
*   **Delta**: Wie stark sich der EV ändert, wenn der Aktienkurs um 1$ steigt.
*   **Gamma**: Wie stark sich das Delta ändert.
*   **Vega**: Wie stark sich der EV ändert, wenn die IV um 1% steigt.

### Visualisierungen
*   **Payoff Diagram**: Zeigt den Gewinn/Verlust am Ende der Laufzeit (oder zum Exit-Zeitpunkt) in Abhängigkeit vom Aktienkurs.
*   **Price Distribution**: Ein Histogramm, das zeigt, welche Aktienkurse am Ende der Simulation am wahrscheinlichsten sind.

## 4. Interpretation der Daten
Ein positiver **Expected Value (EV)** deutet darauf hin, dass die Strategie statistisch gesehen langfristig profitabel sein sollte, sofern die Eingabeparameter (IV, Drift) die Realität korrekt widerspiegeln.
