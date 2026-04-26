# Workflow Overview

## Zielmodell

- Ein Push auf `master` deployt immer nur nach `production`.
- Der Homeserver wird niemals automatisch durch einen normalen `master`-Push getroffen.
- Homeserver-Operationen sind immer explizit manuell.
- Homeserver-Operationen laufen auf dem self-hosted Runner.

## Konfiguration

Alle environment-spezifischen Werte stehen in **`ops/environments.yaml`**.
Geteilte Secrets liegen als **Repository Secrets** (nicht pro Environment).

Ein neues Environment hinzufuegen = YAML editieren + pushen.

## Workflows

| File | Purpose | Trigger | Targets |
|---|---|---|---|
| `deploy.yml` | App deploy | Push auf `master` oder manueller `workflow_dispatch` | `production`, `home` |
| `trigger-jobs.yml` | Jobs auf genau einem Zielsystem ausfuehren | Manueller `workflow_dispatch` | `production`, `home` |
| `replicate-db-to-home.yml` | Backup aus Production auf Homeserver-DB restoren | Manueller `workflow_dispatch` | `production` -> `home` |

## Runner-Modell

- `production`: `ubuntu-latest` (GitHub-hosted) — SSH auf den Hetzner-Server
- `home`: `self-hosted` — laeuft direkt auf dem Heimserver

Wichtig: Der self-hosted Runner auf dem Homeserver muss online sein, sonst bleiben Home-Jobs in `queued`.

## Was verwende ich wofuer?

### 1. Normaler Production Deploy

- Aktion: Push auf `master`
- Ergebnis: Deploy nach `production`
- Kein automatischer Deploy auf den Homeserver

### 2. Branch auf Homeserver deployen

- Workflow: `deploy.yml` (manuell)
- Target: `home`
- Ref: Branch, Tag oder SHA
- Nur Frontend + Backend Container werden neu gebaut (DB, Traefik, Authelia bleiben)

### 3. Datenbank auf Homeserver kopieren

- Workflow: `replicate-db-to-home.yml`
- Source: `production`
- Ablauf: Self-hosted Runner SCP-t das neueste Backup direkt von Hetzner und restored es lokal
- Schutz: Workflow verlangt Bestaetigung `RESTORE_HOME_DB`

### 4. Einzelne Jobs ausfuehren

- Workflow: `trigger-jobs.yml`
- Beispiele: `db_backup`, `db_healthcheck`, `option_data`, `saturday_night`
- Target: `production` oder `home`

## Repository Secrets

| Secret | Beschreibung |
|---|---|
| `DEPLOY_SSH_KEY` | SSH Private Key fuer Server-Zugang |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token |
| `MASSIVE_API_KEY` | API-Key Massive-Daten |
| `MASSIVE_API_KEY_FLAT_FILES` | API-Key Flat-File-Daten |
| `POSTGRES_PASSWORD` | PostgreSQL Passwort |
| `AUTHELIA_JWT_SECRET` | Authelia JWT |
| `AUTHELIA_SESSION_SECRET` | Authelia Session |
| `AUTHELIA_STORAGE_ENCRYPTION_KEY` | Authelia Storage |
| `AUTHELIA_PASSWORD_HASH` | Authelia Passwort-Hash |

Telegram Chat IDs stehen in `ops/environments.yaml`, nicht in Secrets.
