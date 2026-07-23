# Roll & Screen V2.1 — Screener-Puts + Roller-Performance

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox syntax.

**Goal:** (1) Screener: Klick auf Aktie zeigt zusätzlich verkaufbare Puts (DTE 30–45, verstellbar) mit Prämien-Kennzahlen. (2) Roller: Langsamkeit beheben — nichts lädt beim Tab-Öffnen, erst nach Symbol-Eingabe läuft DB-Arbeit.

**Architecture:** Roller-Symbol zurück auf Freitext-`text_input` + Guard (statt Selectbox mit teurer DISTINCT-Historie-Query). Screener-Detail bekommt eine zweite Sektion, gespeist aus neuer schlanker Symbol-Puts-Query auf `OptionDataMerged`.

**Tech Stack:** Streamlit, pandas, PostgreSQL, pytest.

## Global Constraints

- Branch ausschließlich `feature/roll-and-screen`, nie master.
- DB nicht lokal → nur pure-Python-Funktionen lokal testbar; SQL/UI verifiziert User nach Push.
- Kein Cache auf Kernberechnungen; reine DB-Reads dürfen `@st.cache_data(ttl=300)`.
- Kein DB-Schema-Change.

## File Structure

| Datei | Änderung |
|---|---|
| `db/SQL/query/screener_symbol_puts.sql` | **neu:** verkaufbare Puts eines Symbols, DTE-Fenster, liquide, ohne K-Filter, mit Kennzahlen. |
| `src/put_screener.py` | **klein:** pure-Python `put_metrics(strike, premium, dte)` für Rendite/annualisiert/Gewinnschwelle (testbar). |
| `pages/roll_and_screen.py` | Screener-Detail: Put-Sektion ergänzen. Roller: Symbol-Freitext + Guard, `_load_symbols`/`roll_symbols.sql`-Nutzung entfernen. |
| `tests/test_put_screener.py` | Test für `put_metrics`. |
| `db/SQL/query/roll_symbols.sql` | **löschen** (nicht mehr genutzt nach Roller-Umbau). |

---

## Task 1: `put_metrics()` — Kennzahlen für verkaufbare Puts (pure Python, testbar)

**Files:**
- Modify: `src/put_screener.py`
- Test: `tests/test_put_screener.py`

**Interfaces:**
- Produces: `put_metrics(strike, premium, dte) -> dict` mit `premium_pct`, `annualized_pct`, `breakeven`, `capital_required`. Reine Arithmetik, keine DB.

- [ ] **Step 1: Failing-Test**

```python
# tests/test_put_screener.py (anhängen)
from src.put_screener import put_metrics


def test_put_metrics_basic():
    m = put_metrics(strike=30.0, premium=1.20, dte=40)
    assert round(m["premium_pct"], 2) == 4.0        # 1.20/30*100
    assert round(m["breakeven"], 2) == 28.80        # 30 - 1.20
    assert round(m["capital_required"], 2) == 3000.0  # 30*100
    assert round(m["annualized_pct"], 1) == 36.5     # 4.0 * 365/40


def test_put_metrics_guards_zero():
    m = put_metrics(strike=0.0, premium=1.0, dte=0)
    assert m["premium_pct"] == 0.0
    assert m["annualized_pct"] == 0.0
```

- [ ] **Step 2: Rot verifizieren**

Run: `python -m pytest tests/test_put_screener.py::test_put_metrics_basic -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implementieren**

```python
# src/put_screener.py (anhängen)
def put_metrics(strike: float, premium: float, dte: int) -> dict:
    """Kennzahlen eines verkaufbaren Puts. Reine Arithmetik, keine DB.

    premium_pct     = Prämie / Strike * 100
    annualized_pct  = premium_pct * 365 / dte
    breakeven       = Strike - Prämie
    capital_required= Strike * 100  (Cash-Secured)
    """
    strike = float(strike or 0)
    premium = float(premium or 0)
    dte = int(dte or 0)
    premium_pct = (premium / strike * 100.0) if strike > 0 else 0.0
    annualized_pct = (premium_pct * 365.0 / dte) if dte > 0 else 0.0
    return {
        "premium_pct": premium_pct,
        "annualized_pct": annualized_pct,
        "breakeven": strike - premium,
        "capital_required": strike * 100.0,
    }
