# Refactoring-Analyse: `src/monte_carlo_simulation.py`

Dieses Dokument beschreibt detailliert den Aufbau, die Funktionen und Verantwortlichkeiten des Moduls `src/monte_carlo_simulation.py`, identifiziert Bugs sowie semantische Schwächen und schlägt konkrete Performance- und Refactoring-Maßnahmen vor.

---

## 1. Überblick

Das Modul stellt die Klasse `UniversalOptionsMonteCarloSimulator` zur Verfügung. Sie führt eine Monte-Carlo-Simulation für beliebige Multi-Leg Options-Strategien durch (z. B. Iron Condor, Vertical Spreads, Straddles). Sie unterstützt:

- Geometrische Brownsche Bewegung (GBM) zur Simulation von Aktienpreisen unter risikoneutraler Bewertung.
- Bewertung beliebiger Multi-Leg-Strategien zum Verfall (klassisch) sowie mit aktivem Trade-Management (Take Profit, Stop Loss, DTE Close, Planned DTE).
- IV-Korrektur (statisch, automatisch DTE-basiert oder manuell prozentual).
- Vektorisiertes Black-Scholes-Pricing inkl. einer schnellen `norm.cdf`-Approximation (Abramowitz & Stegun).
- Berechnung von Greeks (Delta, Gamma, Vega) per finiten Differenzen.
- Batch-Auswertung vieler Strategien mit gemeinsamer Pfad-Cache-Nutzung.
- Suche von Breakevens aus den Simulationen.
- Zusätzlich: Hilfsfunktion `print_strategy_analysis` zur Konsolen-Ausgabe.

Das Modul ist intern stark vektorisiert (NumPy) und nutzt `functools.lru_cache` zur Wiederverwendung von Pfaden.

---

## 2. Architektur und Funktionen im Detail

### 2.1 Konstruktor `__init__`
- Speichert Roh-Volatilität (`raw_volatility`) und berechnete (korrigierte) Volatilität (`volatility`).
- Berechnet `time_to_expiration = dte / 365` (Kalenderjahr, nicht 252 Handelstage).
- Wendet IV-Korrektur über `_apply_iv_correction` an.
- Setzt globalen NumPy-Seed (`np.random.seed`) – Nebeneffekt auf Prozess-Ebene.

### 2.2 IV-Korrektur
- `_calculate_iv_correction_factor(dte)`: heuristische Formel `base_bias + 0.05 * log(dte/30)` mit Bounds `[0.08, 0.25]`.
- `_apply_iv_correction`: drei Modi: `"auto"`, `"none"`, oder Float in `[0.0, 1.0]`. Mindest-IV 1 % wird erzwungen.

### 2.3 Pfaderzeugung
- `_generate_price_paths_cached` (statisch, `lru_cache(128)`): erzeugt GBM-Pfade. Liefert `(num_simulations, dte+1)`-Matrix.
- `simulate_stock_price_paths`: Wrapper, der hashbare Argumente an die statische Methode übergibt.
- `simulate_stock_prices`: Legacy-Helfer, gibt nur die Endpreise zurück.

### 2.4 Payoff-Berechnung am Verfall
- `calculate_option_intrinsic_value`: skalare innere Wertberechnung.
- `calculate_single_option_payoff`: vektorisiert pro Leg, inkl. Transaktionskosten und 100 Shares-Multiplikator.
- `_calculate_strategy_payoffs`: aggregiert alle Legs zu Gesamt-Payoffs und Initial-Cashflow.

### 2.5 Black-Scholes vektorisiert
- `_black_scholes_vectorized`: Broadcasting-fähig, mit interner `fast_norm_cdf` (Abramowitz & Stegun, 5 Terme).
- Sondere Behandlung `T <= 0`: intrinsischer Wert.

### 2.6 Trade-Management
- `_calculate_managed_strategy_payoffs`: simuliert Tag für Tag, prüft Trigger TP/SL/DTE-Close/Planned-DTE auf **Strategie-Ebene**.
- Berechnet `spread_offset = strat_premium − entry_bs_strat_value` und addiert ihn auf theoretische Werte, um Marktspreads zu simulieren.
- Trigger-Prioritäten: `DTE Close > TP > SL > Planned DTE`.
- Speichert `last_exit_reasons`, `last_closed_steps` als Diagnose.

