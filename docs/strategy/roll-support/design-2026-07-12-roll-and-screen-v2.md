# Roll & Screen — Design Spec V2 (UX-Überarbeitung + Time-Travel-Roller)

**Datum:** 2026-07-12
**Branch:** `feature/roll-and-screen`
**Ersetzt/erweitert:** `design-2026-07-10-roll-and-screen.md`
**Grund:** Nach erster Sichtung durch den User. Zwei Baustellen:
  1. **Screener-UX** — Filter nach oben (wie andere Seiten), Klick-auf-Aktie → Score-Herleitung, Annahmen überall sichtbar.
  2. **Roller-Neubau** — vom „Symbol eintippen + aktuelle Kette" hin zum **vollen Time-Travel-Backtest-Fluss** wie `married_put_backtesting` / `spreads_backtesting`.

**Persistenz:** keine (session-only). **DB-Schema:** kein Change.
**Caching:** reine DB-Reads dürfen `@st.cache_data`; Roll-/Positions-Kernrechnung NICHT.

---

## ⚠️ Randbedingung: DB liegt auf anderer Maschine

Die Datenbank ist **nicht** auf der Entwicklungsmaschine erreichbar. Daraus folgt der Arbeitsmodus:

- **Lokal testbar (hier):** nur pure-Python-Rechenkerne ohne DB/Streamlit — `src/roll_support_calc.py`, `src/put_screener.py`. Dafür laufen echte `pytest`-Unit-Tests grün, BEVOR gepusht wird.
- **Nicht lokal testbar:** SQL-Queries und Streamlit-Rendering. Diese werden nur nach Code-Logik geprüft.
- **Feedback-Schleife:** Logik schreiben → pure-Python-Tests grün → **auf `feature/roll-and-screen` pushen** → User zieht auf der DB-Maschine → meldet Fehler zurück → Fix → wiederholen.
- **Konsequenz für Architektur:** Rechenlogik muss maximal von DB/UI getrennt sein, damit der testbare Kern groß und die untestbare Naht dünn ist. Jede Zahl, die in der UI erscheint, kommt aus einer pure-Python-Funktion, die einen Unit-Test hat.
- **Tests werden mitgepusht** — aber **nur auf `feature/roll-and-screen`, NIE auf `master`**. „Nicht auf master" ≠ „nicht ins Repo": der User braucht sie auf der DB-Maschine zur Verifikation, also liegen sie auf dem Feature-Branch.

### Branch-Regel (verbindlich)

- **Alles bleibt auf `feature/roll-and-screen`.** Kein Merge/Push nach `master` durch mich — weder Code noch Tests.
- Die Seite ist in `app.py` **bereits registriert** (Zeile 42, `roll_and_screen = st.Page(...)`) → **keine Registrierung nötig**.

---

## Teil A — Screener-UX

### A1. Filter nach oben (statt Sidebar)

**Ist:** Filter liegen in `st.sidebar` (`render_screener_tab`, Zeilen 328–337).
**Soll:** Filter oben in der Seite, im etablierten Muster von `dividend_screener_zahltagstrategie.py` (Z. 145–150):

```python
with st.expander("🔍 Filter", expanded=True):
    c1, c2, c3, c4 = st.columns(4)
    # KGV-Max, Min-Score, DTE-Fenster, OI/Vol
```

- Kein Sidebar-Code mehr im Screener-Tab.
- Gleiche Widgets/Defaults wie bisher (KGV-Max Default `DEFAULT_PE_MAX`, Min-Score 5, DTE (21,45), OI/Vol ≥100), nur umplatziert.
- „Screener starten"-Button bleibt, direkt unter dem Filter-Expander.

### A2. Klick auf Aktie → Detail-Panel unter der Tabelle

**Ist:** Ergebnis-Tabelle mit `on_select="ignore"` + ein globaler Expander „Score-Details je Kriterium" (Matrix aller Aktien).
**Soll:** Tabelle wird **selektierbar** (`on_select="rerun"`, `single-row`). Klick auf eine Zeile → **Detail-Panel darunter** für genau diese Aktie:

- Kopf: Symbol, Kurs, Gesamt-Score `x / max`, vorgeschlagener Put (Strike/Expiry/DTE/Prämie/Rendite/Gewinnschwelle/Kapital).
- **Score-Herleitung** als Tabelle, eine Zeile je Kriterium:

  | Kriterium | Erreicht | Möglich | Ist-Wert | Annahme |
  |---|---|---|---|---|
  | Umsatzwachstum | ✅ 1 | 1 | +8,3 % | 🔶 (aktuell) |
  | KGV moderat | ❌ 0 | 1 | 46,2 | — |
  | RSI nicht überkauft | ✅ 1 | 1 | 58 | — |
  | Nahe Unterstützung | ✅ 1 | 1 | 4 % über 52W-Tief | 🔶 (Näherung) |
  | … | | | | |

- Die Herleitung kommt aus einer **erweiterten Scoring-Funktion** (siehe A4), die pro Kriterium `(erreicht, möglich, ist_wert, annahme)` zurückgibt — nicht nur den Summen-Score.

### A3. Annahmen überall sichtbar + Sammelkasten

Einheitliche Kennzeichnung an **jeder** Stelle, wo Skuld eine Annahme/Näherung trifft:

| Marker | Bedeutung | Beispiele |
|---|---|---|
| 🔶 (aktuell) | Momentaufnahme statt Mehrjahres-Trend | Umsatz-/EPS-/Cashflow-Wachstum (Yahoo liefert nur ~aktuellen Abschluss) |
| 🔶 (Näherung) | Ersatzgröße statt echtem Wert | Support-Level = 52W-Tief + SMA200 |
| 🔶 (day_close) | Prämie = Tagesschluss statt echtem Bid/Ask | Screener-Put-Prämie, Roller-Historie |