```

- [ ] **Step 4: Grün**

Run: `python -m pytest tests/test_put_screener.py -v`
Expected: PASS (alle).

- [ ] **Step 5: Commit**

```bash
git add src/put_screener.py tests/test_put_screener.py
git commit -m "feat(put-screener): put_metrics() für verkaufbare-Puts-Kennzahlen"
```

---

## Task 2: `screener_symbol_puts.sql` — verkaufbare Puts eines Symbols

**Files:**
- Create: `db/SQL/query/screener_symbol_puts.sql`

**Interfaces:**
- Params: `:symbol`, `:dte_min`, `:dte_max`. Liefert put-Zeilen aus `OptionDataMerged`.
- **Nicht lokal testbar.**

- [ ] **Step 1: Query anlegen**

```sql
-- screener_symbol_puts.sql
-- Aktuell verkaufbare PUTS eines Symbols im DTE-Fenster (Screener-Detail).
-- Kein Strike-Filter (anders als roll_candidates.sql) — alle liquiden Puts.
-- Quelle: "OptionDataMerged". Params: :symbol, :dte_min, :dte_max
SELECT
    o.symbol,
    o.strike_price,
    o.expiration_date,
    o.days_to_expiration,
    o.premium_option_price,
    o.open_interest,
    o.day_volume,
    o.greeks_delta,
    o.implied_volatility,
    o.live_stock_price
FROM "OptionDataMerged" o
WHERE o.symbol = :symbol
  AND o.contract_type = 'put'
  AND o.days_to_expiration BETWEEN :dte_min AND :dte_max
  AND o.premium_option_price > 0
  AND o.open_interest > 0
  AND o.day_volume > 0
ORDER BY ABS(o.strike_price - o.live_stock_price) ASC, o.days_to_expiration ASC
```

- [ ] **Step 2: Commit**

```bash
git add db/SQL/query/screener_symbol_puts.sql
git commit -m "feat(put-screener): screener_symbol_puts.sql — verkaufbare Puts je Symbol"
```

---

## Task 3: Screener-Detail — verkaufbare Puts unter der Score-Herleitung

**Files:**
- Modify: `pages/roll_and_screen.py` (`render_screener_tab`, neuer Loader `_load_symbol_puts`)

**Interfaces:**
- Consumes: `screener_symbol_puts.sql`, `put_metrics`.
- **Nicht lokal testbar.**

- [ ] **Step 1: Loader + Import**

Import ergänzen: `from src.put_screener import score_candidates, score_breakdown, put_metrics, DEFAULT_PE_MAX`.

```python
@st.cache_data(ttl=300)
def _load_symbol_puts(symbol, dte_min, dte_max):
    """Aktuell verkaufbare Puts eines Symbols. Reiner DB-Read -> darf cachen."""
    return select_into_dataframe(
        sql_file_path=PATH_DATABASE_QUERY_FOLDER / "screener_symbol_puts.sql",
        params={"symbol": symbol, "dte_min": int(dte_min), "dte_max": int(dte_max)},
    )
```

- [ ] **Step 2: Put-Sektion nach dem Annahmen-Sammelkasten anhängen**

Am Ende von `render_screener_tab` (nach dem `getroffene`-Block) einfügen:

```python
    st.divider()
    st.markdown("### 💰 Verkaufbare Puts — jetzt")
    pc1, pc2 = st.columns([1, 3])
    p_dte_min, p_dte_max = pc1.slider("DTE-Fenster", 7, 90, (30, 45), 1, key="screener_put_dte")
    puts = _load_symbol_puts(row["symbol"], p_dte_min, p_dte_max)
    if puts is None or puts.empty:
        st.info(f"Keine liquiden Puts für {row['symbol']} im DTE-Fenster {p_dte_min}–{p_dte_max}.")
    else:
        put_rows = []
        for _, o in puts.iterrows():
            m = put_metrics(o["strike_price"], o["premium_option_price"], o["days_to_expiration"])
            put_rows.append({
                "Strike": round(float(o["strike_price"]), 2),
                "Expiry": o["expiration_date"],
                "DTE": int(o["days_to_expiration"]),
                "Prämie ($)": round(float(o["premium_option_price"]), 2),
                "Rendite %": round(m["premium_pct"], 2),
                "Annualisiert %": round(m["annualized_pct"], 1),
                "Gewinnschwelle": round(m["breakeven"], 2),
                "Kapital ($)": round(m["capital_required"], 0),
                "Delta": round(float(o["greeks_delta"]), 3) if o["greeks_delta"] is not None else None,
                "OI": int(o["open_interest"]),
                "Vol": int(o["day_volume"]),
            })
        st.dataframe(pd.DataFrame(put_rows), use_container_width=True, hide_index=True)
        st.caption("🔶 Prämie = day_close (Näherung; echter Bid/Ask im Broker prüfen).")