### 2.7 Erwartungswert & Greeks
- `calculate_expected_value`: ruft je nach Vorhandensein von Management-Parametern den passenden Pfad auf, diskontiert mit `exp(-r*T)`.
- `calculate_expected_value_batch`: Schleife über Strategien; nutzt einmalige Pfad-Simulation, sofern keine Strategie Management nutzt.
- `calculate_greeks` / `calculate_greeks_batch`: zentrale Differenzen für Delta/Gamma, Vorwärtsdifferenz für Vega. Common Random Numbers werden über den `lru_cache` automatisch erreicht (gleiche Parameter ⇒ gleicher Pfad).

### 2.8 Breakeven-Erkennung
- `find_breakeven_from_simulations`: sortiert nach Preis, glättet die Payoffs (Moving Average), sucht Vorzeichenwechsel und clustert nahe beieinanderliegende Punkte.

### 2.9 Gesamtanalyse
- `analyze_strategy`: berechnet EV, Wahrscheinlichkeiten, Risikomaße, Perzentile, Breakevens, Management-Statistiken und liefert großes Result-Dict.
- `print_strategy_analysis`: hübsche Konsolenausgabe.

---

## 3. Bugs und Korrektheitsprobleme

### 3.1 Globaler Seed-Reset (Side-Effect)
`__init__` und `_generate_price_paths_cached` rufen `np.random.seed(...)` auf dem **globalen** RNG auf. Das verändert den Zufallszustand für den gesamten Prozess und kann andere Module unerwartet beeinflussen.
**Fix:** `np.random.default_rng(seed)` (lokaler `Generator`) verwenden.

### 3.2 `lru_cache` auf statischer Methode mit `np.ndarray`-Rückgabe
- Der Cache hält numpy-Arrays im Speicher. Bei vielen unterschiedlichen Parametern kann er schnell mehrere GB belegen (`maxsize=128`, jedes Array `num_simulations × (dte+1)`).
- Da `_generate_price_paths_cached` zusätzlich `np.random.seed(...)` aufruft, wechselt der globale Seed bei Cache-**Misses**, aber nicht bei Cache-**Hits** – inkonsistentes Verhalten.
- Rückgaben sind veränderbare Arrays; ein Aufrufer könnte das Cache-Objekt versehentlich mutieren.

### 3.3 IV-Korrektur-Validierung inkonsistent
- In `__init__` wird der Faktor für `iv_correction == "auto"` (case-sensitive) gesetzt, aber `_apply_iv_correction` vergleicht `lower() == "auto"`. Mit z. B. `"AUTO"` ergeben sich unterschiedliche Werte für `volatility` und `iv_correction_factor`.
- `iv_correction_factor` wird bei String-Werten ungleich `"auto"`/`"none"` stillschweigend auf `0.0` gesetzt, statt einen `ValueError` zu werfen, obwohl `_apply_iv_correction` das tut.

### 3.4 `_calculate_managed_strategy_payoffs` – Schleifen-Korrektheit
- `closed_at_step` und `exit_prices` haben Form `(sim, leg)`; bei Triggern werden alle Beine eines Sims gleichzeitig geschlossen. Die Variable `closed_at_step` wird **deklariert, aber nie gefüllt** (toter Code).
- `step_size`-Optimierung ist auskommentiert, aber `step_size = 1` wird gesetzt und nie verwendet.
- Bei `num_legs == 0` werden `entry_bs_prices`/`spread_offset` mit leeren Arrays gerechnet → potentieller Edge-Case.
- `print(f"DEBUG WARNING: ...")` statt `logger.warning(...)` – verstößt gegen Logging-Guidelines.
- Nach der Schleife wird für nicht getriggerte Sims `sim_exit_reasons[...] = 0` redundant gesetzt (Initialwert); zudem wird der **nicht-letzte** Step verwendet, falls `num_steps - 1 == self.dte`, was korrekt ist – aber die Auswertung erfolgt zum letzten **Pfadpunkt**, nicht in der eigentlichen `for`-Schleife. Konsistenter wäre, den letzten Step regulär in die Schleife zu integrieren.

### 3.5 Black-Scholes Edge Cases
- `np.log(S / K)` kracht still bei `S <= 0` oder `K <= 0` (gibt `nan`/`-inf`). Inputs werden nicht validiert.
- `T_safe` mit `1e-9` führt zu sehr großen `d1`/`d2` und damit zu Werten, die mit der A&S-Approximation außerhalb des stabilen Bereichs liegen können (Approximation ist nominell für `|x| < ~7` gut).
- `is_call` muss als boolesches Array übergeben werden; `np.where(is_call, ...)` wird mit dtype-bool korrekt arbeiten. Bei `int`-Werten werden Calls/Puts trotzdem nach Truthy ausgewählt, aber das ist fragil.

