# Workflow Overview

## Workflows

| File | Purpose | Trigger | Target |
|---|---|---|---|
| `deploy.yml` | Production deploy | push auf `master` | Hetzner Production |
| `deploy-dev.yml` | Dev deploy | manuell via `workflow_dispatch` | Hetzner Dev |
| `trigger-jobs.yml` | Manuelle Jobs (Data Collection, DB Backup, Healthcheck) | manuell via `workflow_dispatch` | Production / Dev |

## Deployment-Modell

- Ein aktiver Hetzner-Server pro Environment (Production / Dev).
- Environment-spezifische Zugangsdaten ueber GitHub Environments getrennt.
- Alle Server nutzen NOPASSWD sudo fuer den `deploy` User.
- `deploy.yml` nutzt eine flexible `mysudo`-Funktion (Passwort-sudo falls `DEPLOY_PASSWORD` existiert, sonst plain sudo).