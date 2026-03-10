#!/bin/bash
###############################################################################
# SKULD Server Setup Script
# 
# Richtet einen frischen Hetzner-Server (Debian/Ubuntu) produktionsfertig ein.
# Muss als root ausgeführt werden: ssh root@<IP> 'bash -s' < setup_server.sh
#
# Was wird eingerichtet:
#   - deploy-User mit sudo + Passwort
#   - SSH-Hardening (kein Root-Login, kein Passwort-Auth)
#   - UFW Firewall (22, 80, 443, 51820/udp)
#   - fail2ban (SSH-Schutz)
#   - Docker + Docker Compose
#   - Swap (8 GB)
#   - Automatische Sicherheitsupdates (unattended-upgrades)
#   - sysctl-Hardening
#   - Timezone Europe/Berlin
###############################################################################

set -euo pipefail

# ─── Colors ─────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[⚠]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; }
info() { echo -e "${BLUE}[i]${NC} $*"; }
step() { echo -e "\n${BLUE}════════════════════════════════════════${NC}"; echo -e "${BLUE}  $*${NC}"; echo -e "${BLUE}════════════════════════════════════════${NC}"; }

# ─── Preflight checks ──────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    err "Dieses Script muss als root ausgeführt werden."
    exit 1
fi

# ─── Configuration ──────────────────────────────────────────────────────────
DEPLOY_USER="deploy"
SWAP_SIZE="8G"
TIMEZONE="Europe/Berlin"
SSH_PORT=22

# Ports for UFW
UFW_TCP_PORTS=(22 80 443)
UFW_UDP_PORTS=(51820)

# ─── Prompt for deploy password ────────────────────────────────────────────
step "Deploy-User Passwort festlegen"