- **Marker** erscheint als Spalten-Wert/Suffix + `help=`-Tooltip mit Klartext-Begründung.
- **Sammelkasten** unter jedem Ergebnis: `st.expander("⚠️ Getroffene Annahmen")` listet alle in diesem Ergebnis wirksamen Annahmen einmal ausgeschrieben (die verifizierte Datenlage aus dem alten Spec, Abschnitt „Warum nur aktuell").

### A4. Scoring-Refactor für Transparenz

`src/put_screener.py::score_candidates` liefert heute nur den Summen-Score + Kriteriumsspalten. Für das Detail-Panel wird ergänzt:

- Neue Funktion `score_breakdown(row, pe_max) -> list[dict]`: pro Kriterium `{key, label, erreicht, moeglich, ist_wert, annahme}`.
- `score_candidates` nutzt intern `score_breakdown` (Single Source of Truth — Summe = Summe der `erreicht`).
- **Diese Funktion ist pure Python → voll unit-testbar** (Kern des lokal testbaren Teils).

---

## Teil B — Roller-Neubau (voller Time-Travel wie Spreads)

### B1. Neuer Ablauf

Angelehnt 1:1 an `married_put_backtesting.display_married_put_backtesting` bzw. `spreads_backtesting`:

1. **Symbol wählen** — `st.selectbox` mit Autocomplete (Streamlit-Typeahead), Symbol-Liste aus DB (siehe B2). Kein Freitext-`text_input` mehr.
2. **Historisches Einstiegsdatum** — `render_date_filter` gegen `DatesHistory` (nur Tage, an denen es Daten gibt).
3. **DTE-Bereich am Einstiegsdatum** — statt aller Puts als eine riesige Liste bzw. eines Einzel-Verfalls:
   - Zwei-Zahlen-DTE-Filter (z. B. Slider/Range `dte_min`–`dte_max`, Default 30–60), bezogen aufs **Einstiegsdatum**.
   - Skuld zeigt **alle Puts** des Symbols, deren `days_to_expiration` (= `expiration_date − entry_date`) in diesem Bereich liegt — über mehrere Verfälle hinweg.
   - Anzeige als **selektierbare Tabelle** (Strike/Verfall/DTE/Prämie/…) → User klickt seinen gehandelten Put (Zeilenauswahl).
   - Es werden nur Puts angeboten, die am Einstiegsdatum **tatsächlich in der DB liegen** (`roll_put_history.sql` gegen `OptionDataMassiveHistory`, um `dte_min`/`dte_max` erweitert).
4. **Einstandskurse (Backtest-Option)** — Checkbox „🛠️ Echte Ausführungskurse (Optional)":
   - Default: `day_close` am Einstiegsdatum als Eröffnungsprämie (🔶 day_close).
   - Override: reale Fill-Prämie manuell (Muster `spreads_backtesting.py`).
5. **Heutiger Wert** desselben Puts — **letzter in der DB verfügbarer `day_close`** dieses `option_osi` (jüngster Tag, 1-Wochen-Fallback-Fenster). **KEIN Live-YahooQuery-Call** (User-Wunsch: der letzte DB-Wert reicht, robuster + kein externer Call). 🔶 day_close.
6. **Block „Aktuelle Position"** — `position_status` (pnl %/abs, innerer Wert, Restzeitwert, alte Gewinnschwelle, DTE).
7. **Roll-Block — IMMER anzeigen, Status markiert:**
   - Position **im Minus** (`P_heute > P_eroeffnung`): Banner „🔴 Position im Verlust — Rollen sinnvoll" → volle Roll-Kandidaten.
   - Position **im Plus**: Banner „🟢 Position im Gewinn — Rollen optional (z. B. um DTE zu verlängern)" → Kandidaten trotzdem sichtbar, aber als optional beschriftet.
8. **3 Roll-Stufen** — je eine Tabelle mit Ampel (bestehende Logik `roll_candidate`).
9. **Roll-Kandidat aufklappbar** — Klick auf einen Kandidaten → Detail: Herleitung von Netto-Prämie und neuer Gewinnschwelle (dieselbe Transparenz-Idee wie Screener-Detail). Zeigt die Buch-Formel mit eingesetzten Zahlen.
10. **Endspiel-Hinweis** — wenn keine ✅ in allen Stufen: bestehender Hinweis + Verweis auf ITM-CC-Scanner.

### B2. Symbol-Autocomplete

- `st.selectbox("Symbol", symbols)` — Streamlit-Selectbox hat eingebautes Type-to-filter (= „Autocomplete"-Gefühl). Muster existiert: `married_put_analysis.py:163`, `rsl_momentum.py:192`.
- Symbol-Liste: `SELECT DISTINCT symbol FROM "OptionDataMassiveHistory" ORDER BY symbol` (oder vorhandener Symbol-Helper, falls einer existiert — beim Bauen prüfen). Gecacht (`@st.cache_data`).
- Kein voller Fuzzy-Autocomplete-Widget nötig — Selectbox reicht und bleibt konsistent zu den anderen Seiten.

### B2b. Put-Auswahl-Query (Erweiterung bestehender Query)

- `roll_put_history.sql` existiert bereits und liefert alle Puts eines Symbols am Einstiegsdatum. **Erweiterung:** um `dte_min`/`dte_max`-Filter auf `days_to_expiration` (= `expiration_date − entry_date`), damit der DTE-Bereich greift.
- Kein separates Verfall-Dropdown/keine eigene Verfall-Query nötig (DTE-Bereich statt Einzel-Verfall).

### B3. Roll-Kandidaten-Datenquelle

- Unverändert `roll_candidates.sql` (aktuelle Kette, DTE 30–90, liquide).
- **Wichtig:** „heutiger Wert" und Roll-Kandidaten kommen aus der **aktuellen** Kette (`OptionDataMerged` / `OptionDataMassive`), nicht aus der Vergangenheit. Nur der **Einstand** (Symbol + Vergangenheitsdatum + Put-Auswahl) ist Time-Travel. Das entspricht der Realität: man rollt **heute**, mit heutigen Preisen; die neuen Puts laufen in die Zukunft (DTE 30–90), diese Daten existieren heute schon in der aktuellen Kette. Es werden **keine** Kursdaten aus der Zukunft benötigt.

### B4. Rechenkerne (pure Python, lokal getestet)

- `position_status`, `roll_candidate`, `ampel` — **existieren bereits und sind buchverifiziert**. Nicht neu erfinden.
- Ergänzung nur, falls das Kandidaten-Detail (B1.9) eine zusätzliche „Herleitungs-Struktur" braucht — dann als reine Funktion `roll_candidate_explained(...) -> dict` mit den Zwischenschritten, ebenfalls unit-getestet gegen die Buch-Szenarien.

---

## Datei-Übersicht (was wird angefasst)

| Datei | Änderung |
|---|---|
| `pages/roll_and_screen.py` | **Groß:** Screener-Tab (Filter oben, Detail-Panel), Roller-Tab (Time-Travel-Fluss, Symbol-Selectbox, Status-Banner, Kandidaten-Detail) |
| `src/put_screener.py` | **Mittel:** `score_breakdown()` ergänzen, `score_candidates` darauf aufsetzen |
| `src/roll_support_calc.py` | **Klein/optional:** ggf. `roll_candidate_explained()` für Kandidaten-Detail |
| `db/SQL/query/put_screener.sql` | Prüfen, ob alle für die Herleitung nötigen Ist-Werte selektiert werden |
| `db/SQL/query/roll_put_history.sql` | **Klein:** um `dte_min`/`dte_max`-Filter erweitern (DTE-Bereich am Einstiegsdatum) |
| `db/SQL/query/roll_candidates.sql` | Wahrscheinlich unverändert |
| `db/SQL/query/symbols_options.sql` (neu) | DISTINCT-Symbolliste für Selectbox (falls kein Helper existiert) |
| `tests/test_roll_support_calc.py` | Bestehende Buch-Szenario-Tests; ggf. Tests für `roll_candidate_explained` |
| `tests/test_put_screener.py` | Tests für `score_breakdown` (erreicht/möglich/annahme je Kriterium) |

---

## Explizit NICHT in Scope (V2)

- DB-Schema-Change / echter Mehrjahres-Trend (bleibt Proxy „aktuell", ehrlich markiert).
- Echter Bid/Ask je Option in der Historie (day_close-Näherung bleibt).
- Roll-Ketten über mehrere Rollen (ein Einstand, ein Roll-Schritt).
- Asymmetrischer CC-Endspiel-Rechner (nur Hinweis + Verweis).
- React-Portierung.

---

## Definition of Done (V2)

**Lokal (ohne DB) verifizierbar:**
- [ ] `pytest tests/test_roll_support_calc.py -v` grün (Buch-Szenarien 1–4).
- [ ] `pytest tests/test_put_screener.py -v` grün (`score_breakdown`: pro Kriterium erreicht/möglich/annahme korrekt; Summe konsistent).

**Auf DB-Maschine (User verifiziert nach Push):**
- [ ] Screener: Filter oben, Klick auf Aktie → Detail-Panel mit Score-Herleitung, Annahmen-Marker + Sammelkasten sichtbar.
- [ ] Roller: Symbol-Selectbox mit Autocomplete; Einstiegsdatum → **DTE-Bereich (z. B. 30–60) → alle Puts darin als Tabelle** → Auswahl → Einstand (mit Override) → heutiger Wert (letzter DB-`day_close`, kein Live-Call) → Position-Block.
- [ ] Roll-Block immer sichtbar, Status-Banner (Verlust/Gewinn) korrekt.
- [ ] Roll-Kandidat aufklappbar → Netto-/GS-Herleitung.
- [ ] Endspiel-Hinweis wenn keine ✅.
- [ ] Keine Regression: Seite lädt in `app.py`, beide Tabs laufen.

## Arbeitsmodus-Checkliste (jeder Push)
- [ ] Pure-Python-Tests grün gemacht.
- [ ] Nur `feature/roll-and-screen` gepusht (kein anderer Branch).
- [ ] User-Feedback (Fehler von DB-Maschine) abwarten, dann Fix.
