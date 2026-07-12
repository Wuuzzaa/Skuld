# Roll & Screen V2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Screener-UX aufwerten (Filter oben, Klick→Score-Herleitung, Annahmen sichtbar) und den Roller zum vollen Time-Travel-Backtest umbauen (Vergangenheits-Einstand → heutiger Wert → Roll-Kandidaten).

**Architecture:** Rechenlogik (pure Python, lokal unit-getestet) strikt getrennt von der DB/Streamlit-Naht (nur nach Push auf der DB-Maschine verifizierbar). Bestehende buchverifizierte Kerne (`position_status`, `roll_candidate`, `ampel`, `score_candidates`) bleiben — es werden nur transparenz-liefernde Funktionen (`score_breakdown`, `roll_candidate_explained`) ergänzt und die UI umgebaut.

**Tech Stack:** Python 3, Streamlit, pandas, PostgreSQL (SQL-Dateien unter `db/SQL/query/`), pytest.

## Global Constraints

- **Branch:** ausschließlich `feature/roll-and-screen`. NIE nach `master` mergen/pushen — weder Code noch Tests.
- **DB nicht lokal:** Nur pure-Python-Funktionen (ohne DB/Streamlit) sind hier testbar. SQL/UI werden nach Push vom User auf der DB-Maschine verifiziert.
- **Tests kommen mit auf den Feature-Branch** (User braucht sie drüben).
- **Kein DB-Schema-Change.** Keine neue Persistenz (session-only).
- **Kein Cache auf Kernberechnungen** (`position_status`, `roll_candidate`, heutiger Put-Preis). Reine DB-Reads dürfen `@st.cache_data(ttl=300)`.
- **Kein Live-YahooQuery** für den heutigen Put-Wert — letzter DB-`day_close` (1-Wochen-Fenster).
- **Seite ist in `app.py` bereits registriert** (Zeile 42) — keine Registrierung nötig.
- **Buch-Netto-Formel (verbindlich):** `netto_abs = P_eroeffnung + n*P_neu - P_heute`; `breakeven_new = K2 - netto_abs/(n*100)`. Alle Prämien absolut in $/Kontrakt.
- **Annahmen-Marker:** einheitlich `🔶` + Tooltip; Werte: „(aktuell)", „(Näherung)", „(day_close)".

---

## File Structure

| Datei | Verantwortung |
|---|---|
| `src/put_screener.py` | Scoring-Kern; **neu:** `score_breakdown()` liefert pro Kriterium erreicht/möglich/ist-wert/annahme. |
| `src/roll_support_calc.py` | Roll-Rechenkern; **neu:** `roll_candidate_explained()` liefert Herleitungs-Zwischenschritte. |
| `db/SQL/query/roll_put_history.sql` | **erweitert:** `dte_min`/`dte_max`-Filter (DTE-Bereich am Einstiegsdatum). |
| `db/SQL/query/roll_symbols.sql` | **neu:** DISTINCT-Symbolliste für Selectbox. |
| `db/SQL/query/roll_candidates.sql` | unverändert. |
| `db/SQL/query/put_screener.sql` | unverändert (liefert schon alle Ist-Werte). |
| `pages/roll_and_screen.py` | UI-Umbau: Screener (Filter oben, Detail-Panel), Roller (Symbol-Selectbox, DTE-Range, letzter-day_close, Status-Banner, Kandidaten-Detail). |
| `tests/test_put_screener.py` | **neu:** `score_breakdown` + `score_candidates`. |
| `tests/test_roll_support_calc.py` | **neu:** Buch-Szenarien + `roll_candidate_explained`. |

---

## Task 1: Roll-Rechenkern-Tests (Buch-Szenarien) absichern

**Files:**
- Test: `tests/test_roll_support_calc.py` (Create)

**Interfaces:**
- Consumes: `src/roll_support_calc.py::position_status(K, S, P_eroeffnung, P_heute, n) -> dict`, `roll_candidate(stufe, K, K2, P_eroeffnung, P_heute, P_neu, n) -> dict`, `ampel(netto, breakeven_new, breakeven_old) -> str`.
- Produces: grüne Baseline-Tests, die die bestehende buchverifizierte Logik einfrieren, bevor irgendwas geändert wird.

- [ ] **Step 1: Failing-Test schreiben**

