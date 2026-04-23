# Workflow Overview

## Zielmodell

- Ein Push auf `master` deployt immer nur nach `production`.
- Der Homeserver wird niemals automatisch durch einen normalen `master`-Push getroffen.
- Homeserver-Operationen sind immer explizit manuell.

## Workflows

| File | Purpose | Trigger | Targets |
|---|---|---|---|
| `deploy.yml` | App deploy | Push auf `master` oder manueller `workflow_dispatch` | `production`, `dev-hetzner`, `home-server` |
| `trigger-jobs.yml` | Jobs auf genau einem Zielsystem ausfuehren | Manueller `workflow_dispatch` | `production`, `dev-hetzner`, `home-server` |
| `replicate-db-to-home.yml` | Backup aus einer Quell-Umgebung auf Homeserver-Datenbank wiederherstellen | Manueller `workflow_dispatch` | `production` oder `dev-hetzner` -> `home-server` |

## Was verwende ich wofuer?

### 1. Normaler Production Deploy

- Aktion: Push auf `master`
- Ergebnis: Deploy nach `production`
- Wichtig: Kein automatischer Deploy auf den Homeserver

### 2. Branch oder Commit auf Homeserver deployen

- Workflow: `deploy.yml`
- `target`: `home-server`
- `ref`: Branch, Tag oder SHA
- Ergebnis: Gewaehlter Code wird auf den Homeserver deployed

DB-Verbindung ist dabei branch-unabhaengig:

- Die DB-Konfiguration kommt immer aus dem gewaehlten GitHub Environment (`home-server`), nicht aus dem Branch.
- Beim Deploy werden Pflichtwerte fuer `POSTGRES_*` validiert.
- Fuer `home-server` werden sichere Defaults gesetzt, falls Variablen fehlen (`POSTGRES_HOST=postgres`, `POSTGRES_DB=Skuld`, `POSTGRES_USER=admin`, `POSTGRES_PORT=5432`).
- Nach dem Start wird ein echter SQL-Test (`select 1`) gegen die Ziel-DB ausgefuehrt. Schlaegt der fehl, faellt der Deploy sofort auf Fehler.

### 3. Datenbank auf Homeserver kopieren

- Workflow: `replicate-db-to-home.yml`
- `source_environment`: `production` oder `dev-hetzner`
- Zweck: Neuestes Backup der gewaehlten Quell-Umgebung laden und in `skuld_staging_db` auf dem Homeserver restoren
- Schutz: Workflow verlangt die Bestaetigung `RESTORE_HOME_DB`

Technischer Ablauf:

1. Job `fetch_backup` laeuft im gewaehlten Source-Environment (`production` oder `dev-hetzner`).
2. GitHub Runner verbindet sich per SSH auf den Quellserver und ermittelt das neueste Backup in `~/backups/postgres`.
3. Der Runner laedt die Backup-Datei per SCP herunter.
4. Die Datei wird als kurzlebiges GitHub-Artifact abgelegt.
5. Job `restore_home` laeuft im Environment `home-server`.
6. Der Runner laedt das Artifact, kopiert es per SCP auf den Homeserver und restored es in `skuld_staging_db`.

Wichtig:

- Es gibt keine direkte SSH-Verbindung Hetzner -> Homeserver.
- Die GitHub Action ist die Bruecke zwischen beiden Umgebungen.
- Dadurch koennen pro Environment unterschiedliche SSH-Keys verwendet werden.

Pflicht-Secrets fuer DB-Transfer:

- Environment `production` (bzw. `dev-hetzner`):
  - `DEPLOY_HOST` = Quellserver
  - `DEPLOY_USER` = SSH-User auf Quellserver (z. B. `deploy`)
  - `DEPLOY_SSH_KEY` = Private Key, dessen Public Key auf dem Quellserver in `~/.ssh/authorized_keys` liegt
- Environment `home-server`:
  - `DEPLOY_HOST` = Homeserver
  - `DEPLOY_USER` = SSH-User auf Homeserver
  - `DEPLOY_SSH_KEY` = Private Key, dessen Public Key auf dem Homeserver in `~/.ssh/authorized_keys` liegt

Quick-Check SSH pro Ziel:

1. Public Key des jeweiligen Environment-Keys auf dem Server hinterlegen (`authorized_keys`).
2. SSH-Login ohne Passwort testen.
3. Sicherstellen, dass der Quellserver Backups in `~/backups/postgres/skuld_*.sql.gz` oder `skuld_manual_*.sql.gz` hat.
4. Sicherstellen, dass auf dem Homeserver der Container `skuld_staging_db` laeuft.

### 4. Einzelne Jobs auf einem bestimmten Server ausfuehren

- Workflow: `trigger-jobs.yml`
- Beispiele:
  - `db_backup` auf `production`
  - `db_healthcheck` auf `home-server`
  - `stock_data_daily` auf `dev-hetzner`
- Wichtig: Dieser Workflow kopiert keine Datenbank zwischen Servern. Das macht nur `replicate-db-to-home.yml`.

## GitHub Environments

### `production`

Secrets: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `MASSIVE_API_KEY`, `MASSIVE_API_KEY_FLAT_FILES`, `POSTGRES_PASSWORD`, `AUTHELIA_JWT_SECRET`, `AUTHELIA_SESSION_SECRET`, `AUTHELIA_STORAGE_ENCRYPTION_KEY`, `AUTHELIA_PASSWORD_HASH`

Variables: `DOMAIN_NAME`, `AUTH_DOMAIN`, `TRAEFIK_ENTRYPOINT`, `TRAEFIK_CERTRESOLVER_LABEL_SKULD`, `TRAEFIK_CERTRESOLVER_LABEL_AUTHELIA`, `AUTH_SCHEME`, `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PORT`

### `dev-hetzner`

Gleiche Struktur wie `production`, aber mit Dev-spezifischen Werten.

### `home-server`

Gleiche Struktur wie `production`, aber mit Werten fuer den Homeserver / das Testsystem.

Besonderheiten:

- `deploy.yml` nutzt fuer `home-server` automatisch `docker-compose.yml` plus `docker-compose.testing.yml`.
- `trigger-jobs.yml` und `replicate-db-to-home.yml` nutzen auf dem Homeserver den Postgres-Container `skuld_staging_db`.

Wichtig fuer Branch-Deploys:

- Der Workflow `deploy.yml` akzeptiert fuer `ref` grundsaetzlich Branch, Tag oder SHA.
- Wenn ein beliebiger Branch nicht auf `home-server` deployed werden kann, liegt das nicht am YAML, sondern an den GitHub-Environment-Einstellungen.
- In GitHub unter `Settings -> Environments -> home-server -> Deployment branches and tags` muss dafuer `No restriction` gesetzt sein. Bei `Selected branches and tags` blockiert GitHub den Job bereits vor dem eigentlichen Deploy.

Hinweis zu Environment-Regeln:

- Fuer manuelle Deploys mit beliebigen `ref`-Werten auf `home-server` muss das Environment diese Refs erlauben (oder `No restriction`).