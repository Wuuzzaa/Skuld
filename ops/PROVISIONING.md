# Server Provisioning Guide

How to set up a blank Ubuntu server for SKULD deployments in under 10 minutes.

## Prerequisites

On your **local machine** (Windows/Mac):
- `gh` CLI installed and authenticated (`gh auth login`)
- SSH access to the new server (root or sudo user)

On the **new server**:
- Ubuntu 22.04 or 24.04 (fresh install)
- SSH access working (root@IP or user with sudo)
- Internet connectivity

## Quick Start (Copy-Paste)

```bash
# 1. Get a runner registration token (valid for 1 hour)
TOKEN=$(gh api repos/Wuuzzaa/Skuld/actions/runners/registration-token --jq .token)

# 2. Run the provisioning script on the new server
ssh root@SERVER_IP "RUNNER_TOKEN=$TOKEN RUNNER_LABELS=skuld-myserver bash -s" < ops/provision-server.sh

# 3. Add the server to ops/environments.yaml (see below)

# 4. Test deploy
skuld deploy myserver --branch master
```

That's it. The script handles everything: system updates, deploy user, SSH hardening, firewall, Docker, networks, app directory, and GitHub Actions Runner.

## Step-by-Step (Detailed)

### Step 1: Get Server Access

**Cloud (Hetzner/DigitalOcean):**
- Create an Ubuntu 22.04/24.04 server
- Note the IP address and root password/SSH key

**Physical Server:**
- Install Ubuntu Server (USB stick or PXE)
- Ensure SSH is enabled (`sudo apt install openssh-server`)
- Note the IP address

### Step 2: Generate Runner Token

On your local machine:

```bash
TOKEN=$(gh api repos/Wuuzzaa/Skuld/actions/runners/registration-token --jq .token)
echo $TOKEN
```

This token is valid for **1 hour**. Generate it right before running the script.

### Step 3: Run the Provisioning Script

```bash
ssh root@SERVER_IP "RUNNER_TOKEN=$TOKEN RUNNER_LABELS=skuld-myserver bash -s" < ops/provision-server.sh
```

**What happens:**
1. System packages updated
2. `deploy` user created (passwordless sudo, docker group)
3. SSH hardened (key-only, no root password login)
4. UFW firewall enabled (ports 22, 80, 443)
5. Docker + Docker Compose installed
6. Docker daemon configured (log rotation, iptables disabled)
7. Docker networks created (`web`, `postgres_setup_default`)
8. `/opt/skuld/` directory created
9. GitHub Actions Runner installed as systemd service
10. Validation checks run

The script is **idempotent** — safe to run again if something fails halfway.

### Step 4: Add Server to environments.yaml

Edit `ops/environments.yaml` and add a new block:

```yaml
myserver:
  host: SERVER_IP           # or "localhost" if runner is on the same machine
  user: deploy
  runner: self-hosted       # or "ubuntu-latest" for cloud with SSH deploy
  domain: myserver.skuld-options.com
  auth_domain: auth-myserver.skuld-options.com
  telegram_chat_id: "-YOUR_CHAT_ID"
  db_container: skuld_myserver_db
  compose_args: "-f docker-compose.yml -f docker-compose.testing.yml"
  traefik_entrypoint: web
  certresolver_skuld: "traefik.enable=true"
  certresolver_authelia: "traefik.enable=true"
  auth_scheme: http
  authelia: "true"
  skuld_middlewares: "force-https,authelia"
  skuld_env: Staging
  deploy_services: "skuld-frontend skuld-backend"
  skip_compose_down: "true"
  postgres_host: postgres
  postgres_db: Skuld
  postgres_user: admin
  postgres_port: "5432"
```

### Step 5: Deploy

```bash
skuld deploy myserver --branch master
```

Or without the skuld CLI:

```bash
gh workflow run deploy.yml --repo Wuuzzaa/Skuld --ref master -f target=myserver -f ref=master
```

## Configuration Options

All options are passed as environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `RUNNER_TOKEN` | (required) | GitHub runner registration token |
| `RUNNER_LABELS` | `self-hosted` | Comma-separated runner labels |
| `RUNNER_NAME` | hostname | Runner name in GitHub |
| `INSTALL_RUNNER` | `true` | Set `false` to skip runner |
| `INSTALL_TUNNEL` | `false` | Set `true` to install cloudflared |
| `GITHUB_REPO` | `Wuuzzaa/Skuld` | Target repository |
| `DEPLOY_USER` | `deploy` | Username to create |
| `SSH_AUTHORIZED_KEYS` | from conf | SSH public keys to authorize |

Example with all options:

```bash
ssh root@SERVER_IP "
  RUNNER_TOKEN=$TOKEN \
  RUNNER_LABELS=skuld-prod,linux \
  RUNNER_NAME=hetzner-prod \
  INSTALL_TUNNEL=true \
  bash -s" < ops/provision-server.sh
```

## Adding SSH Keys for Developers

Edit `ops/provision-server.conf` and add public keys to `SSH_AUTHORIZED_KEYS`, then re-run the script:

```bash
ssh root@SERVER_IP "bash -s" < ops/provision-server.sh
```

Or manually on the server:

```bash
echo "ssh-ed25519 AAAA... newdev@laptop" >> /home/deploy/.ssh/authorized_keys
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Script fails at Docker install | Check internet connectivity: `curl -I https://download.docker.com` |
| Runner not showing in GitHub | Token expired? Generate a new one and re-run |
| "Permission denied" after setup | SSH key not in authorized_keys? Check `provision-server.conf` |
| Deploy fails with "host unreachable" | Check `host` in environments.yaml. Use `localhost` for self-hosted runners |
| UFW blocks Docker traffic | Normal — Docker uses its own iptables rules (daemon.json: iptables=false) |

## Re-running the Script

The script is idempotent. You can re-run it anytime to:
- Add new SSH keys (update `provision-server.conf` first)
- Update the runner version (change `RUNNER_VERSION` in conf)
- Fix a broken configuration

```bash
ssh root@SERVER_IP "bash -s" < ops/provision-server.sh
```

No `RUNNER_TOKEN` needed for re-runs if the runner is already registered.

## Server Requirements (What the Script Creates)

After provisioning, the server has:

```
User:       deploy (groups: docker, sudo)
Sudo:       passwordless via /etc/sudoers.d/deploy-nopasswd
SSH:        key-only auth, no root password login
Firewall:   UFW active (22/tcp, 80/tcp, 443/tcp open)
Docker:     docker-ce + compose plugin + buildx
Networks:   web, postgres_setup_default (external)
App Dir:    /opt/skuld/ (owner: deploy:docker)
Runner:     /home/deploy/actions-runner/ (systemd service)
```