while true; do
    read -s -p "Passwort für '$DEPLOY_USER' eingeben: " DEPLOY_PASS
    echo
    read -s -p "Passwort wiederholen: " DEPLOY_PASS_CONFIRM
    echo
    if [[ "$DEPLOY_PASS" == "$DEPLOY_PASS_CONFIRM" ]]; then
        if [[ ${#DEPLOY_PASS} -lt 8 ]]; then
            warn "Passwort muss mindestens 8 Zeichen haben. Nochmal."
            continue
        fi
        break
    else
        warn "Passwörter stimmen nicht überein. Nochmal."
    fi
done

###############################################################################
# 1. SYSTEM UPDATE
###############################################################################
step "1/10 — System aktualisieren"

export DEBIAN_FRONTEND=noninteractive

apt-get update -y
apt-get upgrade -y
apt-get dist-upgrade -y
apt-get autoremove -y
apt-get autoclean -y

log "System ist aktuell."

###############################################################################
# 2. ESSENTIAL PACKAGES
###############################################################################
step "2/10 — Pakete installieren"

apt-get install -y \
    curl \
    wget \
    git \
    nano \
    htop \
    iotop \
    ncdu \
    tree \
    tmux \
    zip \
    unzip \
    net-tools \
    dnsutils \
    ca-certificates \
    gnupg \
    lsb-release \
    software-properties-common \
    apt-transport-https \
    logrotate \
    rsync \
    jq \
    sudo

log "Alle Pakete installiert."

###############################################################################
# 3. DEPLOY USER
###############################################################################
step "3/10 — Deploy-User einrichten"

if id "$DEPLOY_USER" &>/dev/null; then
    warn "User '$DEPLOY_USER' existiert bereits — überspringe Erstellung."
else
    useradd -m -s /bin/bash -G sudo "$DEPLOY_USER"
    log "User '$DEPLOY_USER' erstellt."
fi

# Set password
echo "$DEPLOY_USER:$DEPLOY_PASS" | chpasswd
log "Passwort für '$DEPLOY_USER' gesetzt."

# Ensure sudo group
usermod -aG sudo "$DEPLOY_USER"

# Allow sudo with password (needed for deploy pipeline)
# But don't allow NOPASSWD for security
log "User '$DEPLOY_USER' hat sudo-Rechte (mit Passwort)."

# Copy SSH keys from root to deploy user
DEPLOY_HOME="/home/$DEPLOY_USER"
mkdir -p "$DEPLOY_HOME/.ssh"

if [[ -f /root/.ssh/authorized_keys ]]; then
    cp /root/.ssh/authorized_keys "$DEPLOY_HOME/.ssh/authorized_keys"
    log "SSH-Keys von root kopiert."
else
    warn "Keine authorized_keys bei root gefunden! Bitte manuell hinterlegen."
fi

chown -R "$DEPLOY_USER:$DEPLOY_USER" "$DEPLOY_HOME/.ssh"
chmod 700 "$DEPLOY_HOME/.ssh"
chmod 600 "$DEPLOY_HOME/.ssh/authorized_keys" 2>/dev/null || true

# Create app directory
mkdir -p /opt/skuld
chown "$DEPLOY_USER:$DEPLOY_USER" /opt/skuld
log "Verzeichnis /opt/skuld erstellt."

###############################################################################
# 4. SSH HARDENING
###############################################################################
step "4/10 — SSH härten"

SSHD_CONFIG="/etc/ssh/sshd_config"

# Backup original config
cp "$SSHD_CONFIG" "${SSHD_CONFIG}.bak.$(date +%Y%m%d%H%M%S)"

# Apply hardened settings
cat > /etc/ssh/sshd_config.d/99-skuld-hardening.conf <<'EOF'
# ─── SKULD SSH Hardening ─────────────────────────────────────
# Root-Login komplett deaktivieren
PermitRootLogin no

# Nur Key-Authentifizierung
PasswordAuthentication no
PubkeyAuthentication yes
ChallengeResponseAuthentication no
UsePAM yes

# Weitere Härtung
X11Forwarding no
MaxAuthTries 3
MaxSessions 5
LoginGraceTime 30
ClientAliveInterval 300
ClientAliveCountMax 2

# Nur deploy-User erlauben
AllowUsers deploy
EOF

# Detect SSH service name (ssh on Ubuntu 22.04+, sshd on older)
if systemctl list-units --type=service | grep -q "ssh.service"; then
    SSH_SERVICE="ssh"
elif systemctl list-units --type=service | grep -q "sshd.service"; then
    SSH_SERVICE="sshd"
else
    SSH_SERVICE="ssh"
fi

# Validate config before restarting
if sshd -t; then
    systemctl restart "$SSH_SERVICE"
    log "SSH gehärtet: Root-Login deaktiviert, nur Key-Auth für '$DEPLOY_USER'. (Service: $SSH_SERVICE)"
else
    err "SSH-Konfiguration fehlerhaft! Stelle Original wieder her."
    rm /etc/ssh/sshd_config.d/99-skuld-hardening.conf
    exit 1
fi

###############################################################################
# 5. FIREWALL (UFW)
###############################################################################
step "5/10 — Firewall (UFW) einrichten"

apt-get install -y ufw

# Reset to defaults
ufw --force reset

# Default policies
ufw default deny incoming
ufw default allow outgoing

# Allow configured ports
for port in "${UFW_TCP_PORTS[@]}"; do
    ufw allow "$port/tcp"
    log "Port $port/tcp erlaubt."
done

for port in "${UFW_UDP_PORTS[@]}"; do
    ufw allow "$port/udp"
    log "Port $port/udp erlaubt."
done

# Enable firewall
ufw --force enable
log "UFW aktiviert."

ufw status verbose

###############################################################################
# 6. FAIL2BAN
###############################################################################
step "6/10 — fail2ban einrichten"

apt-get install -y fail2ban

# Create jail.local (overrides jail.conf)
cat > /etc/fail2ban/jail.local <<EOF
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 3
backend  = systemd
banaction = ufw

# Email-Benachrichtigung (optional, deaktiviert)
# destemail = admin@skuld-options.com
# sender = fail2ban@skuld-options.com
# action = %(action_mwl)s

[sshd]
enabled  = true
port     = $SSH_PORT
filter   = sshd
logpath  = /var/log/auth.log
maxretry = 3
bantime  = 3600

# Recidive: Wiederholungstäter länger sperren
[recidive]
enabled  = true
filter   = recidive
logpath  = /var/log/fail2ban.log
bantime  = 604800
findtime = 86400
maxretry = 3
EOF

systemctl enable fail2ban
systemctl restart fail2ban
log "fail2ban konfiguriert und gestartet."

###############################################################################
# 7. DOCKER
###############################################################################
step "7/10 — Docker installieren"

if command -v docker &>/dev/null; then
    warn "Docker ist bereits installiert: $(docker --version)"
else
    # Official Docker GPG Key
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg | \
        gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    # Docker Repository
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") \
        $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
        tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    log "Docker installiert: $(docker --version)"
fi

# Add deploy user to docker group
usermod -aG docker "$DEPLOY_USER"
log "'$DEPLOY_USER' zur docker-Gruppe hinzugefügt."

# Docker daemon settings
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'EOF'
{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "storage-driver": "overlay2",
    "live-restore": true
}
EOF

systemctl enable docker
systemctl restart docker
log "Docker konfiguriert und gestartet."

###############################################################################
# 8. SWAP
###############################################################################
step "8/10 — Swap einrichten ($SWAP_SIZE)"

SWAPFILE="/swapfile"

if swapon --show | grep -q "$SWAPFILE"; then
    warn "Swap existiert bereits:"
    swapon --show
else
    fallocate -l "$SWAP_SIZE" "$SWAPFILE"
    chmod 600 "$SWAPFILE"
    mkswap "$SWAPFILE"
    swapon "$SWAPFILE"

    # Persist in fstab
    if ! grep -q "$SWAPFILE" /etc/fstab; then
        echo "$SWAPFILE none swap sw 0 0" >> /etc/fstab
    fi

    log "Swap erstellt und aktiviert:"
    swapon --show
fi

# Optimize swappiness (use swap less aggressively for server workloads)
sysctl vm.swappiness=10
echo "vm.swappiness=10" > /etc/sysctl.d/99-swap.conf

###############################################################################
# 9. SYSCTL HARDENING & AUTOMATIC UPDATES
###############################################################################
step "9/10 — Sysctl-Hardening & automatische Updates"

# Sysctl security settings
cat > /etc/sysctl.d/99-skuld-security.conf <<'EOF'
# ─── Network Security ───────────────────────────────────────
# Disable IP forwarding (enabled later by Docker if needed)
# net.ipv4.ip_forward = 1  # Docker needs this, so we leave it

# Prevent ICMP redirect attacks
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0

# Prevent source routing
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0

# Enable SYN flood protection
net.ipv4.tcp_syncookies = 1

# Log suspicious packets (martians)
net.ipv4.conf.all.log_martians = 1
net.ipv4.conf.default.log_martians = 1

# Ignore ICMP broadcast requests
net.ipv4.icmp_echo_ignore_broadcasts = 1

# Ignore bogus ICMP error responses
net.ipv4.icmp_ignore_bogus_error_responses = 1

# Enable Reverse Path Filtering (loose mode for Docker compatibility)
net.ipv4.conf.all.rp_filter = 2
net.ipv4.conf.default.rp_filter = 2

# Disable IPv6 if not needed (reduces attack surface)
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
EOF

sysctl --system
log "Sysctl-Hardening angewendet."

# Automatic security updates
apt-get install -y unattended-upgrades apt-listchanges

cat > /etc/apt/apt.conf.d/50unattended-upgrades <<'EOF'
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}";
    "${distro_id}:${distro_codename}-security";
    "${distro_id}ESMApps:${distro_codename}-apps-security";
    "${distro_id}ESM:${distro_codename}-infra-security";
};
Unattended-Upgrade::AutoFixInterruptedDpkg "true";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "false";
EOF

cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF

systemctl enable unattended-upgrades
log "Automatische Sicherheitsupdates aktiviert."

###############################################################################
# 10. TIMEZONE & LOCALE & FINAL TWEAKS
###############################################################################
step "10/10 — Timezone, Locale & finale Einrichtung"

# Timezone
timedatectl set-timezone "$TIMEZONE"
log "Timezone: $TIMEZONE"

# Create Docker networks that Skuld needs
docker network create web 2>/dev/null && log "Docker-Network 'web' erstellt." || warn "Network 'web' existiert bereits."
docker network create postgres_setup_default 2>/dev/null && log "Docker-Network 'postgres_setup_default' erstellt." || warn "Network 'postgres_setup_default' existiert bereits."

# Set bash as default shell for deploy
chsh -s /bin/bash "$DEPLOY_USER"

# Nice bash prompt for deploy user
cat >> "$DEPLOY_HOME/.bashrc" <<'EOF'

# ─── SKULD Server ───────────────────────────────────────────
export PS1='\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '
alias ll='ls -alF'
alias dc='docker compose'
alias dps='docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'
alias dlogs='docker compose logs --tail=50 -f'
alias skuld='cd /opt/skuld'
EOF

chown "$DEPLOY_USER:$DEPLOY_USER" "$DEPLOY_HOME/.bashrc"

###############################################################################
# SUMMARY
###############################################################################
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           SERVER-EINRICHTUNG ABGESCHLOSSEN              ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║${NC}                                                          ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  User:          ${BLUE}$DEPLOY_USER${NC}                               ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  SSH:           Key-Only, Root deaktiviert               ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  Firewall:      UFW aktiv (22, 80, 443, 51820/udp)      ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  fail2ban:      aktiv (SSH-Schutz + Recidive)            ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  Docker:        $(docker --version | cut -d' ' -f3 | tr -d ',')                            ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  Swap:          $SWAP_SIZE                                        ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  Timezone:      $TIMEZONE                           ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  Auto-Updates:  aktiviert (Sicherheit)                   ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  App-Dir:       /opt/skuld                               ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  Networks:      web, postgres_setup_default              ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}                                                          ${GREEN}║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║${NC}  ${YELLOW}WICHTIG: Root-Login ist jetzt deaktiviert!${NC}              ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  ${YELLOW}Nächster Login: ssh deploy@<IP>${NC}                        ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}                                                          ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  Teste JETZT in einem neuen Terminal:                    ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  ${BLUE}ssh deploy@$(curl -s ifconfig.me 2>/dev/null || echo '<SERVER-IP>')${NC}         ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}                                                          ${GREEN}║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
warn "BEVOR du diese SSH-Session schließt:"
warn "  1. Öffne ein NEUES Terminal"
warn "  2. Teste: ssh deploy@<SERVER-IP>"
warn "  3. Teste: sudo docker ps"
warn "  4. Erst wenn das funktioniert, diese Session beenden!"
echo ""
