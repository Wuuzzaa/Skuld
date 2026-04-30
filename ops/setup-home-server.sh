#!/usr/bin/env bash
# ============================================================================
# DEPRECATED: Use ops/provision-server.sh instead!
#
# This script is kept for reference only. The new provision-server.sh handles:
#   - Everything this script does, plus:
#   - Docker installation from scratch
#   - Firewall (UFW) configuration
#   - SSH hardening
#   - GitHub Actions Runner installation
#   - Cloudflare Tunnel setup (optional)
#   - Works on both cloud VPS and physical servers
#
# Migration:
#   TOKEN=$(gh api repos/Wuuzzaa/Skuld/actions/runners/registration-token --jq .token)
#   ssh root@SERVER "RUNNER_TOKEN=$TOKEN RUNNER_LABELS=skuld-home bash -s" < ops/provision-server.sh
# ============================================================================
#
# --- ORIGINAL DESCRIPTION (for reference) ---
# setup-home-server.sh
#
# Makes the home server comply with the SKULD Deployment Contract:
#   - Creates 'deploy' user with passwordless sudo
#   - Sets up SSH key auth for deploy user
#   - Creates /opt/skuld/ with correct ownership
#   - Copies app files from ~/Skuld/ to /opt/skuld/
#   - Ensures Docker networks exist
#
# Run this AS daniel on the home server:
#   bash setup-home-server.sh
#
# Requires: sudo access (will prompt for password — last time you'll need it!)
# ============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }

DEPLOY_USER="deploy"
APP_DIR="/opt/skuld"
OLD_APP_DIR="/home/daniel/Skuld"
DIVIDER="================================================================"

echo "$DIVIDER"
echo "  SKULD Home Server Setup"
echo "  Making this server comply with the Deployment Contract"
echo "$DIVIDER"
echo ""

# Must run as daniel (not root)
if [ "$(whoami)" != "daniel" ]; then
  fail "Run this as 'daniel', not '$(whoami)'"
fi

# ── 1. Create deploy user ──────────────────────────────────────────────
echo "--- Step 1: Create '$DEPLOY_USER' user ---"
if id "$DEPLOY_USER" &>/dev/null; then
  ok "User '$DEPLOY_USER' already exists"
else
  sudo adduser --disabled-password --gecos "SKULD Deploy User" "$DEPLOY_USER"
  ok "Created user '$DEPLOY_USER'"
fi

# Add to required groups
for grp in docker sudo users; do
  if groups "$DEPLOY_USER" | grep -qw "$grp"; then
    ok "$DEPLOY_USER already in group '$grp'"
  else
    sudo usermod -aG "$grp" "$DEPLOY_USER"
    ok "Added $DEPLOY_USER to group '$grp'"
  fi
done

# ── 2. Passwordless sudo ───────────────────────────────────────────────
echo ""
echo "--- Step 2: Passwordless sudo ---"
SUDOERS_FILE="/etc/sudoers.d/deploy-nopasswd"
if [ -f "$SUDOERS_FILE" ]; then
  ok "Sudoers file already exists"
else
  echo "$DEPLOY_USER ALL=(ALL) NOPASSWD:ALL" | sudo tee "$SUDOERS_FILE" > /dev/null
  sudo chmod 440 "$SUDOERS_FILE"
  ok "Created $SUDOERS_FILE"
fi

# Validate
if sudo -u "$DEPLOY_USER" sudo -n true 2>/dev/null; then
  ok "Passwordless sudo works"
else
  warn "Passwordless sudo test failed — may need a fresh login"
fi

# ── 3. SSH key setup ───────────────────────────────────────────────────
echo ""
echo "--- Step 3: SSH key for $DEPLOY_USER ---"
DEPLOY_HOME="/home/$DEPLOY_USER"
DEPLOY_SSH_DIR="$DEPLOY_HOME/.ssh"

sudo mkdir -p "$DEPLOY_SSH_DIR"

# The deploy_key's public key — this is the key that GitHub Actions uses.
# Extracted from the private key on this server (~daniel/.ssh/deploy_key).
DEPLOY_PUBKEY=$(ssh-keygen -y -f /home/daniel/.ssh/deploy_key 2>/dev/null || true)

if [ -z "$DEPLOY_PUBKEY" ]; then
  fail "Could not extract public key from /home/daniel/.ssh/deploy_key"
fi

# Also add the Dell Homeserver key so you can still SSH in as deploy from your Windows machine
DELL_PUBKEY=""
if [ -f /home/daniel/.ssh/authorized_keys ]; then
  DELL_PUBKEY=$(grep "Dell Homeserver" /home/daniel/.ssh/authorized_keys || true)
fi

AUTH_KEYS_FILE="$DEPLOY_SSH_DIR/authorized_keys"
sudo touch "$AUTH_KEYS_FILE"

# Add deploy_key public key
if sudo grep -qF "$DEPLOY_PUBKEY" "$AUTH_KEYS_FILE" 2>/dev/null; then
  ok "deploy_key already authorized"
else
  echo "$DEPLOY_PUBKEY" | sudo tee -a "$AUTH_KEYS_FILE" > /dev/null
  ok "Added deploy_key public key"
