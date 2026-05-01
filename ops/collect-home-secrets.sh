#!/usr/bin/env bash
# ============================================================================
# collect-home-secrets.sh
#
# Run this ON the home server (via SSH) to collect all values needed
# to recreate the GitHub Environment "home-server".
#
# Usage:
#   ssh <your-homeserver>
#   bash collect-home-secrets.sh
#
# Output: prints every secret/variable you need to paste into GitHub.
# ============================================================================
set -euo pipefail

DIVIDER="================================================================"
APP_DIR="/opt/skuld"
ENV_FILE="${APP_DIR}/.env"

echo "$DIVIDER"
echo "  SKULD Home-Server Secret Collector"
echo "$DIVIDER"
echo ""

# --- Helper ---
read_env() {
  local key="$1"
  if [ -f "$ENV_FILE" ]; then
    grep -m1 "^${key}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true
  fi
}

warn() { echo "  [!] $1"; }
ok()   { echo "  [OK] $1"; }

# ============================================================================
# 1. DEPLOY_SSH_KEY
# ============================================================================
echo "--- 1. DEPLOY_SSH_KEY ---"
DEPLOY_KEY=""
for keyfile in /home/deploy/.ssh/id_ed25519 /home/deploy/.ssh/id_rsa; do
  if [ -f "$keyfile" ]; then
    DEPLOY_KEY="$keyfile"
    break
  fi
done

if [ -n "$DEPLOY_KEY" ]; then
  ok "Found: $DEPLOY_KEY"
  echo ""
  echo "  >>> Copy everything between the BEGIN/END lines (inclusive):"
  echo ""
  sudo cat "$DEPLOY_KEY"
  echo ""
else
  warn "No SSH key found in /home/deploy/.ssh/"
  warn "Check manually: ls -la /home/deploy/.ssh/"
fi
echo ""

# ============================================================================
# 2. DEPLOY_USER + DEPLOY_HOST
# ============================================================================
echo "--- 2. DEPLOY_USER ---"
echo "  Value: deploy"
echo ""
echo "--- 3. DEPLOY_HOST ---"
echo "  Value: localhost"
echo "  (Self-hosted runner runs locally, so localhost is correct)"
echo ""

# ============================================================================
# 3. POSTGRES_PASSWORD (from existing .env)
# ============================================================================
echo "--- 4. POSTGRES_PASSWORD ---"
PG_PASS=$(read_env POSTGRES_PASSWORD)
if [ -n "$PG_PASS" ]; then
  ok "From $ENV_FILE:"
  echo "  Value: $PG_PASS"
else
  # Try reading from running container
  PG_PASS_CONTAINER=$(sudo docker exec skuld_staging_db bash -c 'echo $POSTGRES_PASSWORD' 2>/dev/null || true)
  if [ -n "$PG_PASS_CONTAINER" ]; then
    ok "From running container skuld_staging_db:"
    echo "  Value: $PG_PASS_CONTAINER"
  else
    warn "Not found in .env or running container."
    warn "Check: sudo docker inspect skuld_staging_db | grep POSTGRES_PASSWORD"
  fi
fi
echo ""

# ============================================================================
# 4. TELEGRAM (from existing .env)
# ============================================================================
echo "--- 5. TELEGRAM_BOT_TOKEN ---"
TG_TOKEN=$(read_env TELEGRAM_BOT_TOKEN)
if [ -n "$TG_TOKEN" ]; then
  ok "Value: $TG_TOKEN"
else
  warn "Not found in $ENV_FILE. Copy from production environment."
fi
echo ""

echo "--- 6. TELEGRAM_CHAT_ID ---"
TG_CHAT=$(read_env TELEGRAM_CHAT_ID)
if [ -n "$TG_CHAT" ]; then
  ok "Current value: $TG_CHAT"
  echo "  NOTE: Change this to your TEST channel ID if you want"
  echo "        test notifications in a separate chat!"
else
  warn "Not found in $ENV_FILE."
  warn "Set this to your TEST Telegram channel/chat ID."
fi
echo ""

# ============================================================================
# 5. MASSIVE API Keys (from existing .env)
# ============================================================================
echo "--- 7. MASSIVE_API_KEY ---"
MKEY=$(read_env MASSIVE_API_KEY)
if [ -n "$MKEY" ]; then
  ok "Value: $MKEY"
else
  warn "Not found. Copy from production environment."
fi
echo ""

echo "--- 8. MASSIVE_API_KEY_FLAT_FILES ---"
MKEY_FF=$(read_env MASSIVE_API_KEY_FLAT_FILES)
if [ -n "$MKEY_FF" ]; then
  ok "Value: $MKEY_FF"
else
  warn "Not found. Copy from production environment."
fi
echo ""

# ============================================================================
# SUMMARY: Variables (these are fixed values, not secrets)
# ============================================================================
echo "$DIVIDER"
echo "  VARIABLES (fixed values - just copy into GitHub)"
echo "$DIVIDER"
echo ""
echo "  DOMAIN_NAME                           = test.skuld-options.com"
echo "  AUTH_DOMAIN                            = auth-test.skuld-options.com"
echo "  TRAEFIK_ENTRYPOINT                     = web"
echo "  TRAEFIK_CERTRESOLVER_LABEL_SKULD       = (leave empty)"
echo "  TRAEFIK_CERTRESOLVER_LABEL_AUTHELIA    = (leave empty)"
echo "  AUTH_SCHEME                            = http"
echo "  POSTGRES_HOST                          = postgres"
echo "  POSTGRES_DB                            = Skuld"
echo "  POSTGRES_USER                          = admin"
echo "  POSTGRES_PORT                          = 5432"
echo ""

# ============================================================================
# SUMMARY: What's NOT needed
# ============================================================================
echo "$DIVIDER"
echo "  NOT NEEDED for home-server"
echo "$DIVIDER"
echo ""
echo "  - AUTHELIA_JWT_SECRET          (Authelia setup skipped for home-server)"
echo "  - AUTHELIA_SESSION_SECRET      (Authelia setup skipped for home-server)"
echo "  - AUTHELIA_STORAGE_ENCRYPTION_KEY"
echo "  - AUTHELIA_PASSWORD_HASH"
echo ""

# ============================================================================
# Quick health check
# ============================================================================
echo "$DIVIDER"
echo "  HEALTH CHECK"
echo "$DIVIDER"
echo ""

# Docker running?
if sudo docker ps &>/dev/null; then
  ok "Docker is running"
  # DB container?
  if sudo docker ps --format '{{.Names}}' | grep -q skuld_staging_db; then
    ok "skuld_staging_db container is running"
  else
    warn "skuld_staging_db container NOT running"
  fi
  # GitHub Actions runner?
  if pgrep -f "actions-runner" &>/dev/null; then
    ok "GitHub Actions runner is running"
  else
    warn "GitHub Actions runner NOT running"
  fi
else
  warn "Docker is NOT running"
fi

echo ""
echo "$DIVIDER"
echo "  Done. Copy the values above into:"
echo "  GitHub > Repo Settings > Environments > home-server > Secrets/Variables"
echo "$DIVIDER"
