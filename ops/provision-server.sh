#!/usr/bin/env bash
# ============================================================================
# provision-server.sh — SKULD Universal Server Provisioning
#
# Makes any blank Ubuntu 22.04/24.04 server deploy-ready for SKULD.
# Idempotent: safe to re-run at any time.
#
# Usage:
#   # From your local machine (pipe over SSH):
#   TOKEN=$(gh api repos/Wuuzzaa/Skuld/actions/runners/registration-token --jq .token)
#   ssh root@SERVER "RUNNER_TOKEN=$TOKEN RUNNER_LABELS=skuld-home bash -s" < ops/provision-server.sh
#
#   # Or directly on the server:
#   sudo RUNNER_TOKEN=xxx RUNNER_LABELS=skuld-home bash provision-server.sh
#
#   # Skip runner installation:
#   ssh root@SERVER "INSTALL_RUNNER=false bash -s" < ops/provision-server.sh
#
#   # With Cloudflare tunnel:
#   ssh root@SERVER "RUNNER_TOKEN=xxx INSTALL_TUNNEL=true bash -s" < ops/provision-server.sh
#
# Environment variables (all optional except RUNNER_TOKEN if installing runner):
#   RUNNER_TOKEN        — GitHub Actions runner registration token (required for runner)
#   RUNNER_LABELS       — Comma-separated runner labels (default: self-hosted)
#   RUNNER_NAME         — Runner name (default: hostname)
#   INSTALL_RUNNER      — Install GitHub Actions runner (default: true)
#   INSTALL_TUNNEL      — Install Cloudflare tunnel (default: false)
#   GITHUB_REPO         — Repository (default: Wuuzzaa/Skuld)
#   RUNNER_VERSION      — Runner version to install (default: 2.334.0)
#   DEPLOY_USER         — Deploy user name (default: deploy)
#   SSH_AUTHORIZED_KEYS — Newline-separated public keys to authorize
# ============================================================================
set -euo pipefail

# === Colors ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[!!]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }
step() { echo -e "\n${CYAN}=== $1 ===${NC}"; }

# === Configuration (override via env vars or provision-server.conf) ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" 2>/dev/null)" && pwd 2>/dev/null || echo "/tmp")"
if [ -f "$SCRIPT_DIR/provision-server.conf" ]; then
  source "$SCRIPT_DIR/provision-server.conf"
fi

DEPLOY_USER="${DEPLOY_USER:-deploy}"
APP_DIR="${APP_DIR:-/opt/skuld}"
GITHUB_REPO="${GITHUB_REPO:-Wuuzzaa/Skuld}"
RUNNER_VERSION="${RUNNER_VERSION:-2.334.0}"
RUNNER_TOKEN="${RUNNER_TOKEN:-}"
RUNNER_LABELS="${RUNNER_LABELS:-self-hosted}"
RUNNER_NAME="${RUNNER_NAME:-$(hostname)}"
INSTALL_RUNNER="${INSTALL_RUNNER:-true}"
INSTALL_TUNNEL="${INSTALL_TUNNEL:-false}"
DOCKER_NETWORKS="${DOCKER_NETWORKS:-web postgres_setup_default}"
UFW_ALLOW_PORTS="${UFW_ALLOW_PORTS:-22 80 443}"

# === Pre-flight checks ===
echo "================================================================"
echo "  SKULD Server Provisioning"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================================"
echo ""
echo "  Target:       $(hostname) ($(uname -m))"
echo "  Deploy user:  $DEPLOY_USER"
echo "  App dir:      $APP_DIR"
echo "  GitHub repo:  $GITHUB_REPO"
echo "  Runner:       $INSTALL_RUNNER (labels: $RUNNER_LABELS)"
echo "  Tunnel:       $INSTALL_TUNNEL"
echo ""

# Must be root
if [ "$(id -u)" -ne 0 ]; then
  fail "This script must run as root. Use: sudo bash provision-server.sh"
fi

# OS check
if [ ! -f /etc/os-release ]; then
  fail "Cannot detect OS. Only Ubuntu 22.04/24.04 supported."
fi
source /etc/os-release
if [ "$ID" != "ubuntu" ]; then
  fail "Unsupported OS: $ID. Only Ubuntu supported."
fi
UBUNTU_MAJOR="${VERSION_ID%%.*}"
if [ "$UBUNTU_MAJOR" -lt 22 ]; then
  fail "Ubuntu $VERSION_ID too old. Minimum: 22.04"