### 3.6 `analyze_strategy` – Performance-Bug in `spread_offset`
Die Zeile in `analyze_strategy` ist eine extreme Einzeiler-Konstruktion:

```python
'spread_offset': initial_cashflow - (np.mean(np.sum(np.where(
    is_longs_all,
    self._black_scholes_vectorized(...),
    -self._black_scholes_vectorized(...)
), axis=1)) * 100) if not has_management else (initial_cashflow - entry_bs_strat_val),
```

- `_black_scholes_vectorized` wird **zweimal** mit identischen Argumenten aufgerufen.
- Es wird `np.mean(...)` über eine Achse genommen, obwohl der Eingangswert `S` skalar ist – der Mittelwert ist trivial.
- Sehr unleserlich; sollte in eine eigene Methode extrahiert werden.

### 3.7 `find_breakeven_from_simulations`
- `np.convolve(..., mode='same')` führt zu Randartefakten (Glättung am Anfang/Ende ist zu klein gewichtet) → Fehlsignale an den Rändern.
- Die anschließende lineare Interpolation nutzt **die ungeglätteten** `payoffs`, während die Vorzeichenwechsel auf den geglätteten Werten erkannt werden – Inkonsistenz.
- Sortieren über `zip + sort` mit Python-Listen ist langsam; `np.argsort` reicht.

### 3.8 `time_to_expiration` Diskrepanz
`dte / 365` (Kalender) vs. typische Black-Scholes-Konvention `dte / 365.25` oder Handelstage. Konsistent ist es immerhin – aber dokumentieren.

### 3.9 `print(...)`-Aufrufe in Produktivpfad
Mehrere `print` in `_calculate_managed_strategy_payoffs` und `__main__` – sollten Logger sein.

### 3.10 Unbenutzte Imports
- `pandas as pd`, `from typing import Optional`, `from scipy.stats import norm` werden nicht verwendet (nach Einführung der `fast_norm_cdf`).

### 3.11 Strategieweite Management-Parameter
`_calculate_managed_strategy_payoffs` zieht TP/SL/DTE-Close/Planned-DTE aus dem **ersten** Leg, in dem der Wert nicht `None` ist (`next(...)`), behandelt sie also als Strategie-Parameter, obwohl sie pro Leg im Dict liegen. Das widerspricht der API und kann zu falschen Ergebnissen führen, wenn Legs unterschiedliche Werte haben. Entweder:
- Per-Leg-Management implementieren, **oder**
- Management eindeutig auf Strategie-Ebene ziehen (eigenes Argument bzw. Dict-Eintrag pro Strategie).

### 3.12 `expected_value`-State
`calculate_expected_value` setzt `self.expected_value`. `calculate_greeks` ruft die Methode mehrfach für Bumps auf und überschreibt diesen State – am Ende steht im Objekt der EV des letzten Vega-Bumps statt des Basis-EV.

---

## 4. Performance-Optimierungen

### 4.1 Pfaderzeugung
- **`np.cumsum` + `np.exp`** für GBM ist okay; alternativ direkt:
  ```python
  Z = rng.standard_normal((N, T))
  log_paths = np.empty((N, T+1))
  log_paths[:, 0] = 0
  np.cumsum((drift - 0.5*sigma**2)*dt + sigma*sqrt_dt*Z, axis=1, out=log_paths[:, 1:])
  paths = current_price * np.exp(log_paths)
  ```
  Spart das `np.hstack` mit Nullspalte.
- Für **nur Endpreise** (klassische Strategien) reicht **eine** Zufallszahl pro Sim:
  ```python
  ST = S0 * exp((r - 0.5*sigma^2)*T + sigma*sqrt(T)*Z)
  ```
  Massive Beschleunigung (Faktor ~`dte`).
- `simulate_stock_prices` nutzt aktuell den vollen Pfad → unnötig teuer.

### 4.2 Cache-Strategie
- `lru_cache` auf statischer Methode, die `np.ndarray` zurückgibt, führt zu Speicher-Leaks bei vielen Parameterkombinationen. Besser:
  - Eigener kleiner Dictionary-Cache mit klarer Bereinigung.
  - Cache-Key inkl. `endpoints_only`-Flag, damit ein dedizierter günstiger Pfad verwendet werden kann.

