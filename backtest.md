# Skuld Backtesting Framework — Design & Reference

**Status:** V1 implementiert auf Branch `backtest`. Dieses Dokument spiegelt
den Code-Stand, nicht mehr die reine Design-Absicht — Änderungen am Code
werden hier nachgezogen.
**Repo-Standort:** `Skuld-master/backtest.md` (auf Branch `backtest`).
**Ursprüngliches Design:** 2026-06-30 (Daniel + Claude).

---

## 1. Ziel und Anspruch

Das Backtesting-Framework ist ein **strategie-neutrales** Subsystem von
Skuld, das jede End-of-Day-basierte Trading-Aktion simulieren kann, die ein
menschlicher Trader an einem Brokerterminal (Vorbild: Interactive Brokers)
durchführen kann.

**Konkrete Anforderung (aus Brainstorming):**
> Die Engine soll in der Lage sein, jeden Tag in der Vergangenheit die
> Entscheidung zu treffen, die ein Mensch treffen würde — Einstieg,
> Stop-Loss nachziehen, Aussteigen, Rollen, Hedgen. Alles was mit
> EOD-Daten machbar ist, soll machbar sein.
>
> **Performance:** Backtests müssen hochgradig optimiert sein und in
> Sekunden durchlaufen.

**Explizit nicht im Scope:**
- Intraday-Strategien (Open-Range-Breakout etc.) — nicht mit EOD-Daten machbar.
- Eigenständiges Backend / API-Service / Job-Queue — wir bleiben in der
  bestehenden Skuld-App.
- Custom visueller Block-Editor für Strategien — Roadmap V2+.

---

## 2. Integration in Skuld

### 2.1 Code-Layout (Ist)

```
src/backtesting/
├── __init__.py
├── engine/
│   ├── engine.py          # run() + RunConfig + trade-mirror-to-detail helper
│   ├── portfolio.py       # Portfolio, Position, StockLeg, OptionLeg
│   ├── actions.py         # OpenPosition, ClosePosition, ClosePartial,
│   │                      # AdjustPosition, SetStopLoss/TrailingStop/TakeProfit
│   ├── stop_orders.py     # StopLossOrder, TrailingStopOrder, TakeProfitOrder
│   └── calendar.py        # trading_days()
├── data/
│   ├── snapshot.py        # MarketSnapshot, StockData, OptionChain, Option
│   ├── loader.py          # SmartPreloader (SQL-Template-getrieben, RAM-Schätzer)
│   ├── universe.py        # UniverseSpec, UniverseFilter, Universe resolver
│   ├── fields.py          # FieldDef whitelist + FIELD_CATEGORIES
│   └── validator.py       # DB-Verfügbarkeit vs. Universe × Range
├── strategies/
│   ├── base.py            # Strategy + StrategyParams + log_detail()
│   ├── params.py          # NumericParam, TupleParam, ChoiceParam, BoolParam
│   ├── registry.py        # Auto-Register über __init_subclass__
│   ├── rolling.py         # RollingManager + EricLudwigStrategy
│   ├── buy_and_hold.py    # V1-Templates
│   ├── cash_secured_put.py
│   ├── covered_call.py
│   ├── wheel.py
│   ├── vertical_spread.py
│   └── iron_condor.py
├── execution/
│   ├── executor.py        # orchestriert Pricing + Slippage + Commission + Margin
│   ├── slippage.py        # SlippageModel (OI-basiert / fix-pct)
│   ├── commission.py      # CommissionCalculator + CommissionConfig
│   └── margin.py          # RegTMarginCalculator
└── results/
    ├── collector.py       # ResultsCollector, Results-Dataclass
    ├── metrics.py         # PerformanceMetrics + MetricsCalculator
    ├── benchmark.py       # BenchmarkTracker (Buy & Hold)
    ├── storage.py         # save/load unter data/backtest_runs/{run_id}/
    └── export.py          # CSV/JSON downloads für die UI

pages/backtest.py          # Streamlit-Frontend (6 Tabs — s.u.)

db/SQL/query/backtest/
├── available_symbols.sql
├── data_coverage.sql
└── merged_snapshot.sql
```

### 2.2 Trennung von der existierenden Skuld-Codebasis

- Das Package ist **eigenständig**: es importiert `src/database.py`
  (SQL-Ausführung) + `src/historization.py` (Zugriff auf die
  TimeTravel-View), aber nicht umgekehrt.
- Bestehende Skuld-Module (`black_scholes.py`, `monte_carlo_simulation.py`,
  Scanner-Logik) sind unberührt.
- Frontend = **eine** neue Streamlit-Page neben den existierenden
  Scanner-Pages.

### 2.3 Bewusst nicht in V1

- Eigene Job-Queue / Postgres-Jobs-Tabelle / asynchroner Worker.
  Backtests laufen synchron im Streamlit-Request, mit Progress-Bar.
- Auth-Erweiterungen (bestehendes Authelia-Setup reicht).

---

## 3. Daten-Layer

### 3.1 Datenquelle

**Primärquelle:** Die existierende Skuld-Postgres-DB, insbesondere die
historisierten Daten via:
- View `OptionDataMergedHistoryTimeTravel`
- Funktion `getOptionDataMergedHistory(p_target_date date)`

Diese liefern für jedes historische Datum eine vollständige rekonstruierte
merged Option-/Stock-Sicht inklusive aller Felder:
- Option-Chain (alle Strikes × Expiries, Greeks, IV, OI, Volume, `day_close`)
- Stock-Daten (`live_stock_price`, OHLC, technische Indikatoren, Earnings-
  Distanz, Dividenden, HV30)
- IV-Rank, IV-Percentile
- Fundamental-Daten (~400 Felder aus Yahoo)
- Asset-Profile (Sektor, Industrie, Country, Market Cap)

### 3.2 Snapshot-Modell (Ist)

Pro Handelstag stellt der Data-Layer eine `MarketSnapshot`-Instanz bereit:

```python
@dataclass
class MarketSnapshot:
    date: date
    stocks: dict[str, StockData]
    chains: dict[str, OptionChain]
    universe: list[str]
    is_last_day: bool = False  # von der engine für den letzten Tag gesetzt
```

`StockData` hält OHLC, `live_stock_price`, IV-Rank/Percentile, HV30,
Earnings-Distanz, Dividenden und einen freien `extras`-Bag für zusätzliche
Fundamentals. `OptionChain.find(...)` wählt einen Kontrakt anhand
`delta_target` (oder `strike_target`), gefiltert nach `dte_range` und
`min_open_interest`.

Die Strategie sieht ausschließlich Daten, die an Tag *d* real verfügbar
gewesen wären (kein Look-Ahead-Bias — die TimeTravel-View kapselt das).

### 3.3 Loading-Strategie (Ist)

**Hybrid B+C: Smart Preload mit on-demand Computed Fields.**

- Der `SmartPreloader` nimmt bei Instanziierung `symbols` +
  `preload_fields` von der Strategie entgegen und erstellt daraus für
  jede benötigte Datum die SQL — `essential = {"symbol",
  "live_stock_price"}` plus die `preload_fields` der Strategie werden zu
  einer Spaltenliste kombiniert und in `db/SQL/query/backtest/merged_snapshot.sql`
  eingesetzt (`{columns}` und `{where_clause}` Platzhalter).
- Beim ersten Zugriff pro Datum wird die Funktion
  `getOptionDataMergedHistory(:target_date)` mit dieser Spaltenliste und
  optional `WHERE symbol IN (:symbols)` aufgerufen; das Ergebnis landet
  als `pd.DataFrame` im `_frame_cache`. Die `MarketSnapshot`-Instanz
  wird pro Aufruf aus dem gecachten Frame neu konstruiert — für V1
  ausreichend, weil jedes Datum genau einmal pro Backtest besucht wird
  und ein zusätzlicher Snapshot-Cache kein realer Gewinn wäre.
- Strategien deklarieren ihre Daten-Anforderungen via
  `preload_fields: list[str]` als Klassen-Attribut.
- Strategien können zusätzlich `compute_daily(snapshot, portfolio)`
  implementieren — für Werte, die tagesabhängig vom Portfolio-Zustand oder
  Custom-Logik berechnet werden müssen (nicht vorlade-bar).
- `estimate_ram_gb(num_symbols, num_days, avg_contracts)` liefert eine
  grobe Schätzung; **noch nicht** als UI-Warnung verdrahtet
  (Roadmap-Punkt).

### 3.4 Universum-Spezifikation

Zwei Modi, beide V1:

**Statischer Modus:**
```python
UniverseSpec(mode="static", symbols=["SPY", "QQQ", "AAPL"])
```
User tippt Symbol-Liste in der UI (`static_symbols` Text-Area).
Validierung via `validate_universe_and_range` prüft
`OptionDataMassiveHistoryDaily` auf `MIN/MAX(snapshot_date)` sowie
per-Symbol-Coverage.

**Dynamischer Modus:**
```python
UniverseSpec(
    mode="dynamic",
    filter=UniverseFilter(criteria=[...], rank_by=..., top_n=20),
    rebalance="daily" | "weekly" | "monthly",
)
```

Filter-Felder werden aus `FIELD_CATEGORIES` in `data/fields.py` gezogen —
eine kuratierte Whitelist gruppiert nach Kategorien (Markt / Technik /
Fundamentals / Optionen / Dividenden / Earnings). Die UI generiert daraus
Expander-Sektionen; Bahn-2-Python-Strategien können auch außerhalb dieser
Whitelist direkt auf `snapshot.stocks[symbol].extras` zugreifen.

**Symbol-Drop-Verhalten:** `portfolio.enforce_universe(snapshot,
active_universe)` schließt STOCK-only-Positionen, deren Symbol nicht mehr
im aktiven Universum steckt. Positionen mit Options-Legs bleiben offen und
werden weiter vom `on_day` / Rolling / DTE-Close gemanagt.

**Option DTE Close:** Alle Optionspositionen unterliegen der
konfigurierbaren `RunConfig.dte_close_threshold` (Default: 7 Tage).
`portfolio.check_dte_close(snapshot)` schließt automatisch, sobald
`position.dte <= threshold`.

---

## 4. Engine

### 4.1 Hauptschleife (Ist — `engine.run`)

```python
def run(strategy, universe_spec, start_date, end_date, config, preloader=None,
        progress_callback=None):
    portfolio = Portfolio(cash=cfg.initial_cash, config={...})
    universe  = Universe(universe_spec)
    preloader = preloader or SmartPreloader(symbols=..., fields=strategy.preload_fields)
    executor  = Executor(cfg)
    collector = ResultsCollector(..., benchmark_symbol=cfg.benchmark_symbol)

    strategy._logger = collector          # Strategien nutzen self.log_detail(...)
    strategy.on_init(cfg)

    for i, d in enumerate(trading_days(start_date, end_date)):
        symbols_today = universe.resolve(d)
        snapshot      = preloader.get_snapshot(d, symbols=symbols_today + benchmark)
        snapshot.is_last_day = (i == len(days) - 1)

        # 2. Automated maintenance
        portfolio.mark_to_market(snapshot)
        portfolio.apply_dividends(snapshot)
        portfolio.apply_splits(snapshot)       # V1: no-op
        portfolio.apply_expiries(snapshot)     # ITM assignment / OTM expiry
        portfolio.check_dte_close(snapshot)
        portfolio.check_rolling(snapshot, strategy)
        portfolio.check_stop_orders(snapshot)
        portfolio.enforce_universe(snapshot, symbols_today)  # nur Stocks

        # 3. Strategy decision
        if hasattr(strategy, "compute_daily"):
            strategy.compute_daily(snapshot, portfolio)
        actions = strategy.on_day(snapshot, portfolio)

        # 4. Execute actions — trade-log + mirrored detail-log
        for action in actions:
            trade_log = executor.execute(action, portfolio, snapshot)
            for entry in trade_log:
                collector.record_trade(d, entry)
                _record_trade_as_detail(collector, d, entry, portfolio)

        # 5. EOD snapshot
        collector.record_day(d, portfolio, snapshot)
        if progress_callback:
            progress_callback(i + 1, len(days), d, portfolio)

    return collector.finalize()
```

**Detail-Log-Mirror:** Nach jeder erfolgreichen Trade-Ausführung ruft
`engine._record_trade_as_detail(collector, d, entry, portfolio)` auf und
schreibt eine Detail-Zeile mit `quantity_change` (Delta durch diese
Aktion) und `quantity_position` (Bestand nach Aktion) — siehe
Abschnitt 9.4.

### 4.2 Portfolio-Modell

```python
@dataclass
class Portfolio:
    cash: float = 0.0
    positions: list[Position] = ...          # offene + gerade geschlossene
    closed_positions: list[Position] = ...   # historische Closed
    margin_used: float = 0.0
    config: dict = ...                       # dte_close_threshold etc.

@dataclass
class Position:
    id: UUID
    legs: list[StockLeg | OptionLeg]
    opened_at: date
    closed_at: Optional[date]
    entry_cashflow: float
    realized_pnl: float
    stop_orders: list[StopOrder]
    tags: dict[str, str]  # z.B. {"template": "covered_call", "stage": "csp"}
```

**Wichtig:** Multi-Leg-Strukturen (Covered Call = Stock + short Call;
Iron Condor = 4 Option-Legs) sind **eine** Position mit mehreren Legs —
analog zur IB-Modellierung. Erlaubt natürliche P&L-Aggregation und
Position-Tagging.

**Mehrere parallele Positionen im selben Underlying sind erlaubt** (z.B.
Wheel mit drei verschiedenen CCs auf SPY).

**Berechnete Attribute** (auf `Position`):
- `market_value`, `unrealized_pnl`, `unrealized_pnl_pct`
- `dte` (min über alle Option-Legs)
- `delta_current` (aggregiert; Stock-Legs zählen als 1.0/Share)
- `distance_to_strike_pct(snapshot)` — signierte % Distanz zum nächsten
  Short-Strike
- `roll_count` (aus `tags["roll_count"]`)

### 4.3 Aktions-Primitive (`engine/actions.py`)

Die Strategie gibt pro `on_day` eine Liste von Actions zurück:

```python
OpenPosition(legs=[LegSpec(...)], reason="strategy", tags={...},
             stop_loss=None, take_profit=None, trailing_stop_pct=None)
ClosePosition(position_id, reason="strategy")
ClosePartial(position_id, fraction, reason="strategy")
AdjustPosition(position_id, close_leg_ids=[...], open_legs=[...], reason="roll")
SetStopLoss(position_id, level)
SetTrailingStop(position_id, trail_pct)
SetTakeProfit(position_id, level)
```

`LegSpec` unterstützt entweder `option_osi` (exakter Kontrakt) oder die
deskriptive Kombination (`contract_type`, `delta_target`, `dte_range`,
`strike_target`); der Executor löst dann via `chain.find(...)` auf.

Stop-Orders sind **Portfolio-Sache, nicht Strategie-Sache**: einmal
gesetzt, prüft die Engine täglich (`check_stop_orders`). Die Strategie
muss keine eigene Stop-Logik schreiben.

### 4.4 Automatik der Engine

Folgende Mechaniken laufen **ohne Strategie-Zutun**:

- **Daily Mark-to-Market:** aus `snapshot.get_stock().live_stock_price`
  (Aktien) und Kontrakt-Match per `option_osi` (Optionen; aktualisiert auch
  Greeks + IV).
- **Dividend Processing:** V1-Simplification — wenn `stock.last_dividend_date`
  == snapshot.date, wird `last_dividend * quantity` als Cash gebucht.
- **Splits:** `apply_splits` ist **V1-no-op** — Skuld's DB liefert
  Split-adjustierte OHLC, aber keine Split-Events. Hook bleibt bestehen.
  **⚠️ Wichtige Konsequenz — siehe eigener Warnabschnitt in Kap. 10.1.**
- **Option Expiries:** `apply_expiries` schließt am oder nach
  `expiration_date` — ITM → Assignment via `_settle_assignment` (Cash-
  und Stock-Adjustment, ggf. Merge mit vorhandenem Stock-Leg mit
  weighted-average entry price); OTM → Leg wird entfernt. Sobald das
  letzte Leg der Position weg ist, wird `realized_pnl =
  entry_cashflow + Summe(Assignment-Cashflows)` gesetzt und die
  Position via `_move_to_closed` → `on_position_closed` an den
  Collector gemeldet.
- **DTE-Close:** siehe 3.4.
- **Stop-Orders:** SL / Trailing / TP (`stop_orders.py`).
- **Universe Enforcement:** Hard-Exit bei Symbol-Drop **nur für
  stock-only** Positionen.
- **Rolling:** wenn die Strategie einen `rolling_manager` hat, wird
  `check_rolling(portfolio, snapshot)` in der Maintenance-Phase
  aufgerufen.

**Nicht in V1:** Margin-Zinsen und Short-Borrow-Fees sind konfigurierbar
(`RunConfig.margin_interest_rate`, `borrow_fee_default`) aber **noch nicht
in der Portfolio-Buchhaltung implementiert** — siehe Kap. 10 „Ehrliche
Limitierungen".

### 4.5 Eine Wahrheit für Realized-P&L

Das Portfolio ist der **einzige** Ort, an dem eine Position wirklich als
geschlossen gilt. `Portfolio._move_to_closed(position)` fired dann einen
Callback (`portfolio.on_position_closed`), den die Engine mit
`ResultsCollector.on_position_closed` verdrahtet. Das gilt einheitlich
für alle Close-Pfade:

- Executor-Close via `ClosePosition` / `ClosePartial` (`fraction=1.0`)
- `Portfolio.close_position(...)` (DTE-Close, Stop-Order, Universe-Exit)
- `Portfolio.apply_expiries(...)` (ITM-Assignment und OTM-Verfall)

Vor V1-Refactor gab es **zwei** P&L-Zahlen: einmal die vom Executor
tatsächlich in `portfolio.cash` gebuchten Cashflows, und einmal eine
Rekonstruktion aus dem Trade-Log in `_build_position_log`. Die
Rekonstruktion hat u. a. Assignments/Expiries gar nicht mitgezählt,
weil dafür keine Trade-Log-Zeilen entstehen. Diese zweite Rechnung
ist entfernt — der Collector führt die `position_log` jetzt direkt.

---

## 5. Strategien — Zwei Bahnen

### 5.1 Bahn 2: Python-Strategien (Strategy-Base-API)

```python
class Strategy:
    name: str
    description: str
    params: StrategyParams
    universe_default: Optional[UniverseSpec] = None
    preload_fields: list[str] = []
    rolling_manager = None
    _logger: Optional["ResultsCollector"] = None  # von engine injiziert

    def on_init(self, config) -> None: ...
    def compute_daily(self, snapshot, portfolio) -> None: ...
    def on_day(self, snapshot, portfolio) -> list[Action]: ...    # MANDATORY
    def on_position_opened(self, position, snapshot) -> None: ...
    def on_position_closed(self, position, snapshot) -> None: ...
    def on_symbol_dropped(self, symbol, snapshot) -> None: ...

    def log_detail(self, symbol, message, snapshot, **kwargs) -> None:
        """Non-Trade-Log-Zeilen — siehe Kap. 9.4 Quantity-Konvention."""
```

Strategien werden über `__init_subclass__` automatisch in der
`registry` registriert (kein manueller Aufruf nötig, solange
`name` gesetzt ist und die Datei geladen wird).

**Per-Instance-Params:** `Strategy.__init__` erzeugt für jede
Strategie-Instanz eine `params.copy()` (via `StrategyParams.copy()`).
Das Klassenattribut `params` bleibt der Default; per-Run-Änderungen
über `strategy.params.set(...)` bleiben lokal in der Instanz. Wichtig
für V2 (Grid-Search / parallele Backtests), und robust auch schon
für V1 (die UI erzeugt pro Lauf eine frische Instanz).

**Parameter-API (`StrategyParams`):** deklarativ mit Typ, Default, Range,
Step. Beispiel:

```python
params = StrategyParams(
    delta_target    = NumericParam(0.30, range=(0.10, 0.50), step=0.05),
    dte_range       = TupleParam((30, 45), constraints="dte"),
    exit_profit_pct = NumericParam(0.50, range=(0.20, 0.95), step=0.05),
)
```

→ Frontend generiert das Form aus dieser Deklaration automatisch
(`_render_param_form` in `pages/backtest.py`).

### 5.2 Bahn 1: UI-Template-Konfigurator

Der User wählt eines der **6 V1-Templates** aus und parametrisiert es:

| Template | Datei | Inhalt |
|---|---|---|
| Buy and Hold | `buy_and_hold.py` | Kauft `shares_per_symbol` je Symbol am ersten Tag, verkauft am letzten. Für Benchmark-Vergleiche gedacht. |
| Cash-Secured Put | `cash_secured_put.py` | Short OTM Put nach `delta_target` × `dte_range`, Exit bei `exit_profit_pct` der Prämie. |
| Covered Call | `covered_call.py` | 100 Shares + Short OTM Call, Roll/Exit-Regeln. |
| Wheel | `wheel.py` | CSP → Assignment → CC → Called Away → CSP-Zyklus (state via `tags["stage"]`). |
| Vertical Spread | `vertical_spread.py` | Bull-Put / Bear-Call / Bull-Call / Bear-Put — eine Klasse, vier `ChoiceParam`-Varianten. |
| Iron Condor | `iron_condor.py` | Short Call-Spread + Short Put-Spread, symmetrische Wing-Width. |

Jedes Template ist intern eine Bahn-2-Strategie-Klasse. Bahn 1 ist „Bahn 2
mit auto-generiertem Form".

