# Time Flies Screener — Spezifikation

## 1. Strategie-Übersicht

Die "Time Flies"-Strategie (Simon Black) ist eine **delta-neutrale, theta-positive** Kombination aus zwei Strukturen:

### Struktur A: Put Diagonal (Calendar Spread)
| Leg | Typ | DTE | Position |
|-----|-----|-----|----------|
| Short Put | Put | 7–9 DTE | Sell |
| Long Put | Put | 14–19 DTE | Buy |

- **Gleicher Strike** für beide Legs
- Strike: 2–3% unter aktuellem Kurs (VIX-abhängig)
- Profitiert von **Zeitwertverfall** des Short Puts (schnellerer Decay)

### Struktur B: Call Broken Wing Butterfly (BWB)
| Leg | Typ | Strike | Position | Menge |
|-----|-----|--------|----------|-------|
| Long Call | Call | Lower | Buy | 1x |
| Short Call | Call | Middle | Sell | 2x |
| Long Call | Call | Upper (weiter OTM) | Buy | 1x |

- **Gleiche Expiration** wie der Short Put (7–9 DTE)
- "Broken Wing" = oberer Long Call ist weiter entfernt als der untere
- Profitiert von **Volatilitäts-Kontraktion** (Markt steigt ruhig)

### Zusammenspiel
- Put Diagonal: Schutz bei Vola-Expansion (Markt fällt / wird volatil)
- Call BWB: Profit bei Vola-Kontraktion (Markt steigt / wird ruhiger)
- Kombination ist **delta-neutral** und profitiert in beiden Szenarien

---

## 2. Screening-Parameter

### 2.1 Einstiegsbedingungen

| Parameter | Wert | Quelle |
|-----------|------|--------|
| VIX-Level | 14–25 (ideal: 16–22) | Extern / VIX-Daten |
| Underlying | ETFs: IWM, SPY, QQQ | `OptionDataMassive.symbol` |
| Short Put DTE | 7–9 Tage | `expiration_date - CURRENT_DATE` |
| Long Put DTE | 14–19 Tage | `expiration_date - CURRENT_DATE` |
| BWB Expiration | = Short Put Expiration | Gleiche Expiration |
| Strike-Distanz (Puts) | 2–3% unter Spot (VIX < 18: 2%, VIX > 20: 3%) | Berechnet |
| Short Put Delta | -0.15 bis -0.25 | `greeks_delta` |
| Long Put Delta | -0.20 bis -0.35 | `greeks_delta` |

### 2.2 VIX-basierte Strike-Distanz

```
VIX < 16:  1.5% unter Spot (niedrige Vola → engere Strikes)
VIX 16-20: 2.0% unter Spot
VIX 20-25: 2.5% unter Spot  
VIX > 25:  3.0% unter Spot (hohe Vola → weitere Strikes)
```

### 2.3 BWB-Parameter

| Parameter | Wert |
|-----------|------|
| Lower Long Call Delta | 0.30–0.40 |
| Short Call (Middle) Delta | 0.15–0.25 |
| Upper Long Call Delta | 0.05–0.12 |
| Wing-Breite unten | 2–4 Strikes |
| Wing-Breite oben | 3–6 Strikes (asymmetrisch, weiter OTM) |

---

## 3. Daten-Anforderungen

### 3.1 Verfügbar (bestätigt via DB-Query)

| Feld | Tabelle/View | Status |
|------|-------------|--------|
| symbol | OptionDataMassive | ✅ |
| strike_price | OptionDataMassive | ✅ |
| expiration_date | OptionDataMassive | ✅ |
| contract_type (put/call) | OptionDataMassive | ✅ |
| day_close (Optionspreis) | OptionDataMassive | ✅ |
| greeks_delta | OptionDataMassive | ✅ |
| greeks_theta | OptionDataMassive | ✅ |
| greeks_vega | OptionDataMassive | ✅ |
| implied_volatility | OptionDataMassive | ✅ |
| open_interest | OptionDataMassive | ✅ |
| day_volume | OptionDataMassive | ✅ |
| live_stock_price | OptionDataMassive | ✅ |

### 3.2 Nicht verfügbar

| Feld | Impact | Workaround |
|------|--------|-----------|
| Bid/Ask Spread | Kein realer Einstiegspreis | `day_close` als Proxy (Midpoint-Annahme) |
| VIX Realtime | Strike-Distanz-Berechnung | VIX als User-Input oder externes API |
| Intraday-Preise | Nur EOD + 30min delayed | Akzeptable Einschränkung für Screening |

### 3.3 Daten-Refresh
- Alle 30 Minuten während Market Hours (via Massive API Cron)
- Ausreichend für Screening (kein High-Frequency-Ansatz)

---

## 4. Scoring-Algorithmus

### 4.1 Kandidat = komplette 5-Leg-Struktur

Ein valider Kandidat besteht aus:
1. Short Put (7–9 DTE, Ziel-Delta)
2. Long Put (14–19 DTE, gleicher Strike)
3. Long Call lower (BWB)
4. 2x Short Call middle (BWB)
5. Long Call upper (BWB)

### 4.2 Bewertungskriterien (gewichtet)

| Kriterium | Gewicht | Berechnung |
|-----------|---------|------------|
| **Theta-Ratio** | 30% | `short_theta / long_theta` — je höher, desto besser |
| **IV Term Structure** | 25% | `IV_front / IV_back` — ideal > 1.0 (Contango) |
| **Net Credit/Debit** | 20% | Gesamtkosten der Struktur (idealerweise nahe 0 oder leichter Credit) |
| **Delta-Neutralität** | 15% | `abs(sum(all_deltas))` — je näher an 0, desto besser |
| **Liquidität** | 10% | `min(OI_all_legs)` — Minimum Open Interest über alle Legs |

### 4.3 Score-Formel

```python
score = (
    0.30 * normalize(theta_ratio, min=1.0, max=3.0) +
    0.25 * normalize(iv_term_structure, min=0.8, max=1.5) +
    0.20 * normalize(net_credit, min=-2.0, max=2.0) +
    0.15 * (1.0 - normalize(abs(net_delta), min=0, max=0.3)) +
    0.10 * normalize(min_oi, min=100, max=5000)
)
```

### 4.4 Filter (Hard Constraints)

- Alle Legs müssen `open_interest >= 50` haben
- `abs(net_delta) < 0.15` (sonst zu direktional)
- Long Put muss mindestens 5 DTE mehr haben als Short Put
- BWB muss netto ≤ $0.50 Debit sein (sonst zu teuer)
- Earnings-Warnung: Kein Einstieg wenn Earnings innerhalb der Long-Put-Laufzeit

---

## 5. Architektur

### 5.1 Dateien (zu erstellen)

```
db/SQL/query/time_flies_input.sql          — SQL: Put-Paare + BWB-Candidates
src/time_flies_calculation.py              — Python: Scoring, Ranking, Filterung
api/routers/time_flies.py                  — FastAPI: GET /api/time-flies
frontend: src/pages/TimeFlies.tsx          — React: Screener-UI
```

### 5.2 SQL-Query (`time_flies_input.sql`)

**Ansatz:** Zwei CTEs

```sql
-- CTE 1: Put Diagonal Pairs
-- Finde Short Puts (7-9 DTE) und matche mit Long Puts (14-19 DTE) am gleichen Strike
WITH put_pairs AS (
    SELECT 
        sp.symbol,
        sp.strike_price,
        sp.expiration_date AS short_exp,
        lp.expiration_date AS long_exp,
        sp.day_close AS short_premium,
        lp.day_close AS long_premium,
        sp.greeks_delta AS short_delta,
        lp.greeks_delta AS long_delta,
        sp.greeks_theta AS short_theta,
        lp.greeks_theta AS long_theta,
        sp.implied_volatility AS short_iv,
        lp.implied_volatility AS long_iv,
        sp.open_interest AS short_oi,
        lp.open_interest AS long_oi,
        sp.live_stock_price
    FROM "OptionDataMassive" sp
    JOIN "OptionDataMassive" lp 
        ON sp.symbol = lp.symbol 
        AND sp.strike_price = lp.strike_price
        AND sp.contract_type = lp.contract_type
    WHERE sp.contract_type = 'put'
        AND (sp.expiration_date - CURRENT_DATE) BETWEEN 7 AND 9
        AND (lp.expiration_date - CURRENT_DATE) BETWEEN 14 AND 19
        AND sp.greeks_delta BETWEEN -0.30 AND -0.12
        AND sp.open_interest >= 50
        AND lp.open_interest >= 50
),

-- CTE 2: BWB Call Candidates (gleiche Expiration wie Short Put)
bwb_calls AS (
    SELECT 
        symbol, expiration_date, strike_price,
        day_close, greeks_delta, greeks_theta, 
        implied_volatility, open_interest
    FROM "OptionDataMassive"
    WHERE contract_type = 'call'
        AND (expiration_date - CURRENT_DATE) BETWEEN 7 AND 9
        AND greeks_delta BETWEEN 0.05 AND 0.45
        AND open_interest >= 50
)
SELECT * FROM put_pairs
-- BWB-Konstruktion erfolgt in Python (zu viele Kombinationen für reines SQL)
```

### 5.3 Python-Modul (`time_flies_calculation.py`)

```python
# Hauptfunktionen:
def find_bwb_combinations(calls_df, short_exp, stock_price) -> List[BWBCandidate]
def score_time_flies(put_pair, bwb) -> float
def calc_time_flies(df_puts, df_calls, vix_level, risk_free_rate) -> pd.DataFrame
def get_page_time_flies(df) -> pd.DataFrame  # Column-Auswahl für Frontend
```

