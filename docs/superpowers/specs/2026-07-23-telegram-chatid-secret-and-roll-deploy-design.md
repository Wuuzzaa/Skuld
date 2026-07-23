# Prod-Telegram-Chat-ID als Secret + OPS-Entfernung + Roll-&-Screen-Deploy

**Datum:** 2026-07-23
**Status:** Design abgestimmt, Umsetzung startet
**Repo:** `Wuuzzaa/Skuld` (lokal `C:\Python\SKULD\Skuld-master`)
**Löst aus:** EINEN Prod-Deploy nach IONOS (82.165.128.161)

## Problem
1. IONOS-Prod-Telegram-Nachrichten (DB-Backup, Jobs, Deploy, Scanner) landen aktuell im
   Chat `-1003610692224` ("Produktiv System Skuld"). Sie sollen stattdessen in
   `-5463434000` ("Production System Ineos") landen.
2. Die Chat-ID darf nicht im Klartext im (öffentlichen) Repo stehen → als GitHub Secret.
3. Die OPS-Chat-ID (`TELEGRAM_OPS_CHAT_ID` / `telegram_chat_id_ops`) soll komplett aus
   dem Code verschwinden (User-Vorgabe). Sie ist bereits totes Wiring.
4. Das Feature `feature/roll-and-screen` (DeepSeek-Roll-Assistent als Chat) soll live gehen.

Alles zusammen in einem einzigen Prod-Deploy (User-Entscheidung "Beides zusammen").

## Verifizierte Faktenlage (2026-07-23)
- **Telegram getChat (über IONOS, Bot-Token server-lokal):**
  - `-1003610692224` = Kanal "Produktiv System Skuld" (aktuell in `.env` aktiv)
  - `-5463434000` = Gruppe "Production System Ineos" ← **Ziel**
  - `-5262458068` = "chat not found" (Bot nicht mehr drin) — home-Env
- **Chat-ID-Steuerkette IONOS:** `environments.yaml production.telegram_chat_id`
  → beim Deploy in `/opt/skuld/.env` als `TELEGRAM_CHAT_ID` geschrieben
  → gelesen von `src/send_alert.py`, `~/scripts/backup_db.py`, `monitor.sh`, `disk_report.sh`
  (alle lesen aus `.env`, KEINE hartkodierte ID mehr auf dem Server).
- **OPS-Fußabdruck:** nur 4 Zeilen in `deploy.yml` (106, 454, 498, 661). `environments.yaml`
  hat keinen `_ops`-Key → Output leer → `.env` hat `TELEGRAM_OPS_CHAT_ID=` (leer, ungenutzt).
- **Roll-Feature:** `feature/roll-and-screen` (dc1e69a), Probe-Merge in master konfliktfrei
  (`merge-tree`), master aktuell auf f85e9bc, Secret `DEEP_SEEK` gesetzt (22.07.).

## Lösung

### A) Prod-Chat-ID geheim + korrekt
- Neues GitHub Repository Secret **`PROD_TELEGRAM_CHAT_ID`** = `-5463434000`
  (Wert: nackte Zahl mit Minus, KEIN Leerzeichen, KEINE Quotes).
- `deploy.yml`: neue Env-Var `SECRET_PROD_TELEGRAM_CHAT_ID: ${{ secrets.PROD_TELEGRAM_CHAT_ID }}`
  im Deploy-Step. Effektive ID per Fallback:
  `EFFECTIVE_CHAT_ID="${SECRET_PROD_TELEGRAM_CHAT_ID:-$CFG_TELEGRAM_CHAT_ID}"`.
  - `.env`-Build (Z.497): `TELEGRAM_CHAT_ID=${EFFECTIVE_CHAT_ID}` (ohne Leerzeichen ums =).
  - Deploy-Nachrichten (Z.379, 563, 689, 705): dieselbe Fallback-Logik.
  - Damit greift das Secret nur bei production (dort gesetzt); home/hetzner haben es leer
    → Fallback auf `CFG_TELEGRAM_CHAT_ID` aus `environments.yaml` → unverändert.
- `environments.yaml`: `production.telegram_chat_id: ""` + Kommentar
  "→ kommt aus GitHub Secret PROD_TELEGRAM_CHAT_ID (geheim, nicht im Repo)".
  `home` behält `-5262458068`, `hetzner` behält `-1003610692224` (User-Entscheidung).

### B) OPS komplett entfernen
- 4 Zeilen aus `deploy.yml` löschen: 106, 454, 498, 661.
- Nach Deploy verschwindet `TELEGRAM_OPS_CHAT_ID=` aus `/opt/skuld/.env`.

### C) Roll-&-Screen live
- `feature/roll-and-screen` per Squash-Merge in master.

## Ausführungsreihenfolge (ein Prod-Deploy)
1. `gh secret set PROD_TELEGRAM_CHAT_ID` = `-5463434000` (via CLI, kein Copy-Paste-Fehler).
2. Branch `feat/telegram-chatid-secret-and-roll` von master.
3. Änderungen A+B committen (deploy.yml + environments.yaml).
4. `feature/roll-and-screen` mit `--squash` reinmergen (C), committen.
5. Branch → master pushen (Push löst EINEN Auto-Deploy nach IONOS aus).
6. Verifikation (SSH-Check + Testalert):
   - GitHub Actions grün.
   - `/opt/skuld/.env`: `TELEGRAM_CHAT_ID=-5463434000` (exakt, ohne Leerzeichen),
     keine `TELEGRAM_OPS_CHAT_ID`-Zeile mehr.
   - Markierter Testalert (über Server, Token bleibt server-lokal) landet in
     "Production System Ineos".
   - Seite "Roll & Screen" lädt (3 Tabs), DeepSeek-Roll-Assistent antwortet
     (kein "API key missing").

## Rückbaubarkeit
Git-Revert des master-Merge-Commits + `gh secret delete PROD_TELEGRAM_CHAT_ID` stellt den
alten Zustand her. `feature/roll-and-screen` bleibt als Branch erhalten.

## Nicht in Scope / offene Merker
- `replicate-db-to-home.yml:57` hartkodierte `-5262458068` bleibt (home-only Workflow,
  betrifft IONOS-Prod nicht).
- **Bot-Token-Rotation:** Token ist im Session-Transkript gelandet → optional später via
  BotFather rotieren + Secret/`.env` aktualisieren. Kein Blocker.