```

- [ ] **Step 3: Push + User-Verifikation**

```bash
git add pages/roll_and_screen.py
git commit -m "feat(put-screener): verkaufbare Puts (DTE 30-45, verstellbar) im Aktien-Detail"
git push origin feature/roll-and-screen
```

Meldung an User: „Screener: Klick auf Aktie zeigt jetzt zusätzlich verkaufbare Puts. Bitte testen."

---

## Task 4: Roller-Performance — Symbol-Freitext, nichts lädt beim Tab-Öffnen

**Files:**
- Modify: `pages/roll_and_screen.py` (`render_roller_tab`, `_load_symbols` entfernen)
- Delete: `db/SQL/query/roll_symbols.sql`

**Interfaces:**
- Roller startet ohne DB-Zugriff; erst Symbol-Eingabe triggert Historie-Query.
- **Nicht lokal testbar.**

- [ ] **Step 1: `_load_symbols` entfernen**

Funktion `_load_symbols` (inkl. `@st.cache_data`) aus `pages/roll_and_screen.py` löschen.

- [ ] **Step 2: Symbol-Eingabe auf Freitext + Guard**

Ersetze den Selectbox-Block in `render_roller_tab`:

```python
    # 1) Symbol (Freitext) + Kontrakte — nichts lädt vor der Eingabe
    col_sym, col_n = st.columns([2, 1])
    symbol = col_sym.text_input("Symbol", value="", placeholder="z.B. AAPL",
                                key="roll_symbol").strip().upper()
    n_contracts = col_n.number_input("Kontrakte (n)", min_value=1, value=1, step=1)

    if not symbol:
        st.info("Symbol eingeben — erst dann werden Historie und Kurse geladen.")
        return
```

(Der `symbols = _load_symbols()`-Block + dessen `if not symbols`-Guard entfällt komplett.)

- [ ] **Step 3: `roll_symbols.sql` löschen**

```bash
git rm db/SQL/query/roll_symbols.sql
```

- [ ] **Step 4: Syntax + Tests + toter-Import-Check**

Run: `python -m py_compile pages/roll_and_screen.py && python -m pytest tests/ -q`
Expected: compile OK, Tests grün. Prüfen dass `_load_symbols` nirgends mehr referenziert.

- [ ] **Step 5: Push + User-Verifikation**

```bash
git add pages/roll_and_screen.py
git commit -m "perf(roll-support): Roller lädt nichts beim Tab-Öffnen — Symbol-Freitext statt DISTINCT-Historie"
git push origin feature/roll-and-screen
```

Meldung an User: „Roller: Symbol wird jetzt getippt, DB-Arbeit erst danach → kein Hängen beim Tab-Öffnen. Bitte testen."

---

## Self-Review

**Coverage:** Screener-Puts (Task 1+2+3), verstellbares DTE 30–45 (Task 3 Slider), beides Score+Puts (Task 3 hängt an bestehende Herleitung an), Roller-Performance via Freitext (Task 4). ✅

**Placeholder:** keine — Code vollständig.

**Typ-Konsistenz:** `put_metrics` liefert `{premium_pct, annualized_pct, breakeven, capital_required}` (Task 1) — in Task 3 exakt so konsumiert. `_load_symbol_puts(symbol, dte_min, dte_max)` Signatur == Aufruf. ✅