### 4.3 Black-Scholes
- `fast_norm_cdf` ist gut. Alternative: `scipy.special.ndtr` ist in C implementiert und etwa gleich schnell, dabei numerisch stabiler.
- `np.log(S/K)` und `np.exp(-r*T)` können bei wiederholten Aufrufen mit identischen `T`/`r` und vielen `K` durch Vorberechnung gespart werden.
- `_black_scholes_vectorized` wird in `analyze_strategy` mehrfach mit denselben Argumenten aufgerufen; einmal berechnen und wiederverwenden.

### 4.4 Management-Schleife
- Tagesweise Schleife `for step in range(1, num_steps)` mit BS-Bewertung pro Tag ist O(N·T·L). Optimierungen:
  - Frühzeitiges Beenden: nach Trigger nicht mehr neu berechnen (bereits umgesetzt via `active_sims`-Maske).
  - **Step-Size > 1** (z. B. alle 2 Tage) bei großen DTE – aktuell auskommentiert; mit Toleranz aktivieren, sofern TP/SL nicht haarscharf getroffen werden müssen.
  - **Vektorisierung über Steps**: BS pro Step kann gleichzeitig für alle aktiven Sims gerechnet werden – wird gemacht, aber das Reshape/Slicing erzeugt Kopien. `np.ascontiguousarray` einmalig vorbereiten.
  - `t_years` und konstante Größen außerhalb der Schleife vorab berechnen (teilweise erledigt).
  - Trigger-Logik kombiniert in einem einzigen `np.select`/Bitmasken-Ausdruck statt mehrerer `if`/`np.where`.

### 4.5 Batch-Auswertung
- `calculate_expected_value_batch` wiederholt die Management-Berechnung pro Strategie; bei vielen Strategien ohne Management ist die innere Schleife okay, könnte aber komplett vektorisiert werden, indem die Strategie-Legs als 2D-Arrays über Strategien gestapelt werden (mit Padding oder gleicher Leg-Anzahl).
- Diskontierungsfaktor wird einmal vorberechnet – gut. Aber `np.zeros(num_sim)` pro Strategie kann durch Wiederverwendung eines Buffers ersetzt werden.

### 4.6 Greeks
- Drei volle Re-Simulationen sind teuer. **Pathwise/Likelihood-Ratio-Methoden** liefern Greeks aus einem Lauf.
- Mindestens: **Vektorisierte Bumps** über `current_price`-Array statt drei serieller Aufrufe.
- Common Random Numbers funktionieren nur, wenn der gleiche RNG-Zustand verwendet wird; aktuell hängt das vom Cache ab und ist fragil.

### 4.7 Speicher
- `analyze_strategy` gibt `simulated_prices` und `total_payoffs` zurück (große Arrays). Für reines Screening unnötig – über Flag steuerbar machen.

---

## 5. Refactoring-Vorschläge (strukturell)

1. **RNG kapseln**: Eigene Klasse / `np.random.Generator` als Member, kein globaler Seed.
2. **Pfad-Erzeugung trennen**:
   - `_simulate_terminal_prices()` (1 Z je Sim) für klassische Strategien.
   - `_simulate_paths()` (T+1 Spalten) nur, wenn Management aktiv ist.
3. **Black-Scholes als eigenes Modul** (`src/pricing/black_scholes.py`), inkl. `fast_norm_cdf`.
4. **Strategy-Datenmodell**: Statt `List[Dict]` ein `@dataclass OptionLeg` und `@dataclass Strategy` mit Validierung. Management-Parameter explizit auf `Strategy`-Ebene.
5. **ManagementEngine** als eigene Klasse (`StrategyManagementEngine`), die Trigger-Logik kapselt; Prioritäten und Toleranzen konfigurierbar.
6. **Result-Objekt**: `dataclass AnalysisResult` statt riesigem Dict, klar typisiert.
7. **Logging**: `print` ersetzen durch `logger = logging.getLogger(__name__)`. Debug-Hinweise in `_calculate_managed_strategy_payoffs` als `logger.debug(...)`.
8. **Aufräumen**: ungenutzte Imports entfernen, `closed_at_step` und kommentierten `step_size`-Code löschen.
9. **Konfigurierbarkeit**: Diskontierungs-Konvention (365 vs. 252) als Konstante.
10. **Tests**: Reproduzierbare Smoke-Tests für jede Methode (TP-Trigger, SL-Trigger, klassische Auflösung, Greeks-Konsistenz, IV-Korrektur-Modi). Aktuell keinen Unit-Test im Modul selbst.
11. **Dokumentation**: Public API mit ausführlichen Docstrings; interne Helfer als `_private`. Englischsprachige Docstrings sind bereits konsequent.
12. **Validierung**: Inputs (`current_price > 0`, `volatility > 0`, `dte >= 0`, alle Strikes > 0, Premiums >= 0) frühzeitig prüfen.

---

## 6. Konkrete Quick-Wins (priorisiert)

1. **`simulate_stock_prices` ersetzen** durch Single-Step GBM (`exp((r-0.5σ²)T + σ√T·Z)`) – sofortige Beschleunigung im klassischen Pfad.
2. **`np.random.default_rng(seed)` einführen** – beseitigt globalen Seed-Bug.
3. **`spread_offset`-Einzeiler in `analyze_strategy`** in Methode auslagern, BS nur einmal aufrufen.
4. **`print` → `logger`** in `_calculate_managed_strategy_payoffs`.
5. **`closed_at_step` und auskommentierter `step_size`-Code entfernen**.
6. **IV-Korrektur-Vergleich case-insensitive** im `__init__` vereinheitlichen.
7. **`expected_value`-State entfernen** (oder nur in `calculate_expected_value` direkt verwendet, nicht durch Greeks-Bumps überschrieben).
8. **Per-Leg- vs. Strategy-Management** dokumentieren oder Modell trennen.
9. **`find_breakeven_from_simulations`**: NumPy-only, konsistent geglättete Payoffs für Interpolation verwenden.

---

## 7. Bekannte semantische Risiken

- **IV-Korrektur** ist heuristisch und an einer Stelle (`base_bias = 0.08`) hartcodiert – sollte konfigurierbar sein, sonst sind alle EVs systematisch verschoben.
- **`spread_offset`-Modell** addiert eine Konstante auf theoretische BS-Werte über alle Tage; in der Realität schließt sich der Bid/Ask-Spread bei Verfall – Modellgrenze beachten.
- **Trigger-Prioritäten** sind hartcodiert (`DTE Close > TP > SL > Planned DTE`); reale Order-Flows könnten anders aussehen.
- **`fast_norm_cdf`** ist eine Approximation mit ~7.5e-8 maximalem absolutem Fehler – im normalen Strike-Bereich ausreichend, an extremen Tails (`|x| > 7`) drift möglich.

---

## 8. Vorgeschlagene Test-Suite (Auszug)

- `test_terminal_only_paths_match_full_paths`: `simulate_stock_prices()` muss statistisch identisch zum letzten Spalteneintrag von `simulate_stock_price_paths()` sein (gleicher Seed).
- `test_iv_correction_modes`: `"auto"`, `"AUTO"`, `"none"`, `0.0`, `0.15`, ungültige Werte.
- `test_classic_iron_condor_breakevens`: Breakevens innerhalb erwarteter Bandbreite.
- `test_managed_tp_trigger_credit`: Credit-Strategie schließt korrekt bei TP-Schwelle.
- `test_managed_sl_trigger_debit`: Debit-Strategie schließt korrekt bei SL-Schwelle.
- `test_dte_close_priority_over_tp`: DTE-Close überschreibt TP, wenn beides am selben Tag triggert.
- `test_greeks_finite_difference_consistency`: Delta + Gamma konsistent zu kleinem Bump.
- `test_no_global_random_state_pollution`: Externer `np.random.rand()` darf nach Simulation-Init unverändert bleiben.

---

## 9. Fazit

Das Modul ist funktional umfassend und in vielen Bereichen bereits performant vektorisiert. Die wichtigsten Schwachstellen liegen in:

- der **globalen RNG-Verwendung** (Seitenwirkungen, Reproduzierbarkeit fragil),
- der **Speicher-/Cache-Nutzung** (`lru_cache` mit großen Arrays),
- der **redundanten BS-Aufrufe** in `analyze_strategy`,
- der **Verwechslung von Per-Leg- und Strategy-Management-Parametern**,
- sowie der **Lesbarkeit und Wartbarkeit** (Einzeiler, `print`, ungenutzter Code).

Mit den oben genannten Quick-Wins und einer mittelfristigen Restrukturierung in `pricing/`, `simulation/`, `management/`, `analysis/` lässt sich das Modul wartbarer, schneller und korrekter machen, ohne die öffentliche API drastisch zu brechen.
