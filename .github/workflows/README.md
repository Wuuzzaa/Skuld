# Workflow Overview

GitHub Actions laedt nur Workflow-Dateien direkt aus `.github/workflows/`.
Unterordner sind fuer aktive Workflows nicht moeglich. Deshalb erfolgt die Ordnung hier ueber:

- klare Dateinamen
- getrennte Targets pro Workflow
- diese Uebersichtsdoku

## Deployment Workflows

| File | Purpose | Trigger | Target |
|---|---|---|---|
| `deploy.yml` | Production deploy | push auf `master` | Hetzner Production |
| `deploy-dev.yml` | Dev deploy | manuell via `workflow_dispatch` | Hetzner Dev `Skuld-dev` |
| `deploy-testsystem.yml` | Staging/Testsystem deploy | push auf `testsystem` | Home Server |
| `deploy-monitoring-hetzner.yml` | Monitoring deploy | workflow-specific | Hetzner Monitoring |
| `deploy-monitoring-home.yml` | Monitoring deploy | workflow-specific | Home Monitoring |

## Utility Workflows

| File | Purpose |
|---|---|
| `debug-ssh.yml` | SSH/Connectivity Debugging |
| `refresh-testsystem.yml` | Testsystem refresh |
| `restore-helsinki-db.yml` | Restore DB snapshot from Helsinki flow |
| `trigger-jobs.yml` | Trigger scheduled/manual jobs |

## Recommended Convention

- `deploy.yml` bleibt nur fuer Produktion.
- Dev, Staging und Monitoring bekommen jeweils eigene Dateien.
- Environment-spezifische Zugangsdaten werden ueber GitHub Environments getrennt.
- Keine gemeinsamen Prod/Dev Secrets auf Repository-Ebene, wenn Trennung wichtig ist.

## GitHub Setup For `deploy-dev.yml`

Empfohlenes GitHub Environment: `dev-hetzner`

### Environment Secrets

- `DEPLOY_HOST`: `91.98.156.116`
- `DEPLOY_USER`: `deploy`
- `DEPLOY_SSH_KEY`: Private SSH-Key, dessen Public Key auf `Skuld-dev` in `authorized_keys` liegt

Optional als Dev-spezifische Overrides:

- `TELEGRAM_CHAT_ID_DEV`

Koennen auch auf Repository-Ebene verbleiben, wenn Dev und Prod dieselben Werte nutzen duerfen:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `MASSIVE_API_KEY`
- `MASSIVE_API_KEY_FLAT_FILES`
- `POSTGRES_PASSWORD`
- `AUTHELIA_JWT_SECRET`
- `AUTHELIA_SESSION_SECRET`
- `AUTHELIA_STORAGE_ENCRYPTION_KEY`
- `AUTHELIA_PASSWORD_HASH`

### Environment Variables

- `DOMAIN_NAME`
- `AUTH_DOMAIN`
- `TRAEFIK_ENTRYPOINT`
- `TRAEFIK_CERTRESOLVER_LABEL_SKULD`
- `TRAEFIK_CERTRESOLVER_LABEL_AUTHELIA`
- `AUTH_SCHEME`
- `POSTGRES_HOST`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PORT`

## Einheitliches Deployment-Modell

Alle Workflows nutzen eine flexible `mysudo`-Funktion:
- Wenn `DEPLOY_PASSWORD` als Secret existiert → Passwort-basiertes sudo
- Wenn nicht → normales sudo (NOPASSWD)

Damit funktionieren sowohl Helsinki (noch Passwort-sudo) als auch neue Server (NOPASSWD) ohne Aenderung.

`deploy-dev.yml` nutzt direkt `sudo` (Falkenstein hat NOPASSWD via Cloud-Init).

### Fuer Helsinki (optionale Migration)

Wenn Helsinki irgendwann auf NOPASSWD umgestellt wird:
1. `ops/fix-helsinki-sudoers.sh` ausfuehren
2. GitHub Secret `DEPLOY_PASSWORD` loeschen
3. Fertig – alle Workflows nutzen dann automatisch plain sudo