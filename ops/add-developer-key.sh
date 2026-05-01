#!/bin/bash
# ============================================================================
# Add a developer's SSH public key to the production server.
#
# Usage (run from home server or any machine with deploy_key access):
#   ./add-developer-key.sh "ssh-ed25519 AAAAC3Nza... developer@laptop"
#
# Or pipe a public key file:
#   cat ~/.ssh/id_ed25519.pub | ./add-developer-key.sh
#
# This grants the developer read-only SSH access to download DB backups
# via the manage_local_db.ps1 script.
# ============================================================================

set -euo pipefail

HETZNER_HOST="91.98.156.116"
HETZNER_USER="deploy"

# Determine SSH key for connecting to Hetzner
if [ -f "$HOME/.ssh/deploy_key" ]; then
    SSH_KEY="$HOME/.ssh/deploy_key"
elif [ -f "$HOME/.ssh/Dell_homeserver" ]; then
    SSH_KEY="$HOME/.ssh/Dell_homeserver"
else
    echo "Error: No deploy_key or Dell_homeserver key found in ~/.ssh/"
    echo "Run this script from a machine that has SSH access to Hetzner."
    exit 1
fi

# Get the public key from argument or stdin
if [ $# -ge 1 ]; then
    PUBKEY="$*"
elif [ ! -t 0 ]; then
    PUBKEY=$(cat)
else
    echo "Usage: $0 <ssh-public-key-string>"
    echo "   or: cat ~/.ssh/id_ed25519.pub | $0"
    echo ""
    echo "Example:"
    echo "  $0 \"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA... user@laptop\""
    exit 1
fi

# Validate it looks like a public key
if ! echo "$PUBKEY" | grep -qE '^ssh-(ed25519|rsa|ecdsa)'; then
    echo "Error: Does not look like an SSH public key."
    echo "Got: $PUBKEY"
    exit 1
fi

echo "Adding key to ${HETZNER_USER}@${HETZNER_HOST}..."
echo "Key: ${PUBKEY:0:50}..."

ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no \
    "${HETZNER_USER}@${HETZNER_HOST}" \
    "grep -qF '${PUBKEY}' ~/.ssh/authorized_keys 2>/dev/null && echo 'Key already exists.' || (echo '${PUBKEY}' >> ~/.ssh/authorized_keys && echo 'Key added successfully.')"