fi
ok "OS: Ubuntu $VERSION_ID ($PRETTY_NAME)"

# ============================================================================
# MODULE 1: System update
# ============================================================================
step "1/10 System update"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
  curl wget git jq unzip apt-transport-https \
  ca-certificates gnupg lsb-release software-properties-common \
  rsync htop nano
ok "System packages updated"

# ============================================================================
# MODULE 2: Deploy user
# ============================================================================
step "2/10 Deploy user ($DEPLOY_USER)"

if id "$DEPLOY_USER" &>/dev/null; then
  ok "User '$DEPLOY_USER' already exists"
else
  useradd -m -s /bin/bash "$DEPLOY_USER"
  ok "Created user '$DEPLOY_USER'"
fi

# Ensure groups exist
getent group docker &>/dev/null || groupadd docker
getent group sudo &>/dev/null || true

# Add to groups
for grp in docker sudo; do
  if id -nG "$DEPLOY_USER" | grep -qw "$grp"; then
    ok "$DEPLOY_USER already in '$grp'"
  else
    usermod -aG "$grp" "$DEPLOY_USER"
    ok "Added $DEPLOY_USER to '$grp'"
  fi
done

# Passwordless sudo
SUDOERS_FILE="/etc/sudoers.d/deploy-nopasswd"
if [ -f "$SUDOERS_FILE" ]; then
  ok "Sudoers file exists"
else
  echo "$DEPLOY_USER ALL=(ALL) NOPASSWD:ALL" > "$SUDOERS_FILE"
  chmod 440 "$SUDOERS_FILE"
  ok "Passwordless sudo configured"
fi

# ============================================================================
# MODULE 3: SSH hardening
# ============================================================================
step "3/10 SSH configuration"

DEPLOY_HOME="/home/$DEPLOY_USER"
DEPLOY_SSH_DIR="$DEPLOY_HOME/.ssh"
mkdir -p "$DEPLOY_SSH_DIR"

# Add authorized keys if provided
AUTH_KEYS_FILE="$DEPLOY_SSH_DIR/authorized_keys"
touch "$AUTH_KEYS_FILE"

if [ -n "${SSH_AUTHORIZED_KEYS:-}" ]; then
  while IFS= read -r key; do
    [ -z "$key" ] && continue
    if grep -qF "$key" "$AUTH_KEYS_FILE" 2>/dev/null; then
      ok "Key already authorized: ${key:0:40}..."
    else
      echo "$key" >> "$AUTH_KEYS_FILE"
      ok "Added key: ${key:0:40}..."
    fi
  done <<< "$SSH_AUTHORIZED_KEYS"
fi

# Fix ownership and permissions
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$DEPLOY_SSH_DIR"
chmod 700 "$DEPLOY_SSH_DIR"
chmod 600 "$AUTH_KEYS_FILE"
ok "SSH directory permissions set"

# Harden SSHD (only if not already done)
SSHD_CONFIG="/etc/ssh/sshd_config"
SSHD_CHANGED=false

harden_sshd() {
  local key="$1" value="$2"
  if grep -q "^${key}\s*${value}" "$SSHD_CONFIG" 2>/dev/null; then
    return 0
  fi
  # Comment out existing line and add new one
  sed -i "s/^#*${key}\s.*/#&/" "$SSHD_CONFIG"
  echo "${key} ${value}" >> "$SSHD_CONFIG"
  SSHD_CHANGED=true
}

harden_sshd "PermitRootLogin" "prohibit-password"
harden_sshd "PasswordAuthentication" "no"
harden_sshd "PubkeyAuthentication" "yes"
harden_sshd "X11Forwarding" "no"

if [ "$SSHD_CHANGED" = true ]; then
  systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null || true
  ok "SSHD hardened and restarted"
else
  ok "SSHD already hardened"
fi

# ============================================================================
# MODULE 4: Firewall (UFW)
# ============================================================================
step "4/10 Firewall (UFW)"

if ! command -v ufw &>/dev/null; then
  apt-get install -y -qq ufw
fi

# Configure UFW
ufw default deny incoming &>/dev/null
ufw default allow outgoing &>/dev/null

for port in $UFW_ALLOW_PORTS; do
  ufw allow "$port/tcp" &>/dev/null
  ok "Port $port/tcp allowed"