fi

# Add Dell Homeserver key
if [ -n "$DELL_PUBKEY" ]; then
  if sudo grep -qF "Dell Homeserver" "$AUTH_KEYS_FILE" 2>/dev/null; then
    ok "Dell Homeserver key already authorized"
  else
    echo "$DELL_PUBKEY" | sudo tee -a "$AUTH_KEYS_FILE" > /dev/null
    ok "Added Dell Homeserver key"
  fi
fi

# Also copy the deploy_key itself so deploy user can reach Hetzner
if [ -f /home/daniel/.ssh/deploy_key ]; then
  sudo cp /home/daniel/.ssh/deploy_key "$DEPLOY_SSH_DIR/deploy_key"
  ok "Copied deploy_key to $DEPLOY_SSH_DIR/"
fi

# Copy known_hosts so SSH doesn't prompt
if [ -f /home/daniel/.ssh/known_hosts ]; then
  sudo cp /home/daniel/.ssh/known_hosts "$DEPLOY_SSH_DIR/known_hosts"
  ok "Copied known_hosts"
fi

# Fix permissions
sudo chown -R "$DEPLOY_USER:$DEPLOY_USER" "$DEPLOY_SSH_DIR"
sudo chmod 700 "$DEPLOY_SSH_DIR"
sudo chmod 600 "$AUTH_KEYS_FILE"
sudo chmod 600 "$DEPLOY_SSH_DIR/deploy_key" 2>/dev/null || true
ok "SSH permissions set"

# ── 4. Create /opt/skuld/ ──────────────────────────────────────────────
echo ""
echo "--- Step 4: Create $APP_DIR ---"
if [ -d "$APP_DIR" ]; then
  ok "$APP_DIR already exists"
else
  sudo mkdir -p "$APP_DIR"
  ok "Created $APP_DIR"
fi
sudo chown "$DEPLOY_USER:docker" "$APP_DIR"
ok "Ownership set to $DEPLOY_USER:docker"

# ── 5. Copy app files ──────────────────────────────────────────────────
echo ""
echo "--- Step 5: Copy files from $OLD_APP_DIR to $APP_DIR ---"
if [ -d "$OLD_APP_DIR" ]; then
  sudo rsync -a --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
    --exclude '.venv' --exclude 'logs/' \
    "$OLD_APP_DIR/" "$APP_DIR/"
  sudo chown -R "$DEPLOY_USER:docker" "$APP_DIR"
  ok "Files copied (containers NOT affected — they use Docker volumes)"
else
  warn "$OLD_APP_DIR does not exist — skipping copy"
fi

# ── 6. Docker networks ─────────────────────────────────────────────────
echo ""
echo "--- Step 6: Docker networks ---"
for net in web postgres_setup_default; do
  if docker network ls --format '{{.Name}}' | grep -qw "$net"; then
    ok "Network '$net' exists"
  else
    docker network create "$net"
    ok "Created network '$net'"
  fi
done

# ── 7. Update GitHub Actions runner SSH config ──────────────────────────
echo ""
echo "--- Step 7: SSH AllowUsers ---"
if sudo grep -q "AllowUsers" /etc/ssh/sshd_config; then
  if sudo grep "AllowUsers" /etc/ssh/sshd_config | grep -qw "$DEPLOY_USER"; then
    ok "$DEPLOY_USER already in AllowUsers"
  else
    # Add deploy to existing AllowUsers line
    sudo sed -i "s/^AllowUsers.*/& $DEPLOY_USER/" /etc/ssh/sshd_config
    sudo systemctl restart ssh 2>/dev/null || sudo systemctl restart sshd 2>/dev/null || true
    ok "Added $DEPLOY_USER to AllowUsers and restarted SSH"
  fi
else
  ok "No AllowUsers restriction in sshd_config — all users allowed"
fi

# ── 8. Validation ──────────────────────────────────────────────────────
echo ""
echo "$DIVIDER"
echo "  VALIDATION"
echo "$DIVIDER"
echo ""

# Check user exists and groups
if id "$DEPLOY_USER" &>/dev/null; then
  ok "User: $(id $DEPLOY_USER)"
else
  fail "User $DEPLOY_USER does not exist!"
fi

# Check sudo
if sudo -u "$DEPLOY_USER" sudo -n docker ps &>/dev/null; then
  ok "Passwordless sudo + docker works"
else
  warn "Could not verify sudo+docker — try logging in as deploy to test"
fi

# Check app dir
if [ -d "$APP_DIR" ] && [ -f "$APP_DIR/docker-compose.yml" ]; then
  ok "$APP_DIR has docker-compose.yml"
else
  warn "$APP_DIR/docker-compose.yml not found"
fi

# Check SSH auth
echo ""
echo "$DIVIDER"
echo "  DONE!"
echo "$DIVIDER"
echo ""
echo "  Next steps:"
echo "  1. Test SSH: ssh -i ~/.ssh/deploy_key deploy@localhost"
echo "  2. Test from Windows: ssh -i ~/.ssh/Dell_homeserver deploy@192.168.0.235"
echo "  3. Verify: sudo docker ps (as deploy, without password)"
echo ""
