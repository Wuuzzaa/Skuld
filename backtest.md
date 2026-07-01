# Skuld Backtesting Framework — Design (V1)

**Status:** Design abgeschlossen, wartet auf User-Approval vor Implementierungsplan
**Datum:** 2026-06-30
**Autor:** Daniel + Claude (Brainstorming-Session)
**Speicherort:** Skuld-Memory-Hub (nicht im Skuld-Repo — erst nach Freigabe ggf. dorthin)

---

## 1. Ziel und Anspruch

Das Backtesting-Framework ist ein **strategie-neutrales** Subsystem von Skuld, das jede End-of-Day-basierte Trading-Aktion simulieren kann, die ein menschlicher Trader an einem Brokerterminal (Vorbild: Interactive Brokers) durchführen kann.

**Konkrete Anforderung (aus Brainstorming):**
> Die Engine soll in der Lage sein, jeden Tag in der Vergangenheit die Entscheidung zu treffen, die ein Mensch treffen würde — Einstieg, Stop-Loss nachziehen, Aussteigen, Rollen, Hedgen. Alles was mit EOD-Daten machbar ist, soll machbar sein.
>
> **Performance:** Backtests müssen hochgradig optimiert sein und in Sekunden durchlaufen.

**Explizit nicht im Scope:**
- Intraday-Strategien (Open-Range-Breakout etc.) — nicht mit EOD-Daten machbar.
- Eigenständiges Backend / API-Service / Job-Queue — wir bleiben in der bestehenden Skuld-App.
- Custom visueller Block-Editor für Strategien — Roadmap V2+.

---

## 2. Integration in Skuld

### 2.1 Code-Layout

Das Framework wird als **gegliedertes Python-Package** im bestehenden Skuld-Repo angelegt:

```
src/backtesting/
  __init__.py
  engine/         # Hauptschleife, Portfolio, Position, Actions
  data/           # Snapshot-Loader, UniverseSpec, Filter, Validator
  strategies/     # Strategy-Base-Class, Template-Registry, V1-Templates
  execution/      # Slippage, Commission, Margin, Expiries, Corporate Actions
  results/        # Collector, Metrics, Benchmark, Storage, Export

pages/
  backtest.py     # Streamlit-Frontend (Setup / Performance / Trades / Symbols / Export)
```

### 2.2 Trennung von der existierenden Skuld-Codebasis

- Das Package ist **eigenständig**: es importiert aus `src/database.py` und `src/historization.py` (Daten), aber **nicht** umgekehrt.
- Bestehende Skuld-Module (`black_scholes.py`, `monte_carlo_simulation.py`, Scanner-Logik) sind nicht betroffen.
- Frontend = **eine** neue Streamlit-Page neben den existierenden Scanner-Pages.

### 2.3 Bewusst nicht in V1

- Eigene Job-Queue / Postgres-Jobs-Tabelle / asynchroner Worker-Service (Lead-Dev hat explizit verschoben). Backtests laufen synchron im Streamlit-Request, mit Progress-Bar.
- Auth-Erweiterungen (bestehendes Authelia-Setup reicht).

---

## 3. Daten-Layer

### 3.1 Datenquelle

**Primärquelle:** Die existierende Skuld-Postgres-DB, insbesondere die historisierten Daten via:
- View `OptionDataMergedHistoryTimeTravel`
- Funktion `getOptionDataMergedHistory(p_target_date date)`

Diese liefern für jedes historische Datum eine vollständige rekonstruierte merged Option-/Stock-Sicht inklusive aller Felder:
- Option-Chain (alle Strikes × Expiries, Greeks, IV, OI, Volume, Day-Close)
- Stock-Daten (OHLC, technische Indikatoren, Earnings-Distanz, Dividenden, HV30)
- IV-Rank, IV-Percentile
- Fundamental-Daten (~400 Felder aus Yahoo)
- Asset-Profile (Sektor, Industrie, Country, Market Cap)

### 3.2 Snapshot-Modell

Pro Handelstag stellt der Data-Layer ein `MarketSnapshot`-Objekt bereit:

```python
class MarketSnapshot:
    date: date
    stocks: dict[symbol, StockData]   # OHLC, Indikatoren, Fundamentals, etc.
    chains: dict[symbol, OptionChain] # Calls + Puts × Strikes × Expiries
    universe: list[symbol]            # die heute aktiven Symbole

    def find_option(symbol, type, delta_target=None, dte_range=None,
                    strike_target=None, ...) -> Option | None: ...
```

Die Strategie sieht ausschließlich Daten, die an Tag d real verfügbar gewesen wären (kein Look-Ahead-Bias, weil die TimeTravel-View das schon kapselt).

### 3.3 Loading-Strategie

**Hybrid B+C: Smart Preload mit on-demand Computed Fields.**

- Beim Backtest-Start werden alle benötigten Daten für (Universum × Zeitraum × Strategy-deklarierte Felder) in **wenigen Bulk-Queries** gegen die TimeTravel-View geladen und in Pandas-DataFrames im RAM gehalten.
- Strategien deklarieren ihre Daten-Anforderungen via `preload_fields: list[str]`.
- Strategien können zusätzlich `compute_daily(snapshot, portfolio)` implementieren — für Werte, die tagesabhängig vom Portfolio-Zustand oder Custom-Logik berechnet werden müssen (nicht vorlade-bar).
- Vor Backtest-Start: **RAM-Schätzung mit Warnung**, falls Lauf > X GB benötigt (kein Hard-Stop).

### 3.4 Universum-Spezifikation

Zwei Modi, beide V1:

**Statischer Modus:**
```python
UniverseSpec(mode="static", symbols=["SPY", "QQQ", "AAPL"])
```
User tippt Symbol-Liste in der UI oder wählt aus Skuld-internen Quellen (Symbols-Page nutzt aktuell `OptionDataMerged` direkt). Validierung prüft Datenverfügbarkeit im Zeitraum.

**Dynamischer Modus:**
```python
UniverseSpec(
    mode="dynamic",
    filter=UniverseFilter(
        criteria=["RSL > 1.05", "market_cap > 10e9", "sector in [...]"],
        rank_by="RSL",
        top_n=20,
    ),
    rebalance="daily" | "weekly" | "monthly",
)
```

Filter-Felder: **kuratierte Whitelist (ca. 30-50 Felder), gruppiert nach Kategorien** (Markt / Technik / Fundamentals / Optionen / Dividenden / Earnings). UI zeigt Tabs/Sektionen statt einer 400-Feld-Liste. Bahn-2-Python-Strategien können auf alle Felder zugreifen.

**Symbol-Drop-Verhalten:** **Hard-Exit für Aktien.** Wenn ein gehaltenes Aktien-Symbol bei Rebalance aus dem Universum fliegt, schließt die Engine die Position automatisch über `portfolio.enforce_universe(snapshot)`. Für Optionen gilt dies nicht: Optionspositionen bleiben standardmäßig offen und werden weiter gemanagt, auch wenn das Underlying nicht mehr im aktiven Universum-Filter ist.

**Option DTE Close:** Alle Optionspositionen verfügen über eine konfigurierbare DTE-Exit-Logik. Erreicht eine Position (alle Legs) eine Restlaufzeit von <= X Tagen, wird sie automatisch geschlossen.

### 3.5 Komponenten

```
src/backtesting/data/
  snapshot.py         # MarketSnapshot, StockData, OptionChain, find_option helpers
  loader.py           # SmartPreloader: Bulk-Queries + DataFrame-Cache + RAM-Schätzer
  universe.py         # UniverseSpec, UniverseFilter, Resolver
  fields.py           # Filter-Whitelist mit Gruppierung (UI-konsumiert)
  validator.py        # prüft Universum + Zeitraum gegen DB-Verfügbarkeit
```

---

## 4. Engine

### 4.1 Hauptschleife

```python
def run(strategy: Strategy, universe: Universe, start_date: date, end_date: date, initial_cash: float, config: dict) -> Results:
    portfolio = Portfolio(cash=initial_cash, config=config)
    results = ResultsCollector()
    strategy.on_init(config)

    for date in trading_days(start_date, end_date):
        # 1. Resolve Universe + Get Market Snapshot
        symbols_today = universe.resolve(date)
        snapshot = data_layer.get_snapshot(date, symbols=symbols_today)

        # 2. Portfolio-Update (Automated Maintenance)
        portfolio.mark_to_market(snapshot)
        portfolio.apply_dividends(snapshot)
        portfolio.apply_splits(snapshot)
        portfolio.apply_expiries(snapshot)        # ITM Assignment / OTM Expiry
        portfolio.check_dte_close(snapshot)       # Close options if DTE <= threshold
        portfolio.check_rolling(snapshot, strategy) # Optional: Reusable rolling logic
        portfolio.check_stop_orders(snapshot)     # SL / Trailing / TP
        portfolio.enforce_universe(snapshot)      # Hard-Exit for stocks only

        # 3. Strategy Decision
        if hasattr(strategy, "compute_daily"):
            strategy.compute_daily(snapshot, portfolio)
        actions = strategy.on_day(snapshot, portfolio)

        # 4. Execute Actions
        for action in actions:
            execution.execute(action, portfolio, snapshot)

        # 5. Record Daily State
        results.record_day(date, portfolio)

    return results.finalize()
```

### 4.2 Portfolio-Modell

```python
class Portfolio:
    cash: float
    positions: list[Position]
    margin_used: float
    buying_power: float          # cash - margin_used (Reg-T)
    config: dict                 # includes dte_threshold for options

class Position:
    id: UUID
    legs: list[Union[StockLeg, OptionLeg]]    # 1+ Legs per position
    opened_at: date
    entry_cashflow: float
    stop_orders: list[StopOrder]              # SL / Trailing / TP
    tags: dict[str, str]                      # e.g., {"strategy": "covered_call"}
```

**Wichtig:** Multi-Leg-Strukturen (Covered Call = Stock + short Call; Iron Condor = 4 Option-Legs) sind **eine** Position mit mehreren Legs — analog zur IB-Modellierung. Erlaubt natürliche P&L-Aggregation und Position-Tagging.

**Mehrere parallele Positionen im selben Underlying sind erlaubt** (z.B. Wheel mit drei verschiedenen CCs auf SPY).

### 4.3 Aktions-Primitive (`Action`-Klasse)

Die Strategie gibt pro `on_day` eine Liste von Actions zurück:

```python
OpenPosition(legs=[...], tags={...})
ClosePosition(position_id)
ClosePartial(position_id, fraction=0.5)
AdjustPosition(position_id, close_legs=[...], open_legs=[...])  # Roll/Hedge
SetStopLoss(position_id, level=...)
SetTrailingStop(position_id, trail_pct=...)
SetTakeProfit(position_id, level=...)
```

Stop-Orders sind **Portfolio-Sache, nicht Strategie-Sache**: einmal gesetzt, prüft die Engine täglich. Die Strategie muss keine eigene Stop-Logik schreiben.

### 4.4 Automatik der Engine

Folgende Mechaniken laufen **ohne Strategie-Zutun**:
- **Daily Mark-to-Market:** Portfolio-Bewertung zum Tagesschluss.
- **Dividend Processing:** Cash-Gutschrift am Ex-Date für gehaltene Aktien.
- **Corporate Actions:** Adjustment von Stückzahlen und Strikes bei Splits.
- **Option Expiries:** ITM Assignment (Stock Transfer) oder OTM Verfall (wertlos).
- **DTE-Close:** Automatisches Schließen von Optionspositionen, wenn die Restlaufzeit (DTE) den Schwellenwert erreicht.
- **Stop-Orders:** Überprüfung von Stop-Loss, Trailing-Stop und Take-Profit.
- **Margin Management:** Kontinuierlicher Check; automatische Liquidation bei Margin-Call.
- **Universe Enforcement:** Hard-Exit bei Symbol-Drop (**nur für Aktien**).

### 4.5 Komponenten

```
src/backtesting/engine/
  engine.py           # run() Hauptschleife
  portfolio.py        # Portfolio + Position + Leg
  actions.py          # Action-Klassen
  stop_orders.py      # SL/Trailing/TP Logik
  calendar.py         # trading_days() (NYSE-Kalender)
```