```python
# tests/test_roll_support_calc.py
"""Buch-verifizierte Roll-Formeln — Szenarien aus 'Optionen unschlagbar handeln', Kap. 3."""
from src.roll_support_calc import position_status, roll_candidate, ampel


def test_ampel_gruen_wenn_netto_positiv_und_gs_gesenkt():
    assert ampel(netto=10.0, breakeven_new=27.90, breakeven_old=29.00) == "✅"


def test_ampel_gelb_wenn_netto_positiv_aber_gs_nicht_besser():
    assert ampel(netto=10.0, breakeven_new=29.50, breakeven_old=29.00) == "⚠️"


def test_ampel_rot_wenn_netto_nicht_positiv():
    assert ampel(netto=-5.0, breakeven_new=27.0, breakeven_old=29.0) == "❌"


def test_position_status_verlust():
    # Put mit K=30 eröffnet für 100$, heute 210$ wert -> Verlust.
    pos = position_status(K=30.0, S=28.0, P_eroeffnung=100.0, P_heute=210.0, n=1)
    assert round(pos["breakeven_old"], 2) == 29.00      # 30 - 100/100
    assert round(pos["pnl_abs"], 2) == -110.00          # (100 - 210) * 1
    assert round(pos["inner_value"], 2) == 200.00       # max(0, 30-28)*100
    assert round(pos["time_value"], 2) == 10.00         # 210 - 200


def test_roll_candidate_szenario1_stufe1_gruen():
    # Buch-Szenario 1: K=30, Eröffnung 100$, heute 210$, Stufe1 K2=29, P_neu=220$.
    r = roll_candidate(stufe=1, K=30.0, K2=29.0,
                       P_eroeffnung=100.0, P_heute=210.0, P_neu=220.0, n=1)
    assert round(r["netto_abs"], 2) == 110.00           # 100 + 1*220 - 210
    assert round(r["breakeven_new"], 2) == 27.90        # 29 - 110/100
    assert r["ampel"] == "✅"


def test_roll_candidate_szenario3_stufe3_zwei_kontrakte():
    # Buch-Szenario 3: Stufe3 K2=27.50, P_neu=285$, 2 Kontrakte, Eröffnung 100$, heute 400$.
    r = roll_candidate(stufe=3, K=30.0, K2=27.50,
                       P_eroeffnung=100.0, P_heute=400.0, P_neu=285.0, n=2)
    assert round(r["netto_abs"], 2) == 170.00           # 100 + 2*285 - 400
    assert round(r["kapital_noetig"], 2) == 5500.00     # 27.50 * 2 * 100
    assert r["ampel"] == "✅"
```

- [ ] **Step 2: Tests laufen lassen (müssen grün sein — Logik existiert schon)**

Run: `pytest tests/test_roll_support_calc.py -v`
Expected: PASS (6 Tests). Falls ein Test rot ist → die bestehende Formel weicht ab; dann Testwert am Code-Docstring (`roll_support_calc.py` Z. 13–22) verifizieren und korrigieren, NICHT den Produktivcode.

- [ ] **Step 3: Commit**

```bash
git add tests/test_roll_support_calc.py
git commit -m "test(roll-support): Buch-Szenario-Tests für Roll-Rechenkern (Baseline)"
```

---

## Task 2: `roll_candidate_explained()` — Herleitung für Kandidaten-Detail

**Files:**
- Modify: `src/roll_support_calc.py` (Funktion ergänzen)
- Test: `tests/test_roll_support_calc.py` (Test ergänzen)

**Interfaces:**
- Consumes: bestehende `roll_candidate(...)`.
- Produces: `roll_candidate_explained(stufe, K, K2, P_eroeffnung, P_heute, P_neu, n) -> dict` — gibt zusätzlich zum `roll_candidate`-Ergebnis eine `steps`-Liste von `{label, formel, wert}` (Klartext-Herleitung für die UI). Verändert die Zahlen NICHT.

- [ ] **Step 1: Failing-Test schreiben**

```python
# tests/test_roll_support_calc.py  (anhängen)
from src.roll_support_calc import roll_candidate_explained


def test_roll_candidate_explained_liefert_herleitung():
    exp = roll_candidate_explained(stufe=1, K=30.0, K2=29.0,
                                   P_eroeffnung=100.0, P_heute=210.0, P_neu=220.0, n=1)
    # Kernzahlen identisch zu roll_candidate:
    assert round(exp["netto_abs"], 2) == 110.00
    assert round(exp["breakeven_new"], 2) == 27.90
    assert exp["ampel"] == "✅"
    # Herleitung vorhanden und nachvollziehbar:
    labels = [s["label"] for s in exp["steps"]]
    assert "Netto-Prämie" in labels
    assert "Neue Gewinnschwelle" in labels
    netto_step = next(s for s in exp["steps"] if s["label"] == "Netto-Prämie")
    assert "100" in netto_step["formel"] and "220" in netto_step["formel"] and "210" in netto_step["formel"]
    assert round(netto_step["wert"], 2) == 110.00
```

- [ ] **Step 2: Test läuft rot**

Run: `pytest tests/test_roll_support_calc.py::test_roll_candidate_explained_liefert_herleitung -v`
Expected: FAIL — `ImportError: cannot import name 'roll_candidate_explained'`.

- [ ] **Step 3: Funktion implementieren**