done

# Enable UFW (non-interactive)
if ufw status | grep -q "Status: active"; then
  ok "UFW already active"
else
  echo "y" | ufw enable &>/dev/null
  ok "UFW enabled"
fi

# ============================================================================
# MODULE 5: Docker
# ============================================================================
step "5/10 Docker"

if command -v docker &>/dev/null; then
  DOCKER_VER=$(docker --version 2>/dev/null | awk '{print $3}' | tr -d ',')
  ok "Docker already installed ($DOCKER_VER)"
else
  # Add Docker's official GPG key
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc

  # Add Docker repo
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
    tee /etc/apt/sources.list.d/docker.list > /dev/null

  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  ok "Docker installed ($(docker --version | awk '{print $3}' | tr -d ','))"
fi

# Ensure Docker is running
systemctl enable docker &>/dev/null
systemctl start docker &>/dev/null
ok "Docker service running"

# ============================================================================
# MODULE 6: Docker daemon configuration
# ============================================================================
step "6/10 Docker daemon config"

DAEMON_JSON="/etc/docker/daemon.json"
DESIRED_CONFIG='{
  "iptables": false,
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}'

if [ -f "$DAEMON_JSON" ]; then
  ok "daemon.json already exists"
else
  echo "$DESIRED_CONFIG" > "$DAEMON_JSON"
  systemctl restart docker
  ok "daemon.json created, Docker restarted"
fi

# ============================================================================
# MODULE 7: Docker networks
# ============================================================================
step "7/10 Docker networks"

for net in $DOCKER_NETWORKS; do
  if docker network ls --format '{{.Name}}' | grep -qw "$net"; then
    ok "Network '$net' exists"
  else
    docker network create "$net"
    ok "Created network '$net'"
  fi
done

# ============================================================================
# MODULE 8: Application directory
# ============================================================================
step "8/10 Application directory ($APP_DIR)"

if [ -d "$APP_DIR" ]; then
  ok "$APP_DIR exists"
else
  mkdir -p "$APP_DIR"
  ok "Created $APP_DIR"
fi

mkdir -p "$APP_DIR/logs"
chown -R "$DEPLOY_USER:docker" "$APP_DIR"
ok "Ownership: $DEPLOY_USER:docker"

# ============================================================================
# MODULE 9: GitHub Actions Runner
# ============================================================================
step "9/10 GitHub Actions Runner"

if [ "$INSTALL_RUNNER" != "true" ]; then
  ok "Runner installation skipped (INSTALL_RUNNER=$INSTALL_RUNNER)"
else
  if [ -z "$RUNNER_TOKEN" ]; then
    warn "RUNNER_TOKEN not set! Skipping runner installation."
    warn "Get a token: gh api repos/$GITHUB_REPO/actions/runners/registration-token --jq .token"
  else
    RUNNER_HOME="/home/$DEPLOY_USER/actions-runner"
    RUNNER_ARCH="x64"
    # Detect ARM
    if [ "$(uname -m)" = "aarch64" ]; then
      RUNNER_ARCH="arm64"
    fi

    RUNNER_TAR="actions-runner-linux-${RUNNER_ARCH}-${RUNNER_VERSION}.tar.gz"
    RUNNER_URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${RUNNER_TAR}"

    if [ -f "$RUNNER_HOME/.runner" ]; then
      ok "Runner already configured at $RUNNER_HOME"
    else
      # Download runner
      mkdir -p "$RUNNER_HOME"
      cd "$RUNNER_HOME"

      if [ ! -f "$RUNNER_TAR" ]; then
        echo "  Downloading runner v${RUNNER_VERSION} (${RUNNER_ARCH})..."
        curl -sL "$RUNNER_URL" -o "$RUNNER_TAR"
        ok "Downloaded runner"
      fi

      # Extract
      tar xzf "$RUNNER_TAR"
      rm -f "$RUNNER_TAR"
      ok "Extracted runner"

      # Configure (as deploy user)
      chown -R "$DEPLOY_USER:$DEPLOY_USER" "$RUNNER_HOME"
      su - "$DEPLOY_USER" -c "cd $RUNNER_HOME && ./config.sh \
        --url https://github.com/$GITHUB_REPO \
        --token $RUNNER_TOKEN \
        --name $RUNNER_NAME \
        --labels $RUNNER_LABELS \
        --unattended \
        --replace"
      ok "Runner configured (name: $RUNNER_NAME, labels: $RUNNER_LABELS)"
    fi

    # Install as systemd service
    SERVICE_FILE="/etc/systemd/system/actions.runner.${GITHUB_REPO//\//-}.${RUNNER_NAME}.service"
    if [ -f "$SERVICE_FILE" ]; then
      ok "Runner service already installed"
    else
      cd "$RUNNER_HOME"
      ./svc.sh install "$DEPLOY_USER"
      ok "Runner service installed"
    fi

    # Start service
    ./svc.sh start 2>/dev/null || true
    ok "Runner service started"
  fi
