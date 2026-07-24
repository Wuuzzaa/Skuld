# SKULD Job-Scheduler (SM36/SM37-Stil) — Design

**Datum:** 2026-07-24
**Status:** genehmigt, in Umsetzung
**Auslöser:** Ein Fehlklick auf „Start Job" (`--mode all`) hat einen destruktiven Vollimport
(`TRUNCATE OptionDataMassive`, 924.745 Zeilen) gefeuert. Kein Schaden (Postgres-Rollback beim
harten Abbruch), aber die Lücke ist real: ein Klick = destruktiver Sofort-Start.

## Ziel

Ein Sicherheitsnetz nach SAP-SM36/SM37-Vorbild: Jobs werden **geplant** (Queue) statt sofort
gefeuert; ein Worker führt fällige Jobs aus. Destruktive Modi verlangen zusätzlich einen
Typing-Confirm.

## Entscheidungen

| Thema | Entscheidung |
|---|---|
| Netz-Typ | Schedule-Queue (SM37-Stil), geplante Jobs stornierbar |
| Worker | Cron-Dispatcher (Python) im `skuld-backend`-Container, Takt `* * * * *` (jede Minute) |
| Queue-Speicher | Dateibasiert unter `logs/_queue/` (analog `logs/_status/`) — kein DB-Schema-Eingriff |
| Schutzgrad | Queue + Typing-Confirm bei destruktiven Modi (`all`, `historical_full`, `only_run_migrations`) |
| Parallelität | Wie bisher — kein globaler Lock, `run_data_collection.sh` unangetastet |
| Umsetzung | Python-Dispatcher (`src/job_dispatcher.py`), reine testbare Queue-Logik |

## Architektur & Datenfluss

```
Admin-Page (Streamlit)          logs/_queue/            Cron (jede Minute)
[Einplanen] ──schreibt──▶ <job>.json (geplant) ◀──liest── job_dispatcher.py
[Geplante Jobs]                    │                        │ fällig? run_at<=now & status=geplant
   └─ [Stornieren] ──löscht──▶  <geplant>.json      os.rename → status=laufend (Claim)
                                                            │
                                                  run_data_collection.sh <mode>
                                                  (bestehend: Lock/Timeout/write_status/Telegram)
                                                            ▼
                                                  logs/_status/*.jsonl (unverändert)
```

Zwei getrennte Wahrheits-Quellen: `logs/_queue/` = was noch kommt; `logs/_status/` = was fertig
ist (bleibt exakt wie heute, Dispatcher fasst es nicht an).

**Warum `logs/`:** einziger host-gemounteter, rebuild-sicherer Schreibpfad
(`docker-compose.yml`: `./logs:/app/Skuld/logs`).

## Queue-Datei-Format

Ein JSON pro Job unter `logs/_queue/`. Dateiname kodiert Status für atomares Claiming via `rename`:

```
<run_at_iso>__<mode>__<uuid8>.<status>.json
   status ∈ {geplant, laufend}
```

Inhalt:
```json
{
  "id": "a1b2c3d4",
  "mode": "option_data",
  "run_at": "2026-07-24T18:30:00Z",
  "created_at": "2026-07-24T18:05:12Z",
  "created_by": "admin-page",
  "status": "geplant"
}
```

- **Einplanen jetzt:** `run_at = now` → Dispatcher nimmt es beim nächsten Minutentakt.
- **Einplanen später:** `run_at = gewählte Uhrzeit`.
- **Claiming:** Dispatcher `rename(...geplant.json → ...laufend.json)` VOR dem Start → verhindert
  Doppelstart bei überlappenden Dispatcher-Läufen (rename ist atomar auf gleichem Filesystem).
- **Nach Start:** Dispatcher startet `run_data_collection.sh <mode>` detached und **löscht** die
  `laufend`-Datei (der Job trackt sich ab da selbst via `logs/_status/`). Kein Endzustand in der
  Queue nötig → keine Ewig-Dateien.

## Confirm-Flow (Admin-Page)

- Modus-Auswahl wie bisher. „Start Job" → **„Einplanen"** (+ optionaler Zeit-Picker; leer = jetzt).
- Für `DESTRUCTIVE_MODES = {all, historical_full, only_run_migrations}`: ein Textfeld
  „Modusnamen zur Bestätigung eingeben"; „Einplanen"-Button erst aktiv, wenn Eingabe == Modus.
- Neuer Bereich „Geplante Jobs": listet `geplant`-Einträge (Zeit, Modus, wer), je Zeile
  „Stornieren" (löscht Datei). `laufend`-Einträge werden angezeigt, aber nicht stornierbar.

## Fehlerbehandlung

- **Korrupte Queue-Datei** (JSON kaputt): Dispatcher überspringt sie, loggt Warnung, verschiebt sie
  nach `logs/_queue/_corrupt/` (kein Crash, Rest der Queue läuft).
- **`run_data_collection.sh` nicht startbar** (Docker-Exec-Fehler): Dispatcher läuft im
  Backend-Container selbst → ruft das Skript **lokal** auf (kein Docker-Socket nötig, anders als
  die Admin-Page). Fehlgeschlagener Start → Datei zurück auf `geplant` + Warnung.
- **Zukunfts-Jobs:** die 14-Tage-Log-Rotation (`crontab` Z.25) darf `logs/_queue/` NICHT löschen →
  Rotation-Zeile bleibt auf `find /app/Skuld/logs -type f -mtime +14 -delete`; ein weit geplanter
  Job wird durch Bearbeitungs-`mtime` aktuell gehalten oder — sicherer — `_queue/` wird per
  `-not -path "*/_queue/*"` ausgenommen. **Entscheidung: ausnehmen.**

## Nicht angefasst (bewusst)

`run_data_collection.sh` (pro-Modus-Lock, Timeouts, Status), `main.py`, DB-Schema, die 5 regulären
Cron-Zeilen. Der neue Dispatcher ist rein additiv: eine crontab-Zeile + ein Python-Modul + Umbau
des Admin-Buttons. Rückbaubar per Revert.

## Deploy-Hinweise

- crontab ist **image-baked** (`Dockerfile:25 COPY crontab /etc/cron.d/skuld-cron`) → die neue
  Dispatcher-Zeile kommt per Deploy in Betrieb, nicht per Runtime-Edit.
- Admin-Page ist bereits in `app.py` registriert (Z.44) → kein `app.py`-Eingriff.
- Nach Deploy verifizieren: `docker exec skuld-backend crontab -l | grep dispatch`,
  Admin-Page „Einplanen" schreibt Datei, Dispatcher startet sie im Minutentakt.

## Tests

Reine Queue-Logik in `src/job_dispatcher.py` als testbare Funktionen (kein DB/Docker):
- Einplanen schreibt korrekte `geplant`-Datei mit `run_at`.
- `due_jobs(now)` liefert nur fällige `geplant`-Jobs, ignoriert Zukunft + `laufend`.
- Claim: `geplant → laufend` rename, zweiter Claim derselben Datei schlägt fehl (kein Doppelstart).
- Korrupte Datei wird übersprungen, nicht geworfen.
- Stornieren löscht nur `geplant`, nicht `laufend`.