```python
# src/roll_support_calc.py  (am Ende anhängen)
def roll_candidate_explained(stufe: int, K: float, K2: float, P_eroeffnung: float,
                             P_heute: float, P_neu: float, n: int) -> dict:
    """Wie roll_candidate(), plus 'steps': Klartext-Herleitung für die UI.

    Verändert keine Zahlen — reine Zusatz-Transparenz (Formel + eingesetzte Werte).
    """
    base = roll_candidate(stufe=stufe, K=K, K2=K2, P_eroeffnung=P_eroeffnung,
                          P_heute=P_heute, P_neu=P_neu, n=n)
    steps = [
        {
            "label": "Netto-Prämie",
            "formel": f"Eröffnung {P_eroeffnung:.0f} + {n}×{P_neu:.0f} (neu) − {P_heute:.0f} (Rückkauf)",
            "wert": base["netto_abs"],
        },
        {
            "label": "Neue Gewinnschwelle",
            "formel": f"K2 {K2:.2f} − Netto {base['netto_abs']:.0f} / ({n}×100)",
            "wert": base["breakeven_new"],
        },
        {
            "label": "Alte Gewinnschwelle",
            "formel": f"K {K:.2f} − Eröffnung {P_eroeffnung:.0f} / 100",
            "wert": base["breakeven_old"],
        },
        {
            "label": "Kapital nötig",
            "formel": f"K2 {K2:.2f} × {n} × 100",
            "wert": base["kapital_noetig"],
        },
    ]
    return {**base, "steps": steps}
```

- [ ] **Step 4: Test läuft grün**

Run: `pytest tests/test_roll_support_calc.py -v`
Expected: PASS (7 Tests).

- [ ] **Step 5: Commit**

```bash
git add src/roll_support_calc.py tests/test_roll_support_calc.py
git commit -m "feat(roll-support): roll_candidate_explained() für Kandidaten-Herleitung"
```

---

## Task 3: `score_breakdown()` — Score-Herleitung je Kriterium

**Files:**
- Modify: `src/put_screener.py` (Funktion ergänzen, `_CRITERIA` um Ist-Wert-Extraktor + Annahme-Label erweitern)
- Test: `tests/test_put_screener.py` (Create)

**Interfaces:**
- Consumes: bestehende `_CRITERIA`, `score_candidates`, `criterion_labels`.
- Produces: `score_breakdown(row: pd.Series | dict, pe_max: float = DEFAULT_PE_MAX) -> list[dict]` — pro Kriterium `{key, label, erreicht: bool, moeglich: int, ist_wert, annahme: str}`. `annahme` ∈ {"", "aktuell", "Näherung", "day_close"}. Summe der `erreicht` == `score` aus `score_candidates`.

- [ ] **Step 1: Failing-Test schreiben**

```python
# tests/test_put_screener.py
"""Scoring-Kern des CSP-Screeners — pure Python, keine DB."""
import pandas as pd
from src.put_screener import score_candidates, score_breakdown, SCORE_MAX


def _sample_row():
    # Eine Aktie, die die meisten Kriterien erfüllt.
    return {
        "symbol": "TEST",
        "revenue_growth_pct": 8.3,     # > 0 -> erfüllt (aktuell)
        "eps_growth_pct": 5.0,         # > 0 -> erfüllt (aktuell)
        "payout_ratio_pct": 40.0,      # <= 60 -> erfüllt
        "operating_cashflow": 1000.0,  # > 0
        "free_cashflow": 500.0,        # > 0 -> Cashflow erfüllt (aktuell)
        "trailing_pe": 25.0,           # <= 40 -> erfüllt
        "iv_rank": 30.0,               # <= 60 -> erfüllt
        "rsi_14": 58.0,                # < 70 -> erfüllt
        "macd_histogram": 0.2,         # > 0 -> erfüllt
        "sector": "Technology",        # kein Cannabis -> erfüllt
    }


def test_score_breakdown_alle_kriterien_erfuellt():
    bd = score_breakdown(_sample_row(), pe_max=40.0)
    assert len(bd) == SCORE_MAX
    assert all(item["erreicht"] for item in bd)
    assert all(item["moeglich"] == 1 for item in bd)


def test_score_breakdown_kgv_zu_hoch_faellt_raus():
    row = _sample_row()
    row["trailing_pe"] = 80.0  # > 40
    bd = score_breakdown(row, pe_max=40.0)
    pe = next(i for i in bd if i["key"] == "crit_pe")
    assert pe["erreicht"] is False
    assert pe["ist_wert"] == 80.0


def test_score_breakdown_markiert_annahme_aktuell():
    bd = score_breakdown(_sample_row(), pe_max=40.0)
    rev = next(i for i in bd if i["key"] == "crit_revenue_growth")
    assert rev["annahme"] == "aktuell"
    pe = next(i for i in bd if i["key"] == "crit_pe")
    assert pe["annahme"] == ""  # KGV ist keine Näherung


def test_breakdown_summe_gleich_score():
    df = pd.DataFrame([_sample_row()])
    scored = score_candidates(df, pe_max=40.0)
    score = int(scored.iloc[0]["score"])
    bd = score_breakdown(_sample_row(), pe_max=40.0)
    assert sum(1 for i in bd if i["erreicht"]) == score
```

