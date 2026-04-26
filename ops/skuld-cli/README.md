# skuld-cli

CLI for deploying and managing SKULD environments via GitHub Actions.

Every command triggers the corresponding GitHub Actions workflow -- no developer
needs direct SSH access or server credentials.

## What You Need on Your Machine

1. **Python 3.10+**
2. **GitHub CLI** (`gh`): https://cli.github.com/
3. Run `gh auth login` once
4. Push access to the `Wuuzzaa/Skuld` repository

That's it. No SSH keys, no server IPs, no `.env` files, no Docker.

## Installation

```bash
cd ops/skuld-cli
pip install -e .
```

Verify everything is set up:

```bash
skuld doctor
```

## Commands

### Deploy

```bash
# Deploy master to production (Hetzner)
skuld deploy production

# Deploy a feature branch to the home server
skuld deploy home --branch feature/my-feature

# Trigger without watching logs
skuld deploy home --no-watch
```

### Database

```bash
# Create a backup on production
skuld db backup production

# Replicate production DB to home server (prompts for confirmation)
skuld db replicate --source production

# Skip the confirmation prompt
skuld db replicate --source production --confirm

# Run a DB health check
skuld db healthcheck production
skuld db healthcheck home
```

### Data Collection Jobs

```bash
# Trigger a data collection job
skuld jobs run production option_data
skuld jobs run home saturday_night

# Dry run (show what would execute)
skuld jobs run production stock_data_daily --dry-run
```

Available jobs: `saturday_night`, `option_data`, `market_start_mid_end`,
`stock_data_daily`, `historization`

### Status & Monitoring

```bash
# Check prerequisites
skuld doctor

# Show environments and recent deploy runs
skuld status

# Watch the latest deploy
skuld watch deploy.yml
```

## How It Works

```
Developer laptop                 GitHub Actions                   Servers
─────────────────               ──────────────                   ───────
skuld deploy home ──────> gh workflow run deploy.yml
                                      │
                                      ├─ ubuntu-latest runner
                                      │  (rsync, SSH to Hetzner)
                                      │
                                      └─ self-hosted runner        Home Server
                                         (Docker build & up) ────> (Cloudflare Tunnel)
```

The CLI is a thin wrapper around `gh workflow run`. It:

1. Reads `ops/environments.yaml` to map friendly names (`production`, `home`)
   to their server configuration
2. Calls `gh workflow run <workflow>.yml` with the right inputs
3. Streams logs via `gh run watch` until completion

No SSH keys, server IPs, or secrets touch developer machines. Everything
flows through GitHub Actions + Repository Secrets.

### How DB Replication Works

```
skuld db replicate --source production

Hetzner (production)
    │
    ↓ SCP (direct from self-hosted runner)
Home Server (self-hosted runner)
    │
    ↓ docker exec psql restore
PostgreSQL container (skuld_staging_db)
```

The self-hosted GitHub Actions runner runs ON the home server, so it can
SCP backups directly from Hetzner and reach the local Docker containers.
No GitHub Artifacts needed -- the transfer is direct server-to-server.

## Adding a New Server

1. Add a block to `ops/environments.yaml`:

```yaml
  my-new-server:
    host: 1.2.3.4
    user: deploy
    runner: ubuntu-latest
    domain: new.skuld-options.com
    telegram_chat_id: "-123456"
    db_container: my-db-container
    compose_args: "-f docker-compose.yml"
    skuld_env: NewEnv
    deploy_services: ""
    skip_compose_down: false
```

2. Update `ENV_NAMES` in `cli.py` to include the new name
3. Add the name to workflow dropdown options in `.github/workflows/*.yml`
4. Commit and push -- done!

No GitHub Environment to create, no Secrets to copy, no Variables to maintain.