**Legs-Konstruktion** (nutzt existierenden `OptionLeg` Dataclass):
```python
legs = [
    OptionLeg(strike=put_strike, premium=short_put_premium, is_call=False, is_long=False, ...),  # Short Put
    OptionLeg(strike=put_strike, premium=long_put_premium, is_call=False, is_long=True, ...),   # Long Put  
    OptionLeg(strike=bwb_lower, premium=lower_call_premium, is_call=True, is_long=True, ...),   # BWB Lower
    OptionLeg(strike=bwb_middle, premium=middle_call_premium, is_call=True, is_long=False, ...), # BWB Short (2x)
    OptionLeg(strike=bwb_upper, premium=upper_call_premium, is_call=True, is_long=True, ...),   # BWB Upper
]
# Note: BWB middle is 2 contracts → premium * 2 in calculation
```

### 5.4 API-Endpoint (`api/routers/time_flies.py`)

```python
@router.get("/")
async def get_time_flies(
    symbols: str = "IWM,SPY,QQQ",
    vix_level: float = 18.0,          # User-Input oder default
    min_score: float = 0.5,
    risk_free_rate: float = 0.043,
    current_user: dict = Depends(get_current_user)
):
    # 1. Query put_pairs + bwb_calls
    # 2. calc_time_flies()
    # 3. Filter by min_score
    # 4. Return top candidates
```

### 5.5 React Frontend

- Tabelle mit Kandidaten (sortiert nach Score)
- Filter: Symbol, Min Score, VIX Override
- Detail-Panel: Alle 5 Legs, P&L-Diagramm, Greeks-Zusammenfassung
- OptionStrat-Link für visuelle Validierung

---

## 6. Wiederverwendbare Komponenten

| Komponente | Datei | Funktion |
|-----------|-------|----------|
| OptionLeg Dataclass | `src/options_utils.py:14` | Leg-Definition |
| calculate_strategy_metrics() | `src/options_utils.py:113` | Max Profit/Loss, BPR, EV, Theta |
| Monte Carlo EV | `src/monte_carlo_simulation.py` | Expected Value Berechnung |
| query_sql_file() | `src/database.py` | SQL-File laden + ausführen |
| df_to_json_safe() | `api/utils.py` | DataFrame → JSON Response |
| Cache | `api/cache.py` | TTL-basierter Response-Cache |
| Earnings-Warning | `src/options_utils.py` | Earnings-Proximity-Check |

---

## 7. Exit-Regeln (für spätere Implementierung)

| Regel | Bedingung |
|-------|-----------|
| Profit Target | +10% des eingesetzten Kapitals |
| Max Loss | -30% bis -40% |
| Time Exit | 24h vor Expiration des Short Legs zwingend schließen |
| Roll-Möglichkeit | Short Put in nächste Woche rollen (wenn Struktur intakt) |

> **Note:** Exit-Management ist NICHT Teil des Screeners (Phase 1).
> Wird als separates Feature in Phase 2 implementiert.

---

## 8. Einschränkungen & Annahmen

1. **Keine Bid/Ask-Daten** → `day_close` als Midpoint-Proxy. Reale Fills können abweichen.
2. **30-Min Refresh** → Screening zeigt Kandidaten, kein Echtzeit-Execution-Signal.
3. **Kein VIX-Feed** → VIX als manueller Input-Parameter (Default: 18).
4. **5 Legs = 5 Contracts** → Höhere Kommissionen berücksichtigen (5 × $2 = $10 roundtrip).
5. **BWB ist 1-1-2-1 Struktur** → Mitte wird 2x gehandelt, BPR-Berechnung entsprechend.
6. **Nur ETFs** → Aktien theoretisch möglich, aber höheres Einzelrisiko. Start mit IWM/SPY/QQQ.

---

## 9. Implementierungs-Reihenfolge

1. **SQL-Query** — Put-Paare und Call-Candidates aus OptionDataMassive
2. **Python Scoring** — BWB-Konstruktion + Scoring-Algorithmus
3. **API Endpoint** — GET /api/time-flies mit Parametern
4. **React Page** — Tabelle + Detail-Panel
5. **Testing** — Gegen Live-Daten (IWM bestätigt: 49 Puts bei 8 DTE, 72 bei 19 DTE)

---

## 10. Offene Punkte

- [ ] VIX-Datenquelle klären (externer API-Call oder manuelle Eingabe?)
- [ ] Soll der Screener auch einzelne Legs (nur Put Diagonal, nur BWB) anzeigen?
- [ ] Minimum-Underlying-Preis für sinnvolle Strikes? (IWM ~$208 → $4-6 Strikes)
- [ ] Soll Monte Carlo EV pro Kandidat berechnet werden? (Performance-Impact bei vielen Kombinationen)