- [ ] **Step 2: Test läuft rot**

Run: `pytest tests/test_put_screener.py -v`
Expected: FAIL — `ImportError: cannot import name 'score_breakdown'`.

- [ ] **Step 3: `_CRITERIA` erweitern + `score_breakdown` implementieren**

`_CRITERIA` bekommt zwei zusätzliche Felder pro Eintrag: den Ist-Wert-Extraktor und das Annahme-Label. Ersetze den bestehenden `_CRITERIA`-Block und ergänze `score_breakdown`:

```python
# src/put_screener.py — _CRITERIA ersetzen durch 5-Tupel (col, label, fn, ist_wert_key, annahme)
_CRITERIA = [
    ("crit_revenue_growth", "Umsatzwachstum (aktuell)",     lambda r, pe: _is_pos(r.get("revenue_growth_pct")),                                   "revenue_growth_pct", "aktuell"),
    ("crit_eps_growth",     "EPS-Wachstum (aktuell)",        lambda r, pe: _is_pos(r.get("eps_growth_pct")),                                       "eps_growth_pct",     "aktuell"),
    ("crit_payout",         "Payout <= 60 %",                lambda r, pe: _le(r.get("payout_ratio_pct"), 60.0),                                    "payout_ratio_pct",   ""),
    ("crit_cashflow",       "Cashflow positiv (aktuell)",    lambda r, pe: _is_pos(r.get("operating_cashflow")) and _is_pos(r.get("free_cashflow")), "operating_cashflow", "aktuell"),
    ("crit_pe",             "KGV moderat",                   lambda r, pe: _le(r.get("trailing_pe"), pe),                                           "trailing_pe",        ""),
    ("crit_not_volatile",   "Nicht hochvolatil (IV-Rank)",   lambda r, pe: _le(r.get("iv_rank"), 60.0),                                             "iv_rank",            ""),
    ("crit_rsi",            "RSI nicht überkauft",           lambda r, pe: pd.notna(r.get("rsi_14")) and float(r.get("rsi_14")) < RSI_OVERBOUGHT,   "rsi_14",             ""),
    ("crit_macd",           "MACD steigend",                 lambda r, pe: _is_pos(r.get("macd_histogram")),                                        "macd_histogram",     ""),
    ("crit_sector",         "Kein Cannabis/Nischen-Sektor",  lambda r, pe: _sector_ok(r.get("sector")),                                             "sector",             ""),
]

SCORE_MAX = len(_CRITERIA)


def score_breakdown(row, pe_max: float = DEFAULT_PE_MAX) -> list:
    """Pro Kriterium: erreicht/möglich/ist-wert/annahme. Single Source of Truth für UI-Detail."""
    def _get(r, k):
        return r.get(k) if hasattr(r, "get") else r[k]
    out = []
    for col, label, fn, ist_key, annahme in _CRITERIA:
        out.append({
            "key": col,
            "label": label,
            "erreicht": bool(fn(row, pe_max)),
            "moeglich": 1,
            "ist_wert": _get(row, ist_key),
            "annahme": annahme,
        })
    return out
```

Danach `score_candidates` anpassen, damit es das 5-Tupel korrekt entpackt (Iteration nutzt jetzt `col, _label, fn, *_`):

```python
# src/put_screener.py — in score_candidates die Schleife anpassen
    for col, _label, fn, *_rest in _CRITERIA:
        out[col] = out.apply(lambda r, f=fn: bool(f(r, pe_max)), axis=1)
```

Und `criterion_labels` an das 5-Tupel anpassen:

```python
def criterion_labels() -> dict:
    """Mapping crit_-Spalte -> menschenlesbare Beschriftung (für die UI)."""
    return {col: label for col, label, *_ in _CRITERIA}
```

- [ ] **Step 4: Tests laufen grün**

Run: `pytest tests/test_put_screener.py -v`
Expected: PASS (4 Tests).

- [ ] **Step 5: Regression — Roll-Tests weiter grün**

Run: `pytest tests/test_put_screener.py tests/test_roll_support_calc.py -v`
Expected: PASS (alle).

- [ ] **Step 6: Commit**

```bash
git add src/put_screener.py tests/test_put_screener.py
git commit -m "feat(put-screener): score_breakdown() für Score-Herleitung + Annahme-Marker"
```

---

## Task 4: SQL — DTE-Bereich in `roll_put_history.sql` + Symbol-Liste

**Files:**
- Modify: `db/SQL/query/roll_put_history.sql` (DTE-Filter)
- Create: `db/SQL/query/roll_symbols.sql`

**Interfaces:**
- Produces: `roll_put_history.sql` akzeptiert zusätzlich `:dte_min`, `:dte_max`; `roll_symbols.sql` liefert Spalte `symbol`.
- Consumes: nichts (reine SQL). **Nicht lokal testbar** — Verifikation nach Push auf DB-Maschine.

- [ ] **Step 1: `roll_put_history.sql` um DTE-Filter erweitern**

Ersetze die `WHERE`/`ORDER BY`-Endzeilen (aktuell Z. 35–41) durch:

```sql
WHERE a.symbol = :symbol
  AND b.symbol = :symbol
  AND a.contract_type = 'put'
  AND a.date = :entry_date::date
  AND a.expiration_date::date > :entry_date::date
  AND (a.expiration_date::date - :entry_date::date) BETWEEN :dte_min AND :dte_max
ORDER BY a.expiration_date ASC, a.strike_price DESC
```

- [ ] **Step 2: `roll_symbols.sql` anlegen**

```sql
-- roll_symbols.sql
-- DISTINCT-Symbolliste für die Roller-Symbol-Selectbox (Autocomplete).
-- Nur Symbole, für die es überhaupt historische Optionsdaten gibt.
SELECT DISTINCT symbol
FROM "OptionDataMassiveHistory"
ORDER BY symbol
```

- [ ] **Step 3: Commit**

```bash
git add db/SQL/query/roll_put_history.sql db/SQL/query/roll_symbols.sql
git commit -m "feat(roll-support): DTE-Bereich in roll_put_history + roll_symbols.sql"
```

---

## Task 5: Roller-UI — Symbol-Selectbox + DTE-Bereich statt Freitext

**Files:**
- Modify: `pages/roll_and_screen.py` (`render_roller_tab` Anfang; Helfer `_load_symbols`, `_load_put_history`)

**Interfaces:**
- Consumes: `roll_symbols.sql`, `roll_put_history.sql` (mit `dte_min`/`dte_max`), `select_into_dataframe`, `render_date_filter`, `page_display_dataframe`.
- Produces: Roller nutzt `st.selectbox` (Symbol) + DTE-Range-Slider; `_load_put_history(symbol, entry_date, dte_min, dte_max)`.
- **Nicht lokal testbar** (Streamlit + DB) — Verifikation nach Push.

- [ ] **Step 1: Symbol-Loader ergänzen + `_load_put_history` um DTE erweitern**

```python
# pages/roll_and_screen.py — bei den Helfern ergänzen
@st.cache_data(ttl=300)
def _load_symbols():
    """DISTINCT-Symbolliste für die Selectbox. Reiner DB-Read -> darf cachen."""
    df = select_into_dataframe(
        sql_file_path=PATH_DATABASE_QUERY_FOLDER / "roll_symbols.sql",
        params={},
    )
    if df is None or df.empty:
        return []
    return df["symbol"].dropna().astype(str).tolist()
```

`_load_put_history` erweitern:

```python
@st.cache_data(ttl=300)
def _load_put_history(symbol, entry_date, dte_min, dte_max):
    """Puts eines Symbols am Einstiegsdatum im DTE-Bereich. Reiner DB-Read -> darf cachen."""
    return select_into_dataframe(
        sql_file_path=PATH_DATABASE_QUERY_FOLDER / "roll_put_history.sql",
        params={"symbol": symbol, "entry_date": str(entry_date),
                "dte_min": int(dte_min), "dte_max": int(dte_max)},
    )
```

- [ ] **Step 2: Symbol-Eingabe umbauen (Selectbox statt text_input)**

Ersetze in `render_roller_tab` den Block Symbol-`text_input` + „if not symbol"-Guard (aktuell Z. 146–152) durch:

```python
    symbols = _load_symbols()
    if not symbols:
        st.error("Keine Symbole mit historischen Optionsdaten gefunden.")
        return

    col_sym, col_n = st.columns([2, 1])
    symbol = col_sym.selectbox("Symbol", symbols,
                               index=None, placeholder="Symbol wählen…")
    n_contracts = col_n.number_input("Kontrakte (n)", min_value=1, value=1, step=1)
    if not symbol:
        st.info("Bitte ein Symbol wählen.")
        return
```

- [ ] **Step 3: DTE-Range-Slider nach dem Einstiegsdatum, vor der Put-Tabelle**

Ersetze den `_load_put_history(symbol, entry_date)`-Aufruf (aktuell Z. 167) so, dass davor ein DTE-Range steht:

```python
    dte_min, dte_max = st.slider(
        "DTE-Bereich am Einstiegsdatum (Tage bis Verfall)",
        min_value=1, max_value=400, value=(30, 60), step=1,
        help="Zeigt alle Puts, deren Restlaufzeit am Einstiegsdatum in diesem Bereich lag.",
    )
    hist_df = _load_put_history(symbol, entry_date, dte_min, dte_max)
    if hist_df is None or hist_df.empty:
        st.warning(f"Keine Puts für {symbol} am {entry_date} im DTE-Bereich {dte_min}–{dte_max} gefunden.")
        return
```

- [ ] **Step 4: Push + User-Verifikation**

```bash
git add pages/roll_and_screen.py
git commit -m "feat(roll-support): Roller mit Symbol-Selectbox + DTE-Bereich"
git push origin feature/roll-and-screen
```

Dann dem User melden: „Bitte auf DB-Maschine ziehen, Roller-Tab öffnen, Symbol wählen + DTE-Bereich testen, Fehler zurückmelden." Fehler → fixen, erneut pushen.

---

## Task 6: Roller-UI — heutiger Wert = letzter DB-day_close (kein Live-Call)

**Files:**
- Modify: `pages/roll_and_screen.py` (`_current_put_price` vereinfachen)

**Interfaces:**
- Produces: `_current_put_price(option_osi, symbol)` — nur noch DB-Fallback, gibt `(preis_je_aktie, quelle_str)` oder `(None, grund)`.
- Consumes: `select_into_dataframe`. **Nicht lokal testbar.**

- [ ] **Step 1: `_current_put_price` auf reinen DB-Read reduzieren**

Ersetze die gesamte Funktion `_current_put_price` (aktuell Z. 73–113) durch:

```python
# NICHT gecacht: immer frisch (User-Wunsch), aber kein externer Call.
def _current_put_price(option_osi, symbol):
    """Heutiger Wert des bestehenden Puts = letzter verfügbarer day_close aus der DB.

    Kein Live-YahooQuery (User-Wunsch). 1-Wochen-Fenster als Fallback, falls der
    exakte heutige Tag fehlt. Rückgabe: (preis_je_aktie, quelle_str) oder (None, grund).
    """
    sql = """
        SELECT a.day_close AS premium_option_price, a.date
        FROM (
            SELECT date, option_osi, symbol, day_close FROM "OptionDataMassiveHistory"
            WHERE date <> CURRENT_DATE
            UNION ALL
            SELECT CURRENT_DATE AS date, option_osi, symbol, day_close FROM "OptionDataMassive"
        ) AS a
        WHERE a.option_osi = :osi AND a.symbol = :symbol
          AND a.date <= CURRENT_DATE
        ORDER BY a.date DESC
        LIMIT 1
    """
    df = select_into_dataframe(query=sql, params={"osi": option_osi, "symbol": symbol})
    if df is not None and not df.empty:
        d = df.iloc[0]["date"]
        return float(df.iloc[0]["premium_option_price"]), f"DB day_close ({d})"
    return None, "kein Preis in DB"
```

- [ ] **Step 2: Aufrufer anpassen (kein `strike`/`expiration_date`-Argument mehr)**

Im `ThreadPoolExecutor`-Block (aktuell Z. 201–204) den Submit ändern:

```python
        f_price = ex.submit(_current_put_price, option_osi, symbol)
```

Und den nun unnötigen Import `YahooQueryScraper` sowie `is_weekend`/`_today_str` prüfen — `_today_str` wird evtl. nirgends mehr gebraucht; nur entfernen wenn ungenutzt (sonst lassen). `from src.yahooquery_scraper import YahooQueryScraper` entfernen, falls kein anderer Aufruf im File bleibt (mit grep prüfen).

- [ ] **Step 3: Push + User-Verifikation**

```bash
git add pages/roll_and_screen.py
git commit -m "feat(roll-support): heutiger Put-Wert nur aus DB day_close (kein Live-Call)"
git push origin feature/roll-and-screen
```

Meldung an User: „Roller: heutiger Wert kommt jetzt aus letztem DB-day_close. Bitte testen."

---

## Task 7: Roller-UI — Status-Banner (Verlust/Gewinn) + Kandidaten-Detail

**Files:**
- Modify: `pages/roll_and_screen.py` (`render_roller_tab` Roll-Block; `_render_stufe` um Klick-Detail)

**Interfaces:**
- Consumes: `roll_candidate_explained` (Task 2), `position_status`, `page_display_dataframe`.
- Produces: Banner je nach P&L; pro Stufe selektierbare Tabelle mit Klick→Herleitung.
- **Nicht lokal testbar.**

- [ ] **Step 1: Status-Banner vor den Roll-Kandidaten**

Nach dem „Aktuelle Position"-Block, vor `st.markdown("### 🎯 Roll-Kandidaten...")` (aktuell Z. 233–235) einfügen:

```python
    im_verlust = P_heute > P_eroeffnung
    if im_verlust:
        st.error("🔴 Position im Verlust — **Rollen sinnvoll** (Basispreis senken nach Buch-Regel).")
    else:
        st.success("🟢 Position im Gewinn — Rollen **optional** (z. B. um Laufzeit zu verlängern).")
```

- [ ] **Step 2: `_render_stufe` um Klick-Herleitung erweitern**

Ersetze `_render_stufe` (aktuell Z. 269–297) so, dass die Tabelle selektierbar ist und bei Klick die Herleitung des gewählten Kandidaten zeigt. Nutzt `roll_candidate_explained`:

```python
from src.roll_support_calc import position_status, roll_candidate, roll_candidate_explained  # Import oben ergänzen


def _render_stufe(stufe, df, K, P_eroeffnung, P_heute, n, breakeven_old, title):
    """Rendert eine Stufen-Tabelle mit Klick-Herleitung. True wenn mind. ein ✅ existiert."""
    st.markdown(f"#### {title}")
    if df is None or df.empty:
        st.caption("Keine passenden Strikes in dieser Stufe.")
        return False

    rows, calc_by_idx = [], {}
    for i, (_, o) in enumerate(df.iterrows()):
        K2 = float(o["strike_price"])
        P_neu = float(o["premium_option_price"]) * 100.0
        r = roll_candidate(stufe=stufe, K=K, K2=K2, P_eroeffnung=P_eroeffnung,
                           P_heute=P_heute, P_neu=P_neu, n=n)
        calc_by_idx[i] = dict(K2=K2, P_neu=P_neu)
        rows.append({
            "Ampel": r["ampel"], "Neuer Strike": K2, "Expiry": o["expiration_date"],
            "DTE": int(o["days_to_expiration"]), "Prämie neu ($)": float(o["premium_option_price"]),
            "Netto absolut ($)": round(r["netto_abs"], 2), "Neue GS": round(r["breakeven_new"], 2),
            "Alte GS": round(breakeven_old, 2), "Kapital nötig ($)": round(r["kapital_noetig"], 2),
            "OI": int(o["open_interest"]), "Vol": int(o["day_volume"]),
        })
    out = pd.DataFrame(rows)
    event = st.dataframe(out, use_container_width=True, hide_index=True,
                         on_select="rerun", selection_mode="single-row",
                         key=f"stufe_{stufe}")
    sel = event.selection.rows if hasattr(event, "selection") else []
    if sel:
        c = calc_by_idx[sel[0]]
        exp = roll_candidate_explained(stufe=stufe, K=K, K2=c["K2"],
                                       P_eroeffnung=P_eroeffnung, P_heute=P_heute,
                                       P_neu=c["P_neu"], n=n)
        with st.container(border=True):
            st.markdown(f"**Herleitung — Strike {c['K2']:.2f}** ({exp['ampel']})")
            for s in exp["steps"]:
                st.write(f"- **{s['label']}:** {s['formel']} = **{s['wert']:.2f}**")
            st.caption("🔶 Prämien = day_close (Näherung; echter Bid/Ask im Broker prüfen).")
    return (out["Ampel"] == "✅").any()
```

- [ ] **Step 3: Push + User-Verifikation**

```bash
git add pages/roll_and_screen.py
git commit -m "feat(roll-support): Status-Banner + Roll-Kandidaten-Herleitung bei Klick"
git push origin feature/roll-and-screen
```

Meldung an User: „Roller: Banner Verlust/Gewinn + Klick auf Kandidat zeigt Herleitung. Bitte testen."

---

## Task 8: Screener-UI — Filter oben + Klick-Detail-Panel + Annahmen

**Files:**
- Modify: `pages/roll_and_screen.py` (`render_screener_tab`; Import `score_breakdown`)

**Interfaces:**
- Consumes: `score_breakdown` (Task 3), `score_candidates`, `page_display_dataframe`, `_load_screener`.
- Produces: Filter im `st.expander` oben (kein Sidebar), selektierbare Ergebnistabelle, Detail-Panel je Aktie mit Score-Herleitung + Annahmen-Sammelkasten.
- **Nicht lokal testbar.**

- [ ] **Step 1: Import ergänzen**

```python
# oben: bestehenden put_screener-Import erweitern
from src.put_screener import score_candidates, score_breakdown, criterion_labels, DEFAULT_PE_MAX
```

- [ ] **Step 2: Filter von Sidebar nach oben (Expander + Columns)**

Ersetze in `render_screener_tab` den `with st.sidebar:`-Block (aktuell Z. 328–337) durch einen Expander oben:

```python
    with st.expander("🔍 Filter", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        pe_max = c1.slider("KGV-Obergrenze", 10, 200, int(DEFAULT_PE_MAX), 5,
                           help="Tech-Werte dürfen höher liegen.")
        min_score = c2.slider("Mindest-Score", 0, 9, 5, 1)
        dte_min, dte_max = c3.slider("DTE-Fenster (Tage)", 7, 90, (21, 45), 1)
        min_oi = c4.number_input("Min. Open Interest", min_value=100, value=100, step=50)
        min_vol = c4.number_input("Min. Tagesvolumen", min_value=100, value=100, step=50)
```

- [ ] **Step 3: Ergebnistabelle selektierbar + Detail-Panel**

Ersetze den Ergebnis-Block (aktuell Z. 364–375, `page_display_dataframe(... on_select="ignore")` + globaler Score-Details-Expander) durch:

```python
    st.success(f"{len(scored)} qualifizierte Aktien (Score ≥ {min_score}, max {scored.iloc[0]['score_max']}).")
    event = page_display_dataframe(
        scored[display_cols],
        symbol_column="symbol",
        on_select="rerun",
        selection_mode="single-row",
    )
    sel = event.selection.rows if hasattr(event, "selection") else []
    if not sel:
        st.info("Klicke eine Aktie an, um die Score-Herleitung zu sehen.")
        return

    row = scored.iloc[sel[0]]
    st.divider()
    st.markdown(f"### 🔬 Score-Herleitung — {row['symbol']}  ({int(row['score'])}/{int(row['score_max'])})")

    bd = score_breakdown(row, pe_max=pe_max)
    ann_map = {"aktuell": "🔶 (aktuell)", "Näherung": "🔶 (Näherung)", "day_close": "🔶 (day_close)", "": ""}
    detail = pd.DataFrame([{
        "Kriterium": i["label"],
        "Erreicht": "✅" if i["erreicht"] else "❌",
        "Möglich": i["moeglich"],
        "Ist-Wert": i["ist_wert"],
        "Annahme": ann_map.get(i["annahme"], ""),
    } for i in bd])
    st.dataframe(detail, use_container_width=True, hide_index=True)

    getroffene = sorted({i["annahme"] for i in bd if i["annahme"]})
    if getroffene:
        with st.expander("⚠️ Getroffene Annahmen", expanded=False):
            texte = {
                "aktuell": "**(aktuell):** Momentaufnahme statt Mehrjahres-Trend — Yahoo liefert nur den jüngsten Abschluss, kein 10-Jahres-Verlauf.",
                "Näherung": "**(Näherung):** Ersatzgröße statt echtem Wert (z. B. Support ≈ 52W-Tief + SMA200).",
                "day_close": "**(day_close):** Prämie = Tagesschluss statt echtem Bid/Ask.",
            }
            for a in getroffene:
                st.markdown("- " + texte.get(a, a))
```

- [ ] **Step 4: Push + User-Verifikation**

```bash
git add pages/roll_and_screen.py
git commit -m "feat(put-screener): Filter oben + Klick-Detail-Panel mit Score-Herleitung & Annahmen"
git push origin feature/roll-and-screen
```

Meldung an User: „Screener: Filter jetzt oben, Klick auf Aktie zeigt Score-Herleitung + Annahmen. Bitte testen — insb. ob `score_breakdown` mit den echten SQL-Spalten harmoniert (Ist-Werte korrekt)."

---

## Task 9: Endabnahme + Aufräumen

**Files:**
- Modify: `pages/roll_and_screen.py` (nur falls User-Feedback Fixes nötig macht)

- [ ] **Step 1: Alle lokalen Tests grün**

Run: `pytest tests/test_put_screener.py tests/test_roll_support_calc.py -v`
Expected: PASS (alle).

- [ ] **Step 2: Ungenutzte Importe entfernen**

Run: `grep -nE 'YahooQueryScraper|is_weekend|_today_str|ThreadPoolExecutor' pages/roll_and_screen.py`
Prüfen, ob nach den Umbauten noch benutzt. Ungenutzte Importe/Helfer entfernen (z. B. `_today_str`, `YahooQueryScraper`, falls kein Aufruf mehr).

- [ ] **Step 3: Finaler Commit + Push**

```bash
git add -A
git commit -m "chore(roll-support): ungenutzte Importe entfernt, V2 abgeschlossen"
git push origin feature/roll-and-screen
```

- [ ] **Step 4: DoD-Abhaken mit User**

Gehe die DoD aus dem Spec (`design-2026-07-12-roll-and-screen-v2.md`) mit dem User durch — insbesondere die „auf DB-Maschine"-Punkte, die nur er verifizieren kann.

---

## Self-Review-Ergebnis

**Spec-Coverage:** Screener-Filter-oben (Task 8), Klick-Detail (Task 8), Annahmen-Marker+Sammelkasten (Task 3+8), Roller Symbol-Autocomplete (Task 5), DTE-Bereich (Task 4+5), Einstand-Override (bestehend, unverändert), heutiger Wert ohne Live-Call (Task 6), Status-Banner (Task 7), Kandidaten-Herleitung (Task 2+7), Endspiel-Hinweis (bestehend). ✅ Alle Spec-Punkte haben eine Task.

**Platzhalter:** keine — jeder Code-Step zeigt vollständigen Code.

**Typ-Konsistenz:** `score_breakdown` liefert `{key,label,erreicht,moeglich,ist_wert,annahme}` — in Task 3 definiert, in Task 8 exakt so konsumiert. `roll_candidate_explained` liefert `{...roll_candidate, steps:[{label,formel,wert}]}` — Task 2 definiert, Task 7 konsumiert `steps`/`ampel`. `_load_put_history` bekommt in Task 4 (SQL-Params) und Task 5 (Signatur) dieselben 4 Argumente. `_current_put_price(option_osi, symbol)` — Task 6 Signatur == Aufruf. ✅ konsistent.