fi

# ============================================================================
# MODULE 10: Cloudflare Tunnel (optional)
# ============================================================================
step "10/10 Cloudflare Tunnel"

if [ "$INSTALL_TUNNEL" != "true" ]; then
  ok "Tunnel installation skipped (INSTALL_TUNNEL=$INSTALL_TUNNEL)"
else
  if command -v cloudflared &>/dev/null; then
    ok "cloudflared already installed ($(cloudflared --version 2>&1 | head -1))"
  else
    # Install cloudflared
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | \
      tee /usr/share/keyrings/cloudflare-main.gpg > /dev/null
    echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" | \
      tee /etc/apt/sources.list.d/cloudflared.list > /dev/null
    apt-get update -qq
    apt-get install -y -qq cloudflared
    ok "cloudflared installed"
  fi
  warn "Tunnel config must be set up manually: cloudflared tunnel login"
fi

# ============================================================================
# VALIDATION
# ============================================================================
echo ""
echo "================================================================"
echo "  VALIDATION"
echo "================================================================"
echo ""

ERRORS=0

# User
if id "$DEPLOY_USER" &>/dev/null; then
  ok "User: $(id $DEPLOY_USER)"
else
  warn "User $DEPLOY_USER missing!"; ERRORS=$((ERRORS+1))
fi

# Sudo
if su - "$DEPLOY_USER" -c "sudo -n true" 2>/dev/null; then
  ok "Passwordless sudo works"
else
  warn "Passwordless sudo failed"; ERRORS=$((ERRORS+1))
fi

# Docker
if su - "$DEPLOY_USER" -c "docker ps" &>/dev/null; then
  ok "Docker accessible by $DEPLOY_USER"
else
  warn "Docker not accessible by $DEPLOY_USER"; ERRORS=$((ERRORS+1))
fi

# Networks
for net in $DOCKER_NETWORKS; do
  if docker network ls --format '{{.Name}}' | grep -qw "$net"; then
    ok "Network '$net' exists"
  else
    warn "Network '$net' missing!"; ERRORS=$((ERRORS+1))
  fi
done

# App dir
if [ -d "$APP_DIR" ]; then
  ok "$APP_DIR exists (owner: $(stat -c '%U:%G' $APP_DIR))"
else
  warn "$APP_DIR missing!"; ERRORS=$((ERRORS+1))
fi

# UFW
if ufw status | grep -q "Status: active"; then
  ok "Firewall active"
else
  warn "Firewall not active"; ERRORS=$((ERRORS+1))
fi

# Runner
if [ "$INSTALL_RUNNER" = "true" ] && [ -n "$RUNNER_TOKEN" ]; then
  if systemctl is-active --quiet "actions.runner.*" 2>/dev/null; then
    ok "GitHub Actions Runner running"
  else
    warn "Runner service not active"; ERRORS=$((ERRORS+1))
  fi
fi

# Summary
echo ""
echo "================================================================"
if [ "$ERRORS" -eq 0 ]; then
  echo -e "  ${GREEN}SERVER READY FOR SKULD DEPLOYS${NC}"
else
  echo -e "  ${YELLOW}COMPLETED WITH $ERRORS WARNING(S)${NC}"
fi
echo "================================================================"
echo ""
echo "  Next steps:"
echo "  1. Add this server to ops/environments.yaml"
echo "  2. Add DEPLOY_SSH_KEY to GitHub repo secrets (if not done)"
echo "  3. Test deploy: skuld deploy <env-name> --branch master"
echo ""
echo "  SSH test: ssh -i ~/.ssh/YOUR_KEY $DEPLOY_USER@$(hostname -I | awk '{print $1}')"
echo ""