---

## 5. Strategien — Zwei Bahnen

### 5.1 Bahn 2: Python-Strategien (definiert die API)

```python
class Strategy:
    name: str
    description: str
    params: StrategyParams                # declarative parameter definition
    universe_default: UniverseSpec
    preload_fields: list[str]

    def on_init(self, config: dict) -> None: ...
    def compute_daily(self, snapshot: MarketSnapshot, portfolio: Portfolio) -> None: ...
    def on_day(self, snapshot: MarketSnapshot, portfolio: Portfolio) -> list[Action]: ...  # MANDATORY
    def on_position_opened(self, position: Position, snapshot: MarketSnapshot) -> None: ...
    def on_position_closed(self, position: Position, snapshot: MarketSnapshot) -> None: ...
    def on_symbol_dropped(self, symbol: str, snapshot: MarketSnapshot) -> None: ...
```

**Parameter-API (`StrategyParams`):** deklarativ mit Typ, Default, Range, Step. Beispiel:

```python
params = StrategyParams(
    delta_target = NumericParam(0.30, range=(0.10, 0.50), step=0.05),
    dte_range    = TupleParam((30, 45), constraints="dte"),
    exit_profit_pct = NumericParam(0.50, range=(0.20, 0.95), step=0.05),
)
```

→ Frontend generiert das Form aus dieser Deklaration automatisch.

### 5.2 Bahn 1: UI-Template-Konfigurator

Der User wählt eines der **5 V1-Templates** aus und parametrisiert es:

| Template | Inhalt |
|---|---|
| Covered Call | Aktie + short Call, Roll/Exit-Regeln |
| Cash-Secured Put | Cash-Reserve + short Put, Roll/Exit-Regeln |
| Wheel | CSP → Assignment → CC → Called Away → CSP-Zyklus |
| Vertical Spread | Bull-Put / Bear-Call / Bull-Call / Bear-Put (eine Klasse, vier Varianten) |
| Iron Condor | short Call-Spread + short Put-Spread |

Jedes Template ist intern eine Bahn-2-Strategie-Klasse. Bahn 1 ist „Bahn 2 mit auto-generiertem Form".

