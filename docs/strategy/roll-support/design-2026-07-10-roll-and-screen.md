# Roll & Screen — Design Spec

**Datum:** 2026-07-10
**Ersetzt/erweitert:** `design-2026-06-27.md` (korrigiert die dort vertauschte Roll-Hierarchie)
**Buchgrundlage:** „Optionen unschlagbar handeln" — Kapitel 3 (Rollen), Kapitel 4 (Aktienauswahl), Kapitel 5 (Charttechnik/Timing)
**Plattform:** Streamlit `master`
**Persistenz:** keine — session-only, kein DB-Write, kein Schema-Change
**Caching:** Kern-Berechnungen (Roll-Kalkulation, aktueller Positionswert) werden **nicht** gecacht — immer frisch gerechnet. (Reine DB-Reads dürfen wie üblich `@st.cache_data` nutzen, analog Spread-Page.)

---

## Überblick

Eine neue Streamlit-Seite **„Roll & Screen"** (`pages/roll_and_screen.py`) mit **zwei Tabs**, die den Wheel-Ablauf abbilden:

- **Tab 1 — Screener** („Neuer Einstieg"): Finde qualifizierte Aktien + den passenden Cash-Secured-Put nach der Buch-Checkliste (Kap. 4+5).
- **Tab 2 — Roller** („Rollen"): Historisch eröffneten Put eingeben, aktuellen Gewinn/Verlust ermitteln, 3 Roll-Stufen als Kandidaten anzeigen (Kap. 3).

Beide Tabs sind unabhängig; die Logik liegt in getrennten, testbaren `src/`-Modulen.

---

## Datei-Struktur

```
pages/roll_and_screen.py            ← UI: 2 Tabs (Screener + Roller), Widgets, Tabellen
src/put_screener.py                 ← Screener-Scoring (pure Python, testbar)
src/roll_support_calc.py            ← Roll-Kalkulation 3 Stufen (pure Python, testbar)
db/SQL/query/put_screener.sql       ← StockData ⋈ OptionDataMerged (Aktie + bester Put)
db/SQL/query/roll_put_history.sql   ← historischer Put + heutiger Wert (Muster: get_option_data_at_date)
db/SQL/query/roll_candidates.sql    ← Roll-Kandidaten (OptionDataMerged, DTE 30–90)
tests/test_roll_support_calc.py     ← Unit-Tests der Roll-Formeln (Buch-Zahlenbeispiele) — NICHT auf master
tests/test_put_screener.py          ← Unit-Tests Scoring — NICHT auf master
```

**Registrierung:** Seite muss manuell in `app.py` eingetragen werden (Streamlit-Pages werden dort registriert).

**Tests nicht auf master:** Die beiden Testdateien werden lokal genutzt, aber **nicht** ins master-Repo committet/gepusht (via `.gitignore`-Eintrag oder bewusst aus dem Commit ausgelassen). Sie dienen der Verifikation während der Entwicklung.

**Wiederverwendung aus bestehendem Code:**
- `get_option_data_at_date`, `get_option_date_range`, `get_stock_date_range` (aus `pages/backtesting/spreads_backtesting.py`) — Muster für „Optionswert zu beliebigem Datum".
- `get_expiration_type` (`src/utils/option_utils.py`) — monatlich/wöchentlich-Erkennung.
- `page_display_dataframe`, `render_date_filter`, `select_into_dataframe`, `select_timetravel_into_dataframe`.
- `calc_covered_calls` (`src/covered_call_calculation.py`) — nur für den Endspiel-Verweis, kein eigener CC-Rechner in V1.

---

## Tab 2 — Roller (Kern-Feature, höchste Priorität)

> Priorität laut User: **„Primär will ich rollen. Es muss funktionieren und verständlich sein."** Der Roller ist das Herzstück; der Screener ist gleichwertig spezifiziert, aber der Roller darf nicht durch Screener-Komplexität gefährdet werden.

### Ablauf (backtest-artig, inspiriert von der Spread-Backtest-Page)

1. **Symbol + historisches Einstiegsdatum** wählen (`render_date_filter` gegen `DatesHistory`).
2. Skuld zeigt die zu diesem Datum in der Historie verfügbaren **Puts** (aus `OptionDataMassiveHistory`) → User klickt seinen Put an (Zeilenauswahl wie Spread-Page).
3. **Eröffnungsprämie** wird automatisch aus der DB gelesen (`day_close` am Einstiegsdatum) **als Vorschlag** — und ist per Checkbox **„🛠️ Echte Ausführungskurse (Optional)"** mit dem echten Fill überschreibbar (exakt das Muster aus `spreads_backtesting.py`).
4. **Heutiger Wert** desselben Puts via `get_option_data_at_date(option_osi, symbol, heute)`:
   - Echter Marktpreis aus `OptionDataMassiveHistory` (mit 1-Wochen-Fallback, falls exakter Tag fehlt).
   - Ist „heute" ein Handelstag: live Bid/Ask-Mittelwert via YahooQuery (wie Spread-Page).
5. → **Block „Aktuelle Position"** (siehe unten).
6. → **Block „Roll-Kandidaten"**: alle 3 Stufen gleichzeitig, je eine Tabelle mit Ampel.
7. Greift keine Stufe → **Endspiel-Hinweis** (kein Rechner).

### Block „Aktuelle Position"

| Kennzahl | Formel |
|---|---|
| Aktueller Put-Preis `P_heute` | aus DB/Live (Schritt 4) |
| Gewinn/Verlust % | `(P_eröffnung − P_heute) / P_eröffnung` |
| Gewinn/Verlust absolut | `(P_eröffnung − P_heute) × n × 100` |
| Innerer Wert | `max(0, K − S)` |
| Restzeitwert | `P_heute − innerer Wert` |
| Alte Gewinnschwelle | `K − P_eröffnung` |
| DTE (Rest) | Expiry − heute |

`S` = aktueller Aktienkurs aus DB/Live. `K` = Strike des eingegebenen Puts. `n` = Kontraktanzahl.

### Die 3 Roll-Stufen (korrigierte Buch-Hierarchie)

> **WICHTIG — Korrektur gegenüber dem 27.-Juni-Spec:** Dort waren Stufe 1 und 2 vertauscht. Verbindlich nach Buch (S. 71–73, verifiziert am Originaltext 2026-07-10):

| Stufe | Basispreis | Kontrakte | Laufzeit | Greift-Bedingung |
|---|---|---|---|---|
| **Stufe 1** | **niedriger** (K2 < K) | gleich (n) | 30–60 Tage (max 90) | Netto-Prämie > 0 |
| **Stufe 2** | **gleich** (K2 = K) | gleich (n) | 30–60 Tage | Netto-Prämie > 0 (wenn Stufe 1 keinen tauglichen niedrigeren Strike hat) |
| **Stufe 3** | **niedriger** (K2 < K) | **verdoppelt (2n)** | 30–60 Tage | Netto-Prämie > 0 mit 2 Kontrakten; Kapitalcheck (User) |

**Kernprinzip des Buchs (S. 71):** Oberstes Ziel ist immer, den **Basispreis zu senken** (= Gewinnschwelle runter). Darum ist „niedriger" die erste Wahl; „gleicher Basispreis" ist der Rückfall, wenn niedriger keine positive Netto-Prämie bringt. Nach jedem Roll gilt: prüfen, ob man auf eine **niedrigere Stufe zurück** kann (z.B. Stufe 2 → Stufe 1).

**Anzeige:** Alle 3 Stufen **gleichzeitig** als 3 Tabellen (User-Wunsch: volle Transparenz, keine Kaskade). Jede Zeile ist ein konkreter Roll-Kandidat.

### Roll-Kandidaten — Datenquelle & Filter

- Quelle: `OptionDataMerged` (aktuelle Optionskette), contract_type = put.
- Laufzeit-Filter: `days_to_expiration` zwischen **30 und 90** (Buch: 30–60 idealerweise, bis 90 erlaubt).
- Stufe 1 & 3: Strikes **unter** aktuellem Kurs `S` (bzw. unter K — „niedriger als bisher").
- Stufe 2: Strike **= K** (gleicher Basispreis, alle Expiries im DTE-Fenster).
- Liquiditäts-Vorfilter: `open_interest` und `day_volume` vorhanden/>0.

### Kennzahlen je Roll-Kandidat

| Spalte | Formel |
|---|---|
| Neuer Strike `K2` | DB |
| Neues Expiry / DTE | DB |
| Neue Prämie `P_neu` | DB · `day_close` |
| Schließungskosten alt | `P_heute` (Näherung; echter Bid/Ask im Broker prüfen) |
| **Netto-Prämie** (Stufe 1&2) | `P_neu − P_heute` (pro Aktie); absolut `× n × 100` |
| **Netto-Prämie** (Stufe 3) | `P_neu × 2 − P_heute × n` (pro Aktie: `/ (2×100)` bezogen); absolut `× 100` |
| **Neue Gewinnschwelle** | `K2 − (P_eröffnung − P_heute + P_neu)` (Stufe 3: kumulierte Netto durch 2 Kontrakte) |
| Kapital nötig (Stufe 3) | `K2 × 2 × 100` |
| **Sinnvoll?** | Ampel (siehe unten) |

> Die Netto-Prämien-Definition folgt den Buch-Zahlenbeispielen (Szenario 1–4). Die Buch-Beispiele werden 1:1 zu Unit-Tests (siehe Verifikation).

### Ampel „Sinnvoll?"

| Bedingung | Flag |
|---|---|
| Netto-Prämie > 0 **UND** neue Gewinnschwelle < alte Gewinnschwelle | ✅ |
| Netto-Prämie > 0 **ABER** Gewinnschwelle nicht verbessert | ⚠️ |
| Netto-Prämie ≤ 0 (Roll kostet drauf) | ❌ |

### Endspiel (Schritt 5) — nur Hinweis, kein Rechner (V1)

Wenn in **keiner** der 3 Stufen ein ✅-Kandidat existiert, zeigt Skuld einen klar erklärten Hinweis-Block:

> „Kein sinnvoller Put-Roll gefunden. Nach Buchkonzept folgt jetzt das **Endspiel**: Aktien andienen lassen und Covered Calls schreiben (asymmetrische Technik: 1 Call auf 200 Aktien, Einstiegskurs über CC-Prämien bis zur Gewinnschwelle senken)."

+ Verweis/Link auf den bestehenden **Covered Call Scanner** (`pages/covered_call_scanner.py`).
Kein eigener asymmetrischer CC-Rechner in V1 (bewusster Scope-Schnitt: Roller muss wasserdicht sein). V2-Kandidat.

---

## Tab 1 — Screener (Kap. 4+5)

### Prinzip

Scoring-Matrix (wie `dividend_screener`) über `StockData ⋈ OptionDataMerged`. Ausgabe = **eine Zeile pro qualifizierter Aktie mit dem besten passenden Put** (fertiger Trade-Vorschlag). Ziel laut Buch: kleine, hochwertige Liste (~10 Titel), nicht Hunderte.

### Harte Filter (Aktie fällt raus wenn verletzt)

- **Preis 15–80 $** (`LIVE_STOCK_PRICE`) — Buch-Punkte 7+8, Kapitaleinsatz für 200 Aktien.
- **Liquide Optionen**: `open_interest` und `day_volume` je ≥ 3-stellig (≥100) — Buch-Punkt 9.

### Scoring-Kriterien (Punkte, sortiert nach Gesamt-Score)

| # | Buch-Kriterium | DB-Feld (StockData) | Abbildung |
|---|---|---|---|
| 1 | Umsatzwachstum (10 J.) | `FinData_revenueGrowth` | **Proxy „aktuell"** — nur aktuelle Rate, kein 10-J-Verlauf |
| 2 | Nettoergebnis + EPS steigend | `NetIncome`, `KeyStats_trailingEps`, `Forward_EPS_Growth_Percent` | **Proxy „aktuell"** |
| 3 | Dividende + Payout ≤ 60 % (REIT ≤ 90 %) | `Summary_payoutRatio`, `dividend_growth_years`, `dividend_classification` | **Voll** |
| 4 | Aktienrückkäufe | `RepurchaseOfCapitalStock`, `NetCommonStockIssuance` | **Voll** (kein Muss) |
| 5 | Positive operative + freie Cashflows | `FinData_operatingCashflow`, `FinData_freeCashflow` | **Proxy „aktuell"** — aktueller Wert |
| 6 | KGV moderat (Tech höher erlaubt) | `Summary_trailingPE`, `KeyStats_forwardPE` | **Voll** (Schwelle als Slider, Default z.B. 40; Tech-Sektor Ausnahme) |
| 10 | Strike-Staffelung ≤ 5 % | `OptionDataMerged.strike_price` (aus Abständen) | **Berechenbar** |
| 11 | Wöchentliche Optionen | `get_expiration_type` | **Voll** (nice-to-have) |
| 12 | Nicht hochvolatil | `iv`, `iv_rank`, `iv_percentile`, `historical_volatility_30d` | **Voll** |
| 13 | Kein Cannabis/Nischen-Sektor | `company_sector`, `company_industry` | **Teilweise** (Cannabis filterbar; „Medienpräsenz" nicht messbar) |
| Timing (Kap.5) | RSI nicht überkauft | `RSI_14` | **Voll** |
| Timing (Kap.5) | MACD steigend / Kaufsignal | `MACD_12_26_9`, `MACDh_12_26_9`, `MACDs_12_26_9` | **Voll** |
| Timing (Kap.5) | Nahe Unterstützung / 52W-Tief | `Summary_fiftyTwoWeekLow`, `SMA_200` | **Näherung** (kein echtes Support-Level) |

> **Ehrliche Beschriftung:** Proxy-Kriterien (1, 2, 5) werden in der UI als „(aktuell)" gekennzeichnet, nicht als „10 Jahre". Keine Schein-Genauigkeit.

#### Warum nur „aktuell" — verifizierte Datenlage (2026-07-10)

Faktenlage aus dem Code (`src/yahooquery_financials.py`, `src/yahooquery_scraper.py`):

- Yahoo (`yahooquery.all_financial_data()`, Default `frequency="a"`) liefert nur **~4 Jahresabschlüsse** je Symbol. **10 Jahre gibt Yahoo grundsätzlich nicht her.**
- SKULD ruft `all_financial_data()` ohne `frequency` auf und reduziert das Ergebnis anschließend per `idx = df.groupby('symbol')['asOfDate'].idxmax()` auf **nur den jüngsten** Jahresabschluss. Die übrigen ~3 Jahre werden verworfen.
- `FundamentalDataYahoo` hat PK = `symbol` (keine Zeitachse). `FundamentalDataYahooHistoryDaily` historisiert nur den täglichen Snapshot dieses einen Werts — das ist **kein** Jahresverlauf, sondern nur „wann änderte sich der zuletzt gemeldete Wert".

**Fazit:** Ein echter Mehrjahres-Trend ist mit den aktuell gespeicherten Daten nicht möglich. Als Proxy dienen die aktuellen Wachstumsraten (`FinData_revenueGrowth`, `Forward_EPS_Growth_Percent`, `KeyStats_earningsQuarterlyGrowth`) — Aussage „wächst aktuell / positiv?" statt „seit 10 Jahren durchgehend?".

**Spätere Ausbaustufen (NICHT V1, dokumentiert für Backlog):**
- *4-Jahres-Trend:* Fundamental-Sammlung so umbauen, dass die von Yahoo gelieferten ~4 Jahre behalten werden (neue Tabelle mit Key `symbol + fiscalYear`). Ermöglicht echtes „4 Jahre EPS/Umsatz steigend?". **Berührt DB-Schema → nur mit expliziter User-Freigabe.**
- *10-Jahres-Trend:* Zweitquelle anbinden (z.B. stockanalysis.com / FMP / macrotrends). Eigenes größeres Projekt (Scraper + Tabelle + Pipeline), nicht Teil von „Roll & Screen".

### Options-Auswahl je Aktie (bester Put)

Aus `OptionDataMerged` je qualifizierter Aktie der beste passende Put:
- Strike **am Geld** (nächster Strike zu `live_stock_price`) — Buch bevorzugt Puts am Geld.
- DTE ~30 (Fenster 21–45), **monatlich** (3. Freitag) bevorzugt via `get_expiration_type`.
- Liquideste Option (höchstes OI/Volumen) bei Gleichstand.

Ausgabe-Spalten je Zeile: Symbol, Kurs, Score, Strike, Expiry, DTE, Prämie, Rendite %, annualisiert, Gewinnschwelle (`K − Prämie`), Kapitaleinsatz (`K × 100`).

---

## DB-Machbarkeit — Zusammenfassung

**Voll abbildbar (9):** Payout/Dividende, Buybacks, KGV, Preis 15–80 $, Options-Liquidität (OI/Volumen), Strike-Staffelung, wöchentliche Optionen, IV/Volatilität, Sektor-Ausschluss (Cannabis).

**Nur Näherung (4):**
- Punkte 1/2/5 (Mehrjahres-Trends Umsatz/EPS/Cashflow) → aktuelle Werte als Proxy, ehrlich beschriftet.
- Support-Level (Kap.5) → 52W-Tief + SMA200 als Näherung.
- Geld-/Brief-Spanne (Punkt 9) + „Medienpräsenz" (Punkt 13) → nicht sauber messbar, entfallen bzw. via Sektor genähert.

Kein Feld benötigt einen DB-Schema-Change; alles liegt in `StockData` und `OptionDataMerged`.

---

## Verifikation (Unit-Tests, nicht auf master)

Die Roll-Formeln werden gegen die **Buch-Zahlenbeispiele** getestet (Kap. 3, Szenario 1–4), u.a.:
- Szenario 1: Aktie 28 $, Put K=30 $, Eröffnung 100 $, P_heute 210 $ → Stufe 1 (K2=29 $, P_neu 220 $) → Netto +10 $, neue GS 27,90 $. Ampel ✅.
- Szenario 2/3/4: analog inkl. Stufe 2/3 und Endspiel-Übergang.

Bestehen die Tests, ist die Roll-Logik nachweislich buchkonform.

---

## Explizit NICHT in Scope (V1)

- Asymmetrischer Covered-Call-Endspiel-Rechner (nur Hinweis + Verweis).
- Roll-Ketten-Historie über mehrere Rollen (V1 = ein frischer Put; kumulierte Prämie = nur dieser eine Put).
- Bull Put Spreads (Fall 2 des alten Specs).
- DB-Persistenz / Trade-Journal.
- Echter Bid/Ask je Option in der Historie (Näherung via `day_close`; „heute" via Live-YahooQuery).
- Stop-Loss-/Aufgeben-Schwelle.
- React-Portierung (Streamlit master zuerst).

---

## Offene Punkte

1. `P_heute`/Schließungskosten sind Näherung via `day_close` (Historie) bzw. Live-Bid/Ask (heute) — exakte Broker-Preise prüft der User selbst.
2. KGV-Schwelle: als Slider mit Default umgesetzt (Buch-Zahl im Scan nicht eindeutig lesbar; User: „egal"). Tech-Sektor bekommt höhere Toleranz.
3. Stufe-3-Kapitalcheck: Skuld zeigt „Kapital nötig", Entscheidung liegt beim User.

---
---

# UMSETZUNGS-ANLEITUNG — „Morgen direkt loslegen"

> Dieser Abschnitt ist so geschrieben, dass man ohne erneutes Nachdenken mit dem Bauen beginnen kann. Bau-Reihenfolge ist bewusst: **Roller zuerst** (Kern-Feature, höchste Priorität), Screener danach.

## Vorbereitung (5 Min, einmalig)

1. Arbeitsverzeichnis: `C:\Python\SKULD\Skuld-master`, Branch `master`.
2. **Nicht** auf blank-Canvas-Regeln achten (das ist Streamlit, kein Figma). DB laufen lassen (`docker-compose.local-db.yml` oder Remote je nach Setup).
3. Referenz-Dateien vorher öffnen und danebenlegen:
   - `pages/backtesting/spreads_backtesting.py` — Muster für „Optionswert zu Datum X" (Funktionen `get_option_data_at_date`, `get_option_date_range`, `get_stock_date_range`, `display_spreads_backtesting`).
   - `pages/covered_call_scanner.py` + `pages/dividend_screener_zahltagstrategie.py` — Muster für Screener-Seite (Scoring + `page_display_dataframe`).
   - `db/SQL/query/dividend_screener.sql` — Muster für Fundamental-Scoring-Query gegen `StockData`.
   - `src/utils/option_utils.py::get_expiration_type` — monatlich/wöchentlich.
   - `src/black_scholes.py` — nur falls Fallback nötig (in V1 nicht geplant).

## Bau-Reihenfolge (Schritt für Schritt)

### Schritt 0 — Test-Setup (nicht auf master)
- `.gitignore` ergänzen: `tests/test_roll_support_calc.py` und `tests/test_put_screener.py` eintragen, damit sie **nicht** committet/gepusht werden.
- Grund: User-Wunsch „Unit-Tests nicht auf master". Sie dienen nur der lokalen Verifikation.

### Schritt 1 — `src/roll_support_calc.py` (pure Python, ZUERST + Tests)
Reine Rechenfunktionen, keine DB-Aufrufe, kein Streamlit. Signaturen:

```python
def position_status(K, S, P_eroeffnung, P_heute, n) -> dict:
    # returns pnl_pct, pnl_abs, inner_value, time_value, breakeven_old, ...
    # inner_value = max(0, K - S); time_value = P_heute - inner_value
    # breakeven_old = K - P_eroeffnung

def roll_candidate(stufe, K, K2, P_eroeffnung, P_heute, P_neu, n) -> dict:
    # Stufe 1&2: netto_pro_aktie = P_neu - P_heute
    # Stufe 3:   netto_pro_aktie = (P_neu*2 - P_heute*n) / (2)   # bezogen auf 2 Kontrakte
    # neue_breakeven Stufe1/2 = K2 - (P_eroeffnung - P_heute + P_neu)
    # neue_breakeven Stufe3   = K2 - (kumulierte Netto verteilt auf 2 Kontrakte)
    # kapital_noetig Stufe3   = K2 * 2 * 100
    # ampel = ampel(netto, breakeven_new, breakeven_old)

def ampel(netto, breakeven_new, breakeven_old) -> str:
    # netto > 0 AND breakeven_new < breakeven_old -> "✅"
    # netto > 0 AND breakeven_new >= breakeven_old -> "⚠️"
    # netto <= 0 -> "❌"
```

- **`tests/test_roll_support_calc.py`** parallel schreiben (TDD). Testfälle = Buch-Zahlenbeispiele:
  - Szenario 1 (Aktie 28 $): K=30, P_eröffnung=1.00 (=100$), P_heute=2.10 (=210$), Stufe1 K2=29, P_neu=2.20 → netto=+0.10, neue GS=27.90, Ampel ✅.
  - Szenario 2 (Aktie 27 $): K=30, P_heute=3.10, Stufe2 K2=30, P_neu=4.00 → netto=+0.90, Saldo +190$, neue GS=28.10, ✅.
  - Szenario 3 (Aktie 25 $): Stufe1/2 greifen nicht, Stufe3 K2=27.50, P_neu=2.85, 2 Kontrakte, Prämie 570$ → Saldo +170$, GS 26.65, ✅.
  - Szenario 4: keine Stufe greift → Endspiel-Signal (alle Ampeln ❌ / keine ✅).
- `pytest tests/test_roll_support_calc.py -v` muss grün sein, BEVOR die UI gebaut wird.

### Schritt 2 — SQL-Queries für den Roller
- **`db/SQL/query/roll_put_history.sql`**: liste verfügbare Puts eines Symbols zu einem Einstiegsdatum (aus `OptionDataMassiveHistory`), + `day_close` als Eröffnungsprämie. → Muster: `get_option_data_at_date` in `spreads_backtesting.py` (inkl. 1-Wochen-Fallback + `CURRENT_DATE`-UNION für „heute").
- **`db/SQL/query/roll_candidates.sql`**: aktuelle Put-Kette aus `OptionDataMerged` mit `contract_type='put'`, `days_to_expiration BETWEEN 30 AND 90`, `open_interest`/`day_volume` vorhanden. Params: symbol, K (für Stufe 2 = K), S (für Stufe 1/3 Strikes < S).

### Schritt 3 — `pages/roll_and_screen.py` Tab 2 (Roller-UI)
- Kopiere das Interaktionsmuster aus `display_spreads_backtesting`:
  1. `render_date_filter` → Einstiegsdatum (gegen `DatesHistory`).
  2. Put-Auswahl (DataFrame-Zeilenauswahl).
  3. Checkbox „🛠️ Echte Ausführungskurse (Optional)" → Override von `P_eröffnung` (1:1 wie Spread-Page, Zeilen ~215 ff.).
  4. `get_option_data_at_date(osi, symbol, heute)` → `P_heute` (bei „heute" live Bid/Ask via `YahooQueryScraper`).
  5. Block „Aktuelle Position" (via `position_status`).
  6. 3 Tabellen (Stufe 1/2/3) via `roll_candidate` je Kandidat, Ampel-Spalte.
  7. Wenn keine ✅ in allen Stufen → `st.info(...)` Endspiel-Hinweis + Verweis auf `covered_call_scanner`.
- **Kein `@st.cache_data`** auf `P_heute`-Berechnung und Roll-Kandidaten-Rechnung (User: immer frisch). Reine DB-Reads dürfen cachen.

### Schritt 4 — `src/put_screener.py` + `db/SQL/query/put_screener.sql` (Screener-Logik)
- SQL: `StockData ⋈ OptionDataMerged` — Muster `dividend_screener.sql`. Harte WHERE-Filter: `LIVE_STOCK_PRICE BETWEEN 15 AND 80`, `open_interest >= 100`, `day_volume >= 100`.
- `src/put_screener.py`: Scoring-Funktion (pure Python auf DataFrame), Punkte je Kriterium (Tabelle im Screener-Abschnitt oben). Proxy-Kriterien als „(aktuell)" beschriften.
- Bester Put je Aktie: Strike nächst-am-Geld, DTE ~30 (21–45), monatlich (`get_expiration_type`), höchstes OI bei Gleichstand.
- **`tests/test_put_screener.py`**: Scoring mit Beispiel-DataFrame prüfen (nicht auf master).

### Schritt 5 — `pages/roll_and_screen.py` Tab 1 (Screener-UI)
- `st.tabs(["📈 Screener (Neuer Einstieg)", "🔄 Roller (Rollen)"])`.
- Ausgabe via `page_display_dataframe` (bestehendes Helper). Spalten: Symbol, Kurs, Score, Strike, Expiry, DTE, Prämie, Rendite%, annualisiert, Gewinnschwelle, Kapitaleinsatz.
- Filter-Slider in Sidebar: KGV-Max (Default 40), Min-Score, IV-Rank-Max.

### Schritt 6 — Registrierung + Smoke-Test
- Seite in `app.py` registrieren (Streamlit-Page-Liste — nachschauen wie die anderen Seiten dort stehen).
- App starten, beide Tabs manuell durchklicken. Screenshot/Sicht prüfen: Roller mit echtem Symbol (z.B. AAPL) + historischem Datum, Screener liefert Liste.
- **Deploy-Regel beachten:** „GitHub Actions success ≠ App up" — nach Push extern den Streamlit-Endpoint prüfen, bevor „fertig".

## Definition of Done (V1)
- [ ] `pytest tests/test_roll_support_calc.py` grün (Buch-Szenarien 1–3 ✅, Szenario 4 = Endspiel-Signal).
- [ ] Roller: historischer Put wählbar, P&L korrekt, 3 Stufen-Tabellen mit Ampel, Endspiel-Hinweis wenn keine ✅.
- [ ] Override „Echte Ausführungskurse" funktioniert.
- [ ] Screener: harte Filter (15–80$, OI/Vol ≥100) + Scoring, eine Zeile = Aktie + bester Put.
- [ ] Seite in `app.py` registriert, beide Tabs laufen lokal.
- [ ] Tests **nicht** im master-Commit (`.gitignore` gesetzt).
- [ ] Kein DB-Schema-Change, kein Cache auf Kernberechnungen.

## Wichtige Fallstricke (aus SKULD-Erfahrung)
- **OptionDataMerged Spaltennamen exakt:** `live_stock_price` (lowercase), `day_close` (=Prämie), `days_to_expiration`, `greeks_delta`, `open_interest`, `day_volume`. KEIN `bid`/`ask` je Option in der View.
- **Claude-Button-Falle:** falls „Claude-Prompt"-Button ergänzt wird → Detail-Panel-Copy, API-ImportError, doppelte DataTable-Keys beachten.
- **Streamlit-Pages** müssen manuell in `app.py` registriert werden — sonst erscheinen sie nicht.
- **Roll-Hierarchie NICHT verwechseln:** Stufe 1 = niedrigerer Strike, Stufe 2 = gleicher Strike, Stufe 3 = niedriger + 2 Kontrakte. (Das alte 27.-Juni-Spec hatte es falsch.)