**Bewusst nicht V1:** völlig freier visueller Block-Editor
(„wenn-X-dann-Y zusammenklicken"). Diese Brücke ist V2-Roadmap.
V1-Erweiterung: Dev schreibt neue Strategy-Klasse → Frontend zeigt sie
automatisch, sobald das Modul in `strategies/__init__.py` importiert
wird.

---

## 6. Rolling-Strategien (Wiederverwendbare Teilstrategien)

Rolling-Logik ist als modulare Komponente in `strategies/rolling.py`
entkoppelt, damit sie in verschiedenen Hauptstrategien (Wheel, Spreads,
etc.) konsistent eingesetzt werden kann.

### 6.1 Konzept

Rollstrategien sind zustandsbehaftete Sub-Strategien, die einer Position
über `tags["roll_strategy"]` zugeordnet werden. Die Engine ruft
`portfolio.check_rolling(snapshot, strategy)` in der Maintenance-Phase auf,
was auf `strategy.rolling_manager.check_rolling(portfolio, snapshot)`
delegiert; der Manager dispatched pro Position auf die konkrete
`RollStrategy`.

### 6.2 Eric-Ludwig Default-Vorlage

Diese Vorlage implementiert das 4-Phasen-Modell zur defensiven Verteidigung
von (Short) Optionen. Die Trigger-Konstanten sind in
`EricLudwigStrategy` als Klassenattribute mit Defaults hinterlegt.

**Verfügbare Trigger-Variablen:**
- `pos.delta_current`
- `pos.distance_to_strike_pct(snap)`
- `pos.unrealized_pnl_pct()`
- `pos.dte`
- `pos.roll_count`
- `snap.get_stock(sym).iv_rank`

**PHASE 1 – VERTIKAL (Basispreis-Optimierung):**
- **Trigger:** Position deutlich im Geld / Delta > 0.60
- **Aktion:** Basispreis nach unten anpassen (gleiche/ähnliche Laufzeit)
- **Ziel:** Break-even verbessern, Netto-Prämie ≥ 0 (Roll for Credit/Even)
- **Max. Anzahl:** über `roll_count` begrenzbar

**PHASE 2 – HORIZONTAL (Zeit-Gewinn):**
- **Trigger:** Phase 1 ausgeschöpft / DTE < 14
- **Aktion:** Laufzeit verlängern
- **Ziel:** zusätzliche Zeitprämie, mehr Puffer

**PHASE 3 – VERTIKAL (erneut):**
- **Trigger:** Kurs weiter gegen die Position
- **Aktion:** erneute Basispreis-Anpassung, nur wenn Netto-Kredit möglich

**PHASE 4 – POSITIONSGRÖSSE:**
- **Trigger:** Phasen 1-3 ausgeschöpft
- **Aktion:** Kontraktanzahl anpassen (Risikogrenze über
  `params["max_contracts"]`)

### 6.3 Interface

```python
class RollingManager:
    def check_rolling(self, portfolio, snapshot): ...
    def _get_roll_action(self, position, snapshot) -> Optional[Action]: ...

class RollStrategy:
    def evaluate(self, position, snapshot) -> Optional[Action]:
        raise NotImplementedError

class EricLudwigStrategy(RollStrategy):
    def __init__(self, params: dict): ...
    def evaluate(self, position, snapshot) -> Optional[Action]:
        # dispatch to _phase_1..4
        ...
```

---

## 7. Execution-Layer

### 7.1 Pricing & Timing

- **Timing:** Um **Look-Ahead Bias** zu vermeiden, sieht die Strategie am
  Tag *t* zwar den Schlusskurs, Orders werden als **Market-on-Close (MOC)**
  simuliert (`RunConfig.execution_timing = "moc"`, alternativ `"next_open"`
  — Hook vorhanden, noch nicht durchimplementiert).
- **Preisfindung:** Aktien: `live_stock_price`. Optionen: `day_close` aus
  der Options-Chain. Sowohl Executor als auch das automatische
  `close_position` verwenden diese Felder konsistent.

### 7.2 Slippage

**Dynamische OI-basierte Slippage als Default** (`RunConfig.slippage_mode
= "oi"`, umschaltbar auf `"fixed"` mit `slippage_fixed_pct`):

| Liquiditätsklasse | Slippage |
|---|---|
| Aktien | 0.05 % |
| Optionen OI > 1000 | 0.5 % |
| Optionen OI 100–1000 | 1.0 % |
| Optionen OI < 100 | 3.0 % — oder Order rejected wenn `reject_illiquid=True` |

Sowohl beim Open als auch beim Close/Adjust wird die **echte OI des
Kontrakts** aus dem Tages-Snapshot gezogen (`option_osi`-Match gegen
`snapshot.get_chain(symbol).all()`). Fällt ein Kontrakt aus dem Snapshot
(z. B. am Expiry-Tag oder nach Delisting), fallback auf OI=0 →
illiquide Tier.

### 7.3 Commission (IB-Vorbild, konfigurierbar)

```python
CommissionConfig(
    option_per_contract  = 0.65,
    option_min_order     = 1.00,
    stock_per_share      = 0.005,
    stock_min_order      = 1.00,
    stock_max_pct        = 0.01,
    regulatory_per_option = 0.05,
)
```

Wird pro Trade-Log-Eintrag als `commission`-Feld ausgewiesen (bei
Multi-Leg-Orders anteilig verteilt auf alle Legs).

### 7.4 Margin & Finanzierungskosten

**Margin (Reg-T)** — `RegTMarginCalculator.position_margin(...)`:

| Position-Typ | Initial Margin |
|---|---|
| Covered Call (Stock + Short Call) | 0 (besichert) |
| Cash-Secured Put | Strike × 100 × Qty (Cash-Reserve) |
| Naked Short Put | 20 % × Underlying − OTM-Amount + Prämie |
| Naked Short Call | 20 % × Underlying − OTM-Amount + Prämie |
| Vertical Spread | Spread-Width × 100 × Qty |
| Iron Condor | max(Call-Spread-Width, Put-Spread-Width) × 100 × Qty |
| Long Stock auf Margin | 50 % Initial / 25 % Maintenance |

**Finanzierungskosten (V1-Stand):**
- `RunConfig.margin_interest_rate` (Default 0.07 = 7 % p.a.) und
  `borrow_fee_default` (Default 0.01 = 1 % p.a.) sind **im Portfolio
  konfiguriert, aber der tägliche Zins-/Fee-Post ist noch nicht
  implementiert.** Der Hook lebt in `Portfolio.config` und im
  Config-Panel der UI, die Buchung fehlt — siehe „Ehrliche
  Limitierungen" (Kap. 10).

**Margin-Call:** Maintenance-Verletzung → Engine schließt Position(en)
automatisch (vereinfachte Umsetzung — echter Broker würde Anrufzeit
gewähren).

**V2-Roadmap:** Portfolio Margin (risikobasiert).

### 7.5 Order-Mechanik

- **Multi-Leg-Orders sind atomar.** Wenn ein Leg unpriceable ist oder die
  Margin-Prüfung verletzt, wird die ganze Order rejected und als
  Trade-Log-Eintrag mit `type="reject"` + `reason` festgehalten.
- **Rejected Orders** sind kein Fehler — die Strategie sieht im nächsten
  `on_day`, dass die Position nicht da ist, und kann reagieren.

### 7.6 Auto-Mechaniken bei Corporate Actions / Expiries

- **Dividenden:** siehe 4.4 (Ex-Date-Simulation über
  `last_dividend_date == snapshot.date`).
- **Splits:** V1 no-op (OHLC bereits split-adjusted in der DB).
- **Expiries:**
  - Short ITM Call → Shares gehen weg, Cash rein (Strike × 100 × qty)
  - Short ITM Put → Shares kommen rein, Cash raus
  - OTM → Leg wird entfernt (Restwert 0)
  - Assignment mergt bei bereits gehaltenem Stock-Leg mit
    weighted-average entry price.
- **Early Assignment:** V1 nicht modelliert (Roadmap).

### 7.7 Komponenten

```
src/backtesting/execution/
├── executor.py    # dispatch: OpenPosition, Close*, AdjustPosition, Set*Stop
├── slippage.py    # OI-basiert + fix-pct
├── commission.py  # IB-Tiered, konfigurierbar
└── margin.py      # Reg-T calculator
```

`expiries.py` und `corporate_actions.py` aus dem Ursprungsdesign existieren
**nicht** als separate Files — die Logik liegt direkt in
`portfolio.apply_expiries` bzw. `apply_dividends`/`apply_splits`.

---

## 8. Results

### 8.1 Rohdaten-Sammlung während des Laufs

| Log | Inhalt | Granularität | Speicher |
|---|---|---|---|
| Trade-Log | Jede Order-Ausführung mit Pricing, Slippage, Commission, Cash-Status, `position_id`, `reason` | pro Leg pro Action | `results.trade_log` |
| Daily-Portfolio-Log | Cash, Equity, Margin, Buying Power, offene Positionen, Unrealized P&L | pro Handelstag | `results.daily_log` |
| Detail-Log | Trade-Mirror + Non-Trade-Info (Strategie-Entscheidungen, „Holding position", „Entry skipped", …) — siehe Kap. 9.4 | pro Trade-Leg + strategie-generiert | `results.detail_log` |
| Position-Log | Zusammenfassung aller Positions-Lebenszyklen (open/close, Holding-Days, Realized-P&L, Close-Reason, Legs-at-Close) | pro Position | `results.position_log` — vom `Portfolio.on_position_closed`-Callback direkt beim Move-to-Closed befüllt. **Eine Wahrheit:** kein Reconstruction-from-Trade-Log mehr, deshalb erscheinen auch Assignments / OTM-Expiries / DTE-Closes mit korrektem `realized_pnl` |

### 8.2 Abgeleitete Metriken

`PerformanceMetrics` (in `metrics.py`) hält:

**Standard-Performance:** `total_return`, `cagr`, `max_drawdown_abs` /
`_pct` / `_days`, `sharpe`, `sortino`, `calmar`, `annualized_vol`.

**Trade-Statistik:** `n_trades`, `win_rate`, `avg_win`, `avg_loss`,
`largest_win`, `largest_loss`, `profit_factor`, `avg_holding_days`,
`expectancy`.

**Benchmark:** `benchmark_total_return`, `alpha`, `beta`
(Vergleich gegen `BenchmarkTracker` — Buy & Hold des Benchmark-Symbols).

**Symbol-Breakdown:** in der UI live aus `position_log` aggregiert
(nicht als Feld in `PerformanceMetrics`) — Anzahl Trades, Win-Rate,
Total P&L, Avg P&L, `contribution_pct` = `total_pnl / sum(total_pnl)`.

### 8.3 Persistenz (Ist)

**File-basiert unter `data/backtest_runs/{run_id}/`:**

```
config.json         # RunConfig + Strategie-Name + Zeitraum
metrics.json        # PerformanceMetrics als dict
trade_log.parquet   # Fallback: .csv wenn pyarrow fehlt
daily_log.parquet
position_log.parquet
detail_log.parquet
benchmark.parquet
```

`storage.save_results(results)` und `storage.load_results(run_id)` +
`list_runs()` betreiben das. Frontend zeigt einen Load-Selector unter
„Saved runs".

**V2-Roadmap:** Postgres-Tabellen `BacktestRun`, `BacktestTrade`,
`BacktestDaily` für queryable Persistenz.

### 8.4 Benchmark-Vergleich

`BenchmarkTracker` (`results/benchmark.py`) kauft am ersten Tag mit
`live_stock_price` des Benchmark-Symbols so viele Shares wie mit
`initial_cash` möglich (Total-Return-Proxy per `live_stock_price` —
Dividenden werden nicht separat reinvestiert, sondern kommen implizit
über die adjustierte Zeitreihe rein). Beobachtet täglich in
`collector.record_day` und stellt `benchmark_series` bereit.

### 8.5 Komponenten

```
src/backtesting/results/
├── collector.py   # ResultsCollector.record_trade/record_day/record_detail
├── metrics.py     # PerformanceMetrics dataclass + MetricsCalculator
├── benchmark.py   # BenchmarkTracker (Buy & Hold)
├── storage.py     # save/load, list_runs, Parquet/JSON
└── export.py      # export_csv/export_json für UI-Downloads
```

---

## 9. Frontend (`pages/backtest.py`)

Streamlit-Page mit **6 Tabs**: Setup, Performance, Trades, Symbols,
Details, Export.

### 9.1 Tab „Setup"

- Strategie-Auswahl (Dropdown aus `registry.list_names()`)
- Auto-generierte Parameter-Form (`_render_param_form`) aus
  `strategy_cls.params.specs()` — Widget-Typ pro Param-Klasse
  (NumericParam → `st.number_input`, TupleParam → zwei Inputs, ChoiceParam →
  `st.selectbox`, BoolParam → `st.checkbox`).
- Universum-Setup (`_render_universe_setup`) — Radio static / dynamic;
  dynamisch: Expander pro Kategorie aus `FIELD_CATEGORIES`.
- Zeitraum: **Default letzte 60 Tage** (`date.today() - 60d` →
  `date.today()`).
- Engine-Config: Initial Cash ($), Slippage-Mode (`oi` / `fixed`),
  DTE-Close-Threshold, Benchmark-Symbol, Margin-Zinssatz (%/Jahr),
  „Reject illiquid option orders" Checkbox.
- Vor dem Start: `validate_universe_and_range` (static-Modus) —
  Warnings/Errors werden angezeigt, DB-Coverage wird als Info gezeigt.
- Progress-Bar mit „Day X/N — Datum" und Live-Equity/Open-Positions.
- Nach dem Lauf: `save_results(results)` + Session-State-Cache.

Zusätzlich am unteren Ende: „Load saved run"-Selector.

### 9.2 Tab „Performance"

- **Metric-Cards** (3 Reihen à 4) — Total Return, CAGR, Sharpe, Max DD, Win
  Rate, Profit Factor, # Trades, Expectancy, Volatility, Sortino, Calmar,
  Alpha. Formatierung siehe Kap. 9.5.
- **Equity-Curve** (Strategy vs. Benchmark) via Plotly.
- **Drawdown-Kurve** als Prozent (`yaxis_tickformat=".2%"`).

### 9.3 Tab „Trades"

- `results.trade_log` als Streamlit-DataFrame mit Spaltenformat
  (Dollar-Spalten `$%.2f`, Prozent-Spalten `%.2f%%` — siehe Kap. 9.5).
- „Closed positions": `results.position_log` als zweite Tabelle.

### 9.4 Tab „Details" (Neu, seit Detail-Logging-Feature)

Der Detail-Log wird aus zwei Quellen befüllt:

1. **Trade-Mirror:** Für jeden Trade-Log-Eintrag mit legitem
   `position_id` schreibt `engine._record_trade_as_detail(...)` eine
   Detail-Zeile mit:
   - `message` = `"Transaction: {type} ({reason})"`
   - `price`, `cost`, `proceeds`, `commission`
   - **`quantity_change`** — signiertes Delta durch diese Aktion
     (positiv = buy/add, negativ = sell/close)
   - **`quantity_position`** — verbleibender Bestand *dieses Legs*
     nach der Aktion. Bei Full-Close: `0`. Bei Multi-Leg-Positionen
     (Iron Condor, Covered Call): eine Zeile pro Leg mit
     Leg-spezifischer Balance. Identifikation:
     - Option-Legs → per `option_osi` innerhalb der Position
     - Stock-Legs → per `symbol` innerhalb der Position

2. **Strategie-Info** via `Strategy.log_detail(symbol, message, snapshot,
   **kwargs)` — für Non-Trade-Zeilen. Konvention für konsistente Spalten:
   `quantity_change=0`, `quantity_position=<aktueller Bestand>`. Bereits
   umgesetzt in `buy_and_hold.py` („Holding position") und
   `iron_condor.py` („Holding Iron Condor"); Log-Zeilen ohne
   Quantity-Bezug lassen die Felder weg (Streamlit rendert dann NaN).

**Semantik-Beispiele:**

| Vorgang | quantity_change | quantity_position |
|---|---|---|
| Open long stock, 100 Shares | +100 | +100 |
| Zusatzkauf 50 Shares zur selben Position | +50 | +150 |
| Verkauf 60 Shares (Partial Close) | −60 | +90 |
| Vollständiges Close der 90 Shares | −90 | 0 |
| Open Short-Put, 2 Kontrakte | −2 | −2 |
| Close Short-Put (buy-back) | +2 | 0 |
| Iron Condor open (4 Legs) | pro Leg ±1 | pro Leg entsprechend |
| „Holding position" (Non-Trade) | 0 | aktueller Bestand |

### 9.5 Zahlen-Formatierung (Backtesting-Page-Konvention)

**Dollar-Werte:** immer 2 Nachkommastellen (`$1,234.56`).

- Metric-Cards (`fmt_dol`) → `$%,.2f`.
- Progress-Text-Equity → `${equity:,.2f}`.
- Alle DataFrame-Dollar-Spalten in Trades / Details / Positions /
  Symbols über `st.column_config.NumberColumn(format="$%.2f")` verdrahtet.
  Whitelist: `price`, `premium`, `cost`, `proceeds`, `commission`,
  `cash`, `equity`, `margin_used`, `buying_power`, `unrealized_pnl`,
  `realized_pnl`, `total_pnl`, `avg_pnl`, `entry_price`, `exit_price`,
  `strike`.

**Prozentwerte:** immer 2 Nachkommastellen (`15.23 %`).

- Metric-Cards (`fmt_pct`) → `{v*100:.2f}%`.
- Drawdown-Chart y-Axis → `yaxis_tickformat=".2%"`.
- Alle DataFrame-Prozent-Spalten via
  `st.column_config.NumberColumn(format="%.2f%%")`. Da die Rohdaten als
  Fraktionen (0.15 = 15 %) gespeichert sind, wandelt `_prepare_display_df`
  eine Anzeige-Kopie vor `st.dataframe`-Aufruf durch Multiplikation mit
  100. Whitelist: `slippage_pct`, `contribution_pct`, `win_rate`,
  `pnl_pct`, `target_pnl`, `iv_rank`, `iv_percentile`.

**Zahlenwerte ohne Einheit** (Sharpe, Sortino, Calmar, Profit Factor):
`fmt_num` → 2 Nachkommastellen.

**Nicht formatiert:** Free-Text-Log-Messages (z.B.
`"Closing Iron Condor: Target PnL reached (23.5%)"`) — der Text kommt
aus der Strategie-Datei und wird als Rohtext angezeigt.

### 9.6 Tab „Symbols"

Symbol-Breakdown-Tabelle aus `position_log.groupby("symbol")`:
`n_trades`, `total_pnl`, `avg_pnl`, `win_rate`, `contribution_pct`.
Sortiert nach `total_pnl` desc. Formatierung wie oben.

### 9.7 Tab „Export"

`st.download_button`-Reihen für Trade-Log-CSV, Daily-Log-CSV,
Position-Log-CSV, Detail-Log-CSV, Metrics-JSON, Config-JSON.

---

## 10. Ehrliche Limitierungen (User-Doku)

### 10.1 ⚠️ Aktien-Splits während der Backtest-Laufzeit

**Kurzfassung:** Bei Backtests, die einen Aktien-Split überstehen,
verfälschen sich MTM und Realized-P&L systematisch. Bis ein
Split-Event-Kanal existiert (V2-Roadmap), sollten Zeiträume mit
bekannten Splits gemieden werden.

**Ursache — der Zustand ist inkonsistent:**

- Skuld's DB liefert **split-adjustierte** OHLC-Zeitreihen: der
  historische Kurs vor einem 4-für-1-Split wird auf ein Viertel
  korrigiert, sobald der Split stattgefunden hat. Ein Snapshot zeigt
  also *nach* dem Split den geviertelten Preis, auch für Tage *vor*
  dem Split.
- Das Portfolio hält Positionen mit `entry_price` **aus der Zeit vor
  dem Split** (unadjustiert). Beim täglichen `mark_to_market` wird
  dieser alte `entry_price` gegen den neuen, adjustierten
  `live_stock_price` gestellt.
- Ergebnis: die Position wirkt so, als hätte sie 75 % Wert verloren
  (bei 4-für-1). Realer Anleger hätte die 4-fache Stückzahl bekommen
  und wäre wertneutral.

**Konkrete Auswirkung:**

- `Position.market_value`, `unrealized_pnl`, `unrealized_pnl_pct`:
  falsch ab dem Split-Tag.
- `Portfolio.equity`, `Portfolio.mark_to_market`: falsch, weil Legs
  falsch bewertet werden.
- Stop-Loss/Trailing-Stop: **triggern fälschlich**, weil der
  scheinbare Kursabsturz die Level unterschreitet.
- Realized-P&L bei Close nach Split: um Faktor `split-ratio` verzerrt.
- Optionen-Legs: Strike würde in Realität mitadjustiert
  (Split-adjusted Strikes), im Backtest bleibt der alte Strike. Wenn
  die Options-Chain nach Split neu geladen wird, gibt es den alten
  Strike möglicherweise nicht mehr → Position "verschwindet" beim
  Expiry-Check oder wird als OTM verworfen.

**Warum nicht V1-fixbar:**

Ein sauberer Fix bräuchte eine **Split-Event-Tabelle** in der Skuld-DB
(Symbol, Ex-Date, Ratio) — die existiert dort aktuell nicht. Ohne
diese Daten kann die Engine Splits nicht erkennen. Alternativen wie
"Split aus Kurssprung heuristisch inferieren" wären fehleranfällig
und über Dividenden schwer trennbar.

**Praktische Handreichung bis V2:**

- Für Optionsstrategien (CSP, CC, Wheel, Vertical Spread, Iron Condor)
  laufen typische Backtest-Zeiträume ≤ 6 Monate — Split-Risiko real
  gering, aber prüfbar (yfinance Splits-Liste).
- Für Buy-and-Hold / Aktien-Backtests ≥ 1 Jahr: **explizit prüfen**,
  ob im Universum × Zeitraum Splits liegen. Bekannte Fälle Recent:
  AAPL 4-für-1 (2020-08-31), TSLA 3-für-1 (2022-08-25), NVDA 10-für-1
  (2024-06-10). Solche Symbole aus dem Universum nehmen oder Backtest
  auf Zeitraum vor/nach dem Split beschränken.

**Roadmap V2:** Split-Event-Tabelle in Skuld-DB → `apply_splits`
adjustiert Position-Quantity + Option-Strikes am Ex-Date. Bis dahin
bleibt der Hook im Code, tut aber nichts.

### 10.2 Übersicht weitere Limitierungen

| Thema | Status V1 | Anmerkung |
|---|---|---|
| Granularität | Nur EOD | Keine Intraday-Strategien |
| Bid/Ask-Realismus | `day_close` (Optionen) bzw. `live_stock_price` (Aktien) als Mid-Proxy + Slippage-Heuristik | Bei illiquiden Symbolen optimistisch |
| Survivor-Bias | Nicht behandelt | Statisches Universum = heutige Symbole; historische S&P-Mitgliedschaft = V2 |
| Early Assignment | Nicht modelliert | Nur Expiry-Assignment |
| Portfolio Margin | Nicht in V1 | Reg-T only |
| Splits | ⚠️ siehe Kap. 10.1 — Portfolio-Hook ist V1 no-op, DB liefert bereits split-adjustierte OHLC ohne Event-Kanal | Backtests über Split-Tage vermeiden bis V2 |
| Margin-Zinsen / Borrow-Fees | Config vorhanden, tägliche Buchung noch nicht implementiert | Hook lebt in `RunConfig` + `Portfolio.config` |
| RAM-Warnung | `estimate_ram_gb` implementiert, in der UI **noch nicht** angezeigt | Roadmap-Punkt |
| Multi-Strategy-Portfolio | Nicht in V1 | Eine Strategie pro Backtest; „Systeme" = Roadmap |
| Daten-Historie-Tiefe | Abhängig von Skuld-DB-Stand | Via `validate_universe_and_range` messbar |
| Postgres-Persistenz | File-basiert in V1 | DB-Tabellen = V2 |
| Async/Worker | Nein, synchron in Streamlit | Job-Queue = V2 wenn Performance-Schmerz |

---

## 11. Roadmap V2+

In Reihenfolge wahrscheinlicher Nachfrage:

1. Grid-Search / Parameter-Sweep über `StrategyParams`
2. Walk-Forward-Validierung (rollende Train/Test-Windows)
3. Portfolio Margin
4. Early Assignment (mit Ex-Dividenden-Trigger)
5. Multi-Strategy-Portfolios („Systeme")
6. Postgres-Persistenz + Run-Vergleichs-UI
7. Custom visueller Strategy-Builder (Block-Editor)
8. Historische S&P500-Mitgliedschaft (Survivor-Bias-freie dynamische
   Universen)
9. User-uploadbare Python-Strategien (mit Sandboxing)
10. Async Job-Queue für lange Läufe
11. Margin-Zins- und Borrow-Fee-Tagesbuchung tatsächlich verdrahten
12. RAM-Estimator in die UI hängen
13. `next_open`-Execution-Timing zu Ende implementieren
14. **Split-Event-Kanal + `apply_splits`-Verdrahtung** — Voraussetzung:
    Skuld-DB liefert (Symbol, Ex-Date, Ratio). Sobald verfügbar,
    Position-Quantity und Option-Strikes am Ex-Date adjustieren.
    Ohne diesen Kanal sind Backtests über bekannte Split-Tage
    unzuverlässig (Details siehe Kap. 10.1).

---

## 12. Komponenten-Karte (Kurzfassung)

```
src/backtesting/
├── engine/          # run(), Portfolio, Actions, Stop-Orders, Calendar,
│                      Trade→Detail-Mirror
├── data/            # Snapshot, Smart-Preloader, Universe, Filter-Whitelist, Validator
├── strategies/      # Base-Class, Registry, 6 V1-Templates, Rolling (Eric Ludwig)
├── execution/       # Slippage, Commission, Margin (Reg-T), Order-Dispatch
│                      (Expiries + Corporate Actions leben in `portfolio.py`)
└── results/         # Collector, Metrics, Benchmark, File-Storage, Export

pages/backtest.py    # Streamlit-Frontend, 6 Tabs (Setup / Performance /
                       Trades / Symbols / Details / Export)

db/SQL/query/backtest/
├── available_symbols.sql
├── data_coverage.sql
└── merged_snapshot.sql
```

Externe Dependencies (alles bereits in Skuld):

- `pandas` (Daten-Layer)
- `sqlalchemy` + `psycopg2` (DB-Zugriff via existierende `src/database.py`)
- `streamlit` (Frontend)
- `plotly` (Charts)
- `pyarrow` (Parquet-Persistenz — optional, Fallback CSV)

---

## 13. Offene Punkte für Implementation (Deltas gegen Design)

1. **RAM-Warnung** aus `estimate_ram_gb` in die Setup-UI hängen.
2. **Margin-Zinsen und Borrow-Fees** tatsächlich täglich verbuchen
   (Config existiert, Portfolio-Buchhaltung fehlt).
3. **`next_open`-Execution-Timing** implementieren (heute liest der
   Executor immer `live_stock_price` / `day_close` von Tag *t*).
4. **Whitelist der Filter-Felder** weiter ergänzen — `fields.py` ist
   Startpunkt.
5. **`getOptionDataMergedHistory`** ist per Snapshot-Cache und optionaler
   `WHERE symbol IN`-Filterung schon Cost-optimiert; echter Bulk-Query
   über einen Range (statt Tag-für-Tag) wäre V2-Performance-Booster.
6. **Aktuelle Skuld-Symbol-Quelle:** `OptionDataMerged` — bestätigt durch
   `data_coverage.sql`.
7. **Trading-Calendar-Quelle:** aktuell `engine.calendar.trading_days`
   (Werktage). Umstieg auf `exchange_calendars` (NYSE-Kalender inkl.
   Feiertagen) wäre Präzisionsgewinn.

---

## 14. Empfohlener Ausbau-Fahrplan

Diese Reihenfolge baut das Framework so aus, dass jede neue Phase auf
den zuvor **verifizierten** Teilen aufbaut. Vor jedem Phasenwechsel gilt:
die aktuelle Phase muss reproduzierbare, per Handrechnung plausible
Ergebnisse liefern. „Sieht plausibel aus" reicht nicht — Zahl gegen
Excel-Rechnung stellen.

### 14.1 Kern-Prinzipien (gelten überall)

**Aktien vor Optionen.** Aktien-Backtests testen Engine-Loop, MTM,
Cash-Buchung, Universum-Resolution, Metrics, Stop-Orders. Wenn diese
schon nicht stimmen, ist alles auf Options-Ebene Kaffeesatz. Aktien
sind das schnellere Feedback-Signal.

**Aber:** „Aktien funktionieren → alles funktioniert" gilt **nicht**.
Options-Chain-Loading, Multi-Leg-Positionen, OI-Slippage, Assignment /
Expiry / DTE-Close, Reg-T-Margin pro Position-Typ und der
Rolling-Manager sind unabhängige Systeme, die separat validiert werden
müssen — deshalb die granulare Options-Reihenfolge unten.

### 14.2 Golden-Path-Test (querschnittliches Werkzeug)

Bevor Phase 2 startet, einen kleinen reproduzierbaren
Regressionstest anlegen — kein Streamlit, kein Framework-Feature,
sondern ein Notebook oder Script unter `tests/backtesting/golden_path/`:

- Nimm einen Zeitraum von 5–10 Handelstagen, ein einzelnes Symbol.
- Rechne per Excel/Papier die erwartete Equity-Kurve, Trade-Liste,
  Realized-P&L aus.
- Backtest gegen dasselbe Setup laufen lassen.
- Assert: numerische Übereinstimmung bis auf Cent.

Für jede neu abgeschlossene Phase kommt eine neue Golden-Path-Datei
dazu (B&H, SMA-Crossover, CSP-mit-Assignment, …). Ein Regressionstest,
der bei jeder späteren Änderung sofort sagt „kaputt". Nicht als
Unit-Test — als reproduzierbares Notebook, das man vor jedem Merge
lokal durchklickt.

### 14.3 Cash-Identity als Sanity-Assert

Diese Identität muss nach jedem Backtest **immer** gelten:

```
sum(realized_pnl über alle geschlossenen Positionen)
  + sum(unrealized_pnl über alle offenen Positionen)
  - sum(commissions)
  == portfolio.equity - initial_cash
```

Als 3-Zeilen-Assert am Ende von `run()` (in die Logs schreiben, nicht
crashen — wir wollen den kaputten Lauf sehen können). Wenn die
Identität verletzt ist, hat das Framework Cash verloren oder verdoppelt
— rettet zukünftig Wochen an Detektivarbeit.

### 14.4 Phase 1 — Buy & Hold stabilisieren (aktueller Stand)

**Ziel:** B&H über 3–4 verschiedene Zeiträume × Symbole liefert
Standard-P&L, verifizierbar per Handrechnung („100 SPY × Preisdelta
minus Commissions"). Benchmark-Vergleich sinnvoll.

**Was getestet wird:** Engine-Loop, MTM, Cash-Buchung, Universum-
Resolution (statisch), Portfolio-Equity, Drawdown, Sharpe, Alpha vs.
Benchmark, position_log via `on_position_closed`-Callback.

**Abschluss-Kriterium:** Golden-Path-Test „B&H_SPY_10_days.md" grün.

### 14.5 Phase 2 — SMA-Crossover (erste Custom-Aktien-Strategie)

**Warum:** Nicht „Moving Average als Signal" (das wäre B&H mit Timing),
sondern **SMA(50) × SMA(200) Crossover** oder ähnlich —

- Öffnet und schließt dieselbe Position mehrfach im Backtest → testet
  **wiederholtes Open/Close**.
- Golden-Cross / Death-Cross → testet **beide Richtungen**.
- Braucht rollende Fenster → testet die `compute_daily`-Hook (bisher
  ungenutzt, Bug-Risiko).
- Verifizierbar gegen manuellen Excel-Backtest.

**Was getestet wird:** `compute_daily`, wiederholte Position-Zyklen,
gemischte P&L (Winners + Losers), Realized-vs-Unrealized-Trennung.

**Abschluss-Kriterium:** Golden-Path-Test „SMA_5_trades.md" grün.

### 14.6 Phase 2b — Stop-Loss auf Aktienposition

**Warum:** Nur ein Trade in einer B&H-Variante mit `SetStopLoss` bei
−10 % (oder Trailing-Stop). Testet die Stop-Order-Maschinerie **ohne**
Options-Komplexität. Wenn Trailing-Stop mit falschem Peak triggert,
sieht man das hier sofort — später mit Options-Assignment im Spiel wäre
das ein Detektiv-Fall.

**Was getestet wird:** `StopLossOrder`, `TrailingStopOrder`,
`TakeProfitOrder` (Peak-Tracking, Trigger-Level).

### 14.7 Fundamentaldaten / Weitere Aktien-Filter — bewusst **nicht**
       als eigene Phase

Rationale: „Custom-Aktien-Strategie mit RSI oder Fundamentaldaten"
liefert **kein neues Framework-Signal**. Wenn Phase 2 (SMA) läuft und
das Universum-Filter-System (`FIELD_CATEGORIES`) sauber ist, dann sind
RSI/MACD/KGV/Umsatzwachstum als Filter/Signal nur andere Werte an
denselben Hebeln. Skippen und direkt in Optionen — der eigentliche
Framework-Härtetest.

Falls doch: das gehört als Strategie-Variante ins gleiche Set wie SMA
(Phase 2), nicht als eigene Phase.

### 14.8 Phase 3 — Cash-Secured Put (erste Options-Strategie)

**Warum CSP zuerst, nicht „irgendein Standard-Options-Ding":**

- **Ein Leg** (Short Put) — maximal einfach.
- **Ein Assignment-Pfad:** ITM Put → Shares kommen rein → Position hat
  jetzt einen Stock-Leg. Testet `apply_expiries` + `_settle_assignment`
  in einem einzelnen, sauberen Fall.
- **Braucht Margin:** `Strike × 100 × Qty` reserviert → testet
  Cash-Secured-Margin.
- **Bezahlt Prämie:** testet OI-Slippage (nach dem A-Fix — echte OI aus
  Snapshot), Commission.
- Wenn CSP über 3 Monate mit ein paar Assignments sauber läuft und die
  `realized_pnl` gegen „Prämie + Assignment-Delta" per Hand stimmt,
  sind `apply_expiries` und `_settle_assignment` validiert — der
  schwierigste Code im Framework.

**Was getestet wird:** Options-Chain-Loading, `chain.find(delta_target,
dte_range)`, OI-Slippage-Tiers, Reg-T-Margin (CSP-Variante), ITM-Put-
Assignment, `on_position_closed`-Callback bei Expiry.

**Abschluss-Kriterium:** Golden-Path-Test „CSP_1_assignment.md" grün.

### 14.9 Phase 4 — Covered Call

Baut auf CSP auf: falls Assignment kam, liegen 100 Shares im Portfolio
— jetzt Short Call drauf. Testet:

- **Multi-Leg** (Stock + Short Call) in *einer* Position.
- **Andere Assignment-Richtung:** ITM Call → Shares gehen raus.
- **Position mit gemischten Leg-Typen** über die ganze Maintenance-
  Pipeline (MTM, Dividend am Ex-Date, DTE-Close nur auf Options-Leg,
  Stock-Leg bleibt).

### 14.10 Phase 5 — Wheel

„CSP → Assignment → CC → Called Away → CSP-Loop" plus State-Machine
via `tags["stage"]`. Wenn Phase 3+4 stabil ist, ist Wheel fast trivial
— nur Transitions. **Real value:** erster mehrjährlich-realistischer
Backtest wird möglich, mit dem sich Strategien tatsächlich bewerten
lassen.

### 14.11 Phase 6 — Vertical Spread

Zwei Optionen simultan, atomare Multi-Leg-Order, Reg-T-Margin =
`Spread-Width × 100 × Qty`. Wenn beim Open eine der zwei Legs
unpriceable ist, muss die *ganze* Order rejected werden (Kap. 7.5) —
das ist der Executor-Test. Erster echter Roll-Kandidat: der
Rolling-Manager (Eric-Ludwig Phase 1 vertikal) kann hier greifen.

### 14.12 Phase 7 — Iron Condor

Vier-Leg-Order. Rechnerisch nur „zwei Vertikale". Wenn Phase 6 sauber
ist, ist Iron Condor ein **Regressionstest**, kein neues Feature.

### 14.13 Phase 8 — Custom Options-Strategien („Theta Bombe" etc.)

Erst hier. Weil dann *das ganze Framework* verifiziert ist und du
weißt: das Ergebnis, das du siehst, ist real, nicht Framework-Bug.
Klassiker als Einstieg:

- Theta Bombe (viele kleine Prämien, sehr kurz DTE)
- Rolling-Manager stress-testen (Eric Ludwig 4 Phasen)
- Iron Condor mit dynamischer Wing-Width je IV-Rank
- CSP-Ladder (mehrere DTEs / Strikes parallel)

### 14.14 Split-Warnung ab Phase 5

Ab Wheel-Backtests werden Zeiträume schnell ≥ 1 Jahr — dann greift
Kap. 10.1 (Splits). Vor Phase 5 eine Warn-Utility bauen: „Symbol X hat
in [start, end] einen Split — Backtest-Ergebnisse unzuverlässig."
Skuld-DB hat die Ratios (aus `StockAssetProfilesYahoo` oder aus dem
Kurssprung-Delta) — die Erkennung reicht als V1.5, echter Fix
(Position-Quantity + Strike adjustieren) bleibt V2.

### 14.15 Reihenfolge auf einen Blick

| # | Phase | Testet zum ersten Mal | Golden Path |
|---|---|---|---|
| 1 | Buy & Hold stabilisieren | Engine-Loop, MTM, Metrics | `B&H_SPY_10_days` |
| 2 | SMA-Crossover | `compute_daily`, Position-Zyklen | `SMA_5_trades` |
| 2b | Stop-Loss auf Stock | Stop-Order-Maschinerie | (in Phase 2 integrierbar) |
| 3 | Cash-Secured Put | Chain, OI-Slippage, Margin, Assignment | `CSP_1_assignment` |
| 4 | Covered Call | Multi-Leg-Position, andere Assignment-Richtung | `CC_1_called_away` |
| 5 | Wheel | State-Machine über Wechsel hinweg | `Wheel_full_cycle` |
| 6 | Vertical Spread | Atomare 2-Leg-Order, Roll-Kandidat | `Spread_1_roll` |
| 7 | Iron Condor | 4-Leg-Order (Regressionstest) | `IC_1_expiry` |
| 8 | Custom Options | freie Bahn | pro Strategie eigener |

### 14.16 Offene Design-Fragen zum Fahrplan

- **SMA vs. RSI als Phase 2:** SMA-Crossover ist trivial per Hand
  nachrechenbar (Golden Path leichter). RSI ist näher an dem, was
  Optionsstrategien sowieso brauchen. Aktuell auf SMA gesetzt — offen
  für Anpassung.
- **CSP vs. CC als erste Options-Phase:** Argument pro CSP → begrifflich
  einfacher (nur Short Put + eventuelles Assignment). Argument pro CC
  → wenn die 100 Aktien schon aus B&H liegen, ist es der natürliche
  nächste Schritt. Aktuell auf CSP gesetzt — Bauchgefühl, keine harte
  Evidenz.
- **Fundamentaldaten-Strategie skippen:** aktuell bewusst weggelassen
  (Kap. 14.7). Falls sich rausstellt, dass dabei doch
  Framework-relevante Ecken sind (z. B. Universe-Rebalance-Trigger auf
  Fundamentaldaten), wieder reinnehmen.