**Bewusst nicht V1:** völlig freier visueller Block-Editor („wenn-X-dann-Y zusammenklicken"). Diese Brücke ist V2-Roadmap. V1-Erweiterung: Dev schreibt neue Strategy-Klasse → Frontend zeigt sie automatisch.

### 5.3 Komponenten

```
src/backtesting/strategies/
  base.py             # Strategy-Base-Class + StrategyParams + Param-Typen
  registry.py         # Discovery: alle Strategy-Subclasses einsammeln
  covered_call.py     # V1-Templates
  cash_secured_put.py
  wheel.py
  vertical_spread.py
  iron_condor.py
```

---

## 6. Rolling-Strategien (Wiederverwendbare Teilstrategien)

Rolling-Logik wird als modulare Komponente entkoppelt, damit sie in verschiedenen Hauptstrategien (Wheel, Spreads, etc.) konsistent und effizient eingesetzt werden kann.

### 6.1 Konzept
Rollstrategien sind zustandsbehaftete Sub-Strategien, die einer Position zugeordnet werden können. Die Engine triggert diese in der Hauptschleife (`portfolio.check_rolling`), wodurch komplexe Management-Logik nicht in jeder `on_day`-Methode neu implementiert werden muss.

### 6.2 Eric Ludwig Default-Vorlage
Diese Vorlage implementiert das 4-Phasen-Modell zur defensiven Verteidigung von (Short) Optionen.

**Verfügbare Trigger-Variablen:**
- `pos.delta_current`: Aktuelles Delta des/der Legs.
- `pos.distance_to_strike_pct`: Abstand des Kurses zum Basispreis in %.
- `pos.unrealized_pnl_pct`: Aktueller Gewinn/Verlust bezogen auf die Einstiegsprämie.
- `pos.dte`: Verbleibende Tage bis zum Verfall.
- `pos.roll_count`: Anzahl der bereits durchgeführten Rollvorgänge in der aktuellen Phase.
- `snap.iv_rank`: Aktueller IV-Rank des Underlyings.

**PHASE 1 – VERTIKAL (Basispreis-Optimierung):**
- **Trigger:** [PLATZHALTER: z. B. Put im Geld bei X % / Delta > 0.60]
- **Aktion:** Basispreis nach unten anpassen (gleiche oder ähnliche Laufzeit)
- **Ziel:** Break-even verbessern, Netto-Prämie ≥ 0 (Roll for Credit/Even)
- **Max. Anzahl:** [PLATZHALTER: z. B. 2 mal]

**PHASE 2 – HORIZONTAL (Zeit-Gewinn):**
- **Trigger:** [PLATZHALTER: wenn Phase 1 ausgeschöpft / DTE < 14 erreicht]
- **Aktion:** Laufzeit verlängern (gleicher oder angepasster Basispreis)
- **Ziel:** zusätzliche Zeitprämie vereinnahmen, mehr Puffer (Zeitwert-Vorteil)
- **Ziel-DTE:** [PLATZHALTER: z. B. 45 DTE]

**PHASE 3 – VERTIKAL (erneut):**
- **Trigger:** [PLATZHALTER: wenn Kurs weiter fällt trotz Phase 1+2]
- **Aktion:** Erneute Basispreis-Anpassung nach unten
- **Bedingung:** nur wenn Netto-Kredit weiterhin möglich ist

**PHASE 4 – POSITIONSGRÖSSE (Kapitalkraft):**
- **Trigger:** [PLATZHALTER: wenn Phasen 1-3 ausgeschöpft sind]
- **Aktion:** Kontraktanzahl anpassen (z. B. auf 2 Kontrakte mit halbem Basispreis-Abstand rollen, um Break-even massiv zu verbessern)
- **Risikogrenze:** Max. Kapitaleinsatz / Buying Power Limit: [PLATZHALTER]

### 6.3 Interface & Implementation

```python
from typing import Optional, List, Union
from datetime import date
from uuid import UUID

class RollingManager:
    """
    Manages reusable rolling logic for positions.
    """
    def check_rolling(self, portfolio: 'Portfolio', snapshot: 'MarketSnapshot'):
        for position in portfolio.positions:
            if "roll_strategy" in position.tags:
                action = self._get_roll_action(position, snapshot)
                if action:
                    portfolio.apply_action(action)

    def _get_roll_action(self, position: 'Position', snapshot: 'MarketSnapshot') -> Optional['Action']:
        # Logic to dispatch to specific RollStrategy implementation
        pass

class RollStrategy:
    """
    Base class for rolling sub-strategies.
    """
    def evaluate(self, position: 'Position', snapshot: 'MarketSnapshot') -> Optional['Action']:
        raise NotImplementedError

class EricLudwigStrategy(RollStrategy):
    """
    Implementation of the 4-phase defensive rolling model.
    """
    def __init__(self, params: dict):
        self.params = params # Includes triggers for Phase 1-4

    def evaluate(self, position: 'Position', snapshot: 'MarketSnapshot') -> Optional['Action']:
        # 1. Check Phase 1 (Vertical)
        if self._trigger_phase_1(position, snapshot):
            return self._action_phase_1(position, snapshot)
        
        # 2. Check Phase 2 (Horizontal)
        if self._trigger_phase_2(position, snapshot):
            return self._action_phase_2(position, snapshot)
            
        # ... Phase 3 & 4
        return None

    def _trigger_phase_1(self, pos: 'Position', snap: 'MarketSnapshot') -> bool:
        # Check ITM % or Delta threshold
        return False 
```

---

## 7. Execution-Layer

### 7.1 Pricing & Timing

- **Timing:** Um **Look-Ahead Bias** zu vermeiden, sieht die Strategie am Tag $t$ zwar den Schlusskurs, Orders werden jedoch standardmäßig als **Market-on-Close (MOC)** simuliert. 
- **Logik:** Die Strategie-Entscheidung basiert auf EOD-Daten von Tag $t$. Die Ausführung erfolgt zum Schlusskurs von Tag $t$. Dies ist legitim, da die meisten Broker MOC-Orders bis kurz vor Schluss annehmen. Alternativ kann in der Config auf "Next Day Open" umgestellt werden.
- **Preisfindung:** Alle Orders werden zum Tagesschluss (`day_close`) gefüllt.

### 7.2 Slippage

**Dynamische OI-basierte Slippage als Default** (in Config umschaltbar auf fix-pct):

| Liquiditätsklasse | Slippage |
|---|---|
| Aktien | 0.05% |
| Optionen OI > 1000 | 0.5% |
| Optionen OI 100–1000 | 1.0% |
| Optionen OI < 100 | 3.0% oder Order rejected (Config) |

### 7.3 Commission (IB-Vorbild, konfigurierbar)

```python
CommissionConfig(
    option_per_contract = 0.65,
    option_min_order    = 1.00,
    stock_per_share     = 0.005,
    stock_min_order     = 1.00,
    stock_max_pct       = 0.01,
    regulatory_per_option = 0.05,
)
```

### 7.4 Margin & Finanzierungskosten

**Margin (Reg-T):**
Konkrete Berechnungsregeln je Position-Typ:

| Position-Typ | Initial Margin |
|---|---|
| Covered Call (Stock + Short Call) | 0 (besichert) |
| Cash-Secured Put | Strike × 100 × Qty (Cash-Reserve) |
| Naked Short Put | 20% × Underlying − OTM-Amount + Prämie (Standard-Reg-T) |
| Naked Short Call | 20% × Underlying − OTM-Amount + Prämie |
| Vertical Spread | Spread-Width × 100 × Qty |
| Iron Condor | max(Call-Spread-Width, Put-Spread-Width) × 100 × Qty |
| Long Stock auf Margin | 50% Initial / 25% Maintenance |

**Finanzierungskosten (V1):**
- **Margin-Zinsen:** Bei negativer Cash-Bilanz (Long-Stock auf Margin) wird ein täglicher Zins belastet (Config: `margin_interest_rate`, z.B. 7% p.a.).
- **Short Borrow Fees:** Beim Leerkauf von Aktien (Short Stock) wird eine tägliche Leihgebühr fällig (Config: `borrow_fee_default`, z.B. 1% p.a. oder symbol-spezifisch falls verfügbar).

**Margin-Call:**
Maintenance-Verletzung → Engine schließt Position(en) automatisch (vereinfacht gegenüber realem Broker, der Anrufzeit gewähren würde).

**V2-Roadmap:** Portfolio Margin (risikobasiert).

### 7.5 Order-Mechanik

- **Multi-Leg-Orders sind atomar.** Wenn ein Leg nicht füllbar/margin-pflicht-verletzend ist → ganze Order rejected, im Trade-Log mit Grund vermerkt.
- **Rejected Orders** sind kein Fehler — Strategie sieht im nächsten `on_day`, dass die Position nicht da ist, und kann reagieren.

### 7.6 Auto-Mechaniken bei Corporate Actions / Expiries

- **Dividenden:** Cash-Buchung am Ex-Date, wenn Aktie zum Ex-Date gehalten wurde.
- **Splits:** Position-Qty + Option-Strikes werden adjustiert.
- **Expiries:** ITM Call short → Aktien gehen weg + Cash kommt rein (Strike × 100); ITM Put short → Aktien kommen rein + Cash geht raus; OTM → Verfall (Position aufgelöst, Restwert = 0).
- **Early Assignment:** V1 nicht modelliert (Roadmap).

### 7.7 Komponenten

```
src/backtesting/execution/
  executor.py         # orchestriert Pricing + Slippage + Commission + Margin
  slippage.py         # SlippageModel (OI-basiert + fix-pct fallback)
  commission.py       # IB-Tiered, konfigurierbar
  margin.py           # Reg-T Calculator
  expiries.py         # Assignment / Verfall
  corporate_actions.py # Dividenden + Splits
```

---

## 8. Results

### 8.1 Rohdaten-Sammlung während des Laufs

| Log | Inhalt | Granularität |
|---|---|---|
| Trade-Log | Jede Order-Ausführung mit Pricing, Slippage, Commission, Cash-Status | pro Action |
| Position-Log | Geschlossene Positionen mit Open/Close, Holding-Days, P&L, max Drawdown, Close-Reason | pro Position |
| Daily-Portfolio-Log | Cash, Equity, Margin, offene Positionen, Unrealized P&L | pro Handelstag |

### 8.2 Abgeleitete Metriken (V1)

**Standard-Performance:** Total Return, CAGR, Max Drawdown ($, %, Dauer), Sharpe, Sortino, Calmar, Annualized Volatility.

**Trade-Statistik:** Anzahl Trades, Win-Rate, Avg Win, Avg Loss, Largest Win, Largest Loss, Profit Factor, Avg Holding Period, Expectancy.

**Symbol-Breakdown:** Pro Symbol — Anzahl Trades, Win-Rate, Total P&L, Avg P&L, Contribution-% zum Gesamt-P&L.

**Benchmark-Vergleich:** gegen konfigurierbares Benchmark-Symbol (Default SPY Buy & Hold), inkl. Alpha, Beta, Tracking Error.

### 8.3 Persistenz

**V1: File-basiert.** Jeder Lauf bekommt eine GUID. Ergebnisse werden als Parquet (Logs) + JSON (Config + Metriken) auf Disk abgelegt unter `data/backtest_runs/{uuid}/`. Frontend zeigt einen „Lade gespeicherten Lauf"-Selector.

**V2-Roadmap:** Postgres-Tabellen `BacktestRun`, `BacktestTrade`, `BacktestDaily` für queryable Persistenz.

### 8.4 Benchmark-Vergleich

- **Logik:** Die Benchmark (Standard: SPY) wird als **Total Return** simuliert (inkl. Dividenden-Reinvestition), um eine faire Vergleichbarkeit zu Optionsstrategien zu gewährleisten.
- **Berechnung:** Ein fiktives Portfolio startet mit demselben Kapital und kauft am Start-Datum die Benchmark zum Open-Kurs.

### 8.5 Komponenten

```
src/backtesting/results/
  collector.py        # ResultsCollector (sammelt während Lauf)
  metrics.py          # MetricsCalculator
  benchmark.py        # Buy & Hold Benchmark
  storage.py          # File-basierte Parquet/JSON-Persistenz
  export.py           # CSV/JSON Export für UI-Download
```

---

## 9. Frontend (`pages/backtest.py`)

Streamlit-Page mit 5 Tabs/Sektionen:

**Tab „Setup":**
- Strategie-Auswahl (Dropdown aus `registry.list_strategies()`)
- Auto-generierte Parameter-Form aus `StrategyParams`
- Universum-Setup (statisch: Symbol-Input mit Skuld-Symbols-Quelle; dynamisch: gruppierte Filter-UI)
- Zeitraum (Date-Range-Picker)
- Engine-Config: Initial Cash, Slippage-Modus, Commission-Override, Margin-Modus, Benchmark
- „Run Backtest" Button

**Während des Laufs:** Progress-Bar mit „Tag X von N", Live-Equity-Anzeige.

**Tab „Performance":**
- Equity-Curve (vs. Benchmark)
- Drawdown-Kurve
- Kennzahlen als Cards (Total Return, CAGR, Sharpe, Max DD, Win-Rate, Profit Factor)

**Tab „Trades":**
- Trade-Log als sortier-/filterbare Tabelle
- Klick auf Trade → Detail-Drilldown: Legs, Greeks bei Open/Close, P&L-Verlauf der Position

**Tab „Symbols":**
- Symbol-Breakdown-Tabelle (P&L, Win-Rate, Trades, Contribution-%)
- Pro Symbol: Sub-Equity-Mini-Chart

**Tab „Export":**
- Trade-Log, Daily-Log, Metriken als CSV/JSON Download
- Backtest-Config als JSON (Reproduzierbarkeit)

---

## 10. Ehrliche Limitierungen (für User-Doku)

| Thema | Status V1 | Anmerkung |
|---|---|---|
| Granularität | Nur EOD | Keine Intraday-Strategien |
| Bid/Ask-Realismus | `day_close` als Mid-Proxy + Slippage-Heuristik | Bei illiquiden Symbolen optimistisch |
| Survivor-Bias | Nicht behandelt | Statisches Universum = heutige Symbole; historische S&P-Mitgliedschaft = V2 |
| Early Assignment | Nicht modelliert | Nur Expiry-Assignment |
| Portfolio Margin | Nicht in V1 | Reg-T only |
| Multi-Strategy-Portfolio | Nicht in V1 | Eine Strategie pro Backtest; „Systeme" = Roadmap |
| Daten-Historie-Tiefe | Abhängig von Skuld-DB-Stand | Vermutlich ~1-2 Jahre Optionsdaten; bei Implementation messen |
| Postgres-Persistenz | File-basiert in V1 | DB-Tabellen = V2 |
| Async/Worker | Nein, synchron in Streamlit | Job-Queue = V2 wenn Performance-Schmerz |

---

## 11. Roadmap V2+

In Reihenfolge wahrscheinlicher Nachfrage:

1. Grid-Search / Parameter-Sweep über StrategyParams
2. Walk-Forward-Validierung (rollende Train/Test-Windows)
3. Portfolio Margin
4. Early Assignment (mit Ex-Dividenden-Trigger)
5. Multi-Strategy-Portfolios („Systeme")
6. Postgres-Persistenz + Run-Vergleichs-UI
7. Custom visueller Strategy-Builder (Block-Editor)
8. Historische S&P500-Mitgliedschaft (Survivor-Bias-freie dynamische Universen)
9. User-uploadbare Python-Strategien (mit Sandboxing)
10. Async Job-Queue für lange Läufe

---

## 12. Komponenten-Karte (Kurzfassung)

```
src/backtesting/
├── engine/          # Hauptschleife, Portfolio, Actions, Stop-Orders, Calendar
├── data/            # Snapshot, Smart-Preloader, Universe, Filter-Whitelist, Validator
├── strategies/      # Base-Class, Registry, 5 V1-Templates
├── execution/       # Slippage, Commission, Margin (Reg-T), Expiries, Corporate Actions
└── results/         # Collector, Metrics, Benchmark, File-Storage, Export

pages/backtest.py    # Streamlit-Frontend mit 5 Tabs
```

Externe Dependencies (alles bereits in Skuld):
- `pandas` (Daten-Layer)
- `sqlalchemy` + `psycopg2` (DB-Zugriff via existierende `src/database.py`)
- `streamlit` (Frontend)
- `pyarrow` (Parquet-Persistenz — vermutlich neu hinzuzufügen)

---

## 13. Offene Punkte für Implementation

1. **SQL Query Location & Encapsulation:** Alle SQL-Queries müssen in `Skuld/db/SQL/query/backtest` abgelegt werden. Eine saubere Kapselung ist zwingend erforderlich.
2. **Performance-Optimierung:** Um "Sekunden-Laufzeiten" zu erreichen, muss der `MarketSnapshot` im RAM als Hash-Map (Dict) organisiert sein, um O(1) Zugriff pro Symbol/Tag zu ermöglichen.
3. **Tatsächliche Daten-Historie messen:** `SELECT MIN(snapshot_date), MAX(snapshot_date) FROM "OptionDataMassiveHistoryDaily"` — Bestimmt den verfügbaren Backtest-Zeitraum.
4. **Performance der `getOptionDataMergedHistory(date)`-Funktion:** Diese muss für Bulk-Abfragen optimiert sein (Preloading).
5. **Whitelist der Filter-Felder konkret festlegen:** Mapping „UI-Label → DB-Spalte → Kategorie“ (z.B. RSL, IV-Rank, Market Cap).
6. **Trading-Calendar-Quelle:** Empfehlung: `exchange_calendars` (Python-Lib) zur korrekten Handhabung von US-Handelstagen.
7. **Aktuelle Skuld-Symbol-Quelle:** Identifikation der Tabelle für das statische Universum (vermutlich `OptionDataMerged`).
8. **Präzision der Finanzierungskosten:** Festlegung der Standard-Zinssätze für Margin und Borrow Fees in der `config.py`.
