# Workflow Overview

## Workflows

| File | Purpose | Trigger | Target |
|---|---|---|---|
| `deploy.yml` | App deploy | push auf `master` (auto → production) ODER manuell `workflow_dispatch` (production / dev) | Hetzner via GitHub Environment |
| `trigger-jobs.yml` | Manuelle Jobs (Data Collection, DB Backup, Healthcheck) | manuell via `workflow_dispatch` | production / dev |

## Deployment-Modell

- **Ein Workflow fuer alle Environments** – deploy.yml entscheidet anhand `inputs.target` (oder auto bei push).
- GitHub Environments steuern Secrets und Variablen pro Server.
- `mysudo`-Funktion fuer sudo-Kompatibilitaet (NOPASSWD oder Passwort).

## GitHub Environments

### `production`

**Secrets:** `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_PASSWORD` (optional, nur bei Passwort-sudo), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `MASSIVE_API_KEY`, `MASSIVE_API_KEY_FLAT_FILES`, `POSTGRES_PASSWORD`, `AUTHELIA_JWT_SECRET`, `AUTHELIA_SESSION_SECRET`, `AUTHELIA_STORAGE_ENCRYPTION_KEY`, `AUTHELIA_PASSWORD_HASH`

**Variables:** `DOMAIN_NAME`, `AUTH_DOMAIN`, `TRAEFIK_ENTRYPOINT`, `TRAEFIK_CERTRESOLVER_LABEL_SKULD`, `TRAEFIK_CERTRESOLVER_LABEL_AUTHELIA`, `AUTH_SCHEME`, `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PORT`

### `dev-hetzner`

Gleiche Secrets und Variables wie `production`, aber mit Dev-spezifischen Werten (anderer Host, ggf. andere Domain).