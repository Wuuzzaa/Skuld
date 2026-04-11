#cloud-config
# =============================================================================
# Skuld Server – Cloud-Init Template für Hetzner
# =============================================================================
# VERWENDUNG:
#   Das PowerShell-Script "provision-hetzner.ps1" ersetzt die Platzhalter
#   automatisch. Manuelle Nutzung:
#     1. Alle Platzhalterwerte ersetzen
#     2. In der Hetzner Cloud Console unter "Cloud config" einfügen
#        ODER via API / hcloud CLI übergeben
#
# VORAUSSETZUNGEN:
#   - Tailscale Auth-Key generieren (Einmal-Key, ephemeral empfohlen):
#     https://login.tailscale.com/admin/settings/keys
#   - SSH Public Key bereithalten
#   - Wenn Tailscale nicht genutzt wird, setzt das Provisioning-Script
#     automatisch oeffentliche SSH-Regeln ein.
# =============================================================================

# --- Benutzer ---
users:
  - name: holu
    groups: users, admin, sudo, docker
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    ssh_authorized_keys:
      - <SSH_PUBLIC_KEY>
  - name: deploy
    groups: users, docker, sudo
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    ssh_authorized_keys:
      - <SSH_PUBLIC_KEY>

# --- Pakete ---
packages:
  - fail2ban
  - ufw
  - curl
  - git
  - apt-transport-https
  - ca-certificates
  - gnupg
  - lsb-release
  - unattended-upgrades
  - jq

package_update: true
package_upgrade: true

# --- Swap anlegen (sinnvoll bei kleinen CX-Instanzen) ---
swap:
  filename: /swapfile
  size: 2G

# --- Dateien schreiben ---
write_files:
  # Automatische Sicherheits-Updates
  - path: /etc/apt/apt.conf.d/20auto-upgrades
    content: |
      APT::Periodic::Update-Package-Lists "1";
      APT::Periodic::Unattended-Upgrade "1";
      APT::Periodic::AutocleanInterval "7";

  # Docker + UFW Fix: Docker darf UFW-Regeln NICHT umgehen
  # Ohne diesen Fix ignoriert Docker die UFW-Firewall komplett!
  - path: /etc/docker/daemon.json
    content: |
      {
        "iptables": false,
        "log-driver": "json-file",
        "log-opts": {
          "max-size": "10m",
          "max-file": "3"
        }
      }

  # UFW AFTER.RULES für Docker-Netzwerk-NAT
  # Nötig damit Container nach außen kommunizieren können wenn iptables=false
  - path: /etc/ufw/after.rules.docker
    content: |
      # NAT table rules for Docker
      *nat
      :POSTROUTING ACCEPT [0:0]
      -A POSTROUTING -s 172.16.0.0/12 -o eth0 -j MASQUERADE
      -A POSTROUTING -s 192.168.0.0/16 -o eth0 -j MASQUERADE
      COMMIT

  # fail2ban Konfiguration
  - path: /etc/fail2ban/jail.local
    content: |
      [sshd]
      enabled = true
      banaction = iptables-multiport
      maxretry = 3
      bantime = 3600
      findtime = 600

# --- Befehle ausführen ---
runcmd:
  # ==========================================================================
  # 1. Docker CE installieren (offizielles Repository)
  # ==========================================================================
  - install -m 0755 -d /etc/apt/keyrings
  - curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  - chmod a+r /etc/apt/keyrings/docker.asc
  - echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
  - apt-get update
  - apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

  # Docker-Netzwerke für Skuld anlegen
  - docker network create web || true
  - docker network create postgres_setup_default || true

  # ==========================================================================
  # 2. Tailscale installieren (VOR UFW, sonst sperrt man sich aus!)
  # ==========================================================================
<TAILSCALE_INSTALL_BLOCK>

  # ==========================================================================
  # 3. UFW Firewall konfigurieren
  # ==========================================================================
<SSH_FIREWALL_BLOCK>

  # Docker Registry (für Kamal) - nur Tailscale
  - ufw allow from 100.64.0.0/10 to any port 5555
  - ufw allow from fd7a:115c:a1e0::/48 to any port 5555

  # Web Traffic (HTTP/HTTPS) - öffentlich
  - ufw allow 80/tcp
  - ufw allow 443/tcp

  # Docker-Container untereinander kommunizieren lassen
  - ufw allow from 172.16.0.0/12
  - ufw allow from 192.168.0.0/16

  # Docker NAT-Regeln an UFW anhängen
  - cat /etc/ufw/after.rules.docker >> /etc/ufw/after.rules

  # Firewall aktivieren
  - echo "y" | ufw enable

  # ==========================================================================
  # 4. fail2ban aktivieren
  # ==========================================================================
  - systemctl enable fail2ban
  - systemctl start fail2ban

  # ==========================================================================
  # 5. SSH härten
  # ==========================================================================
  # WICHTIG: sed -E (Extended Regex) statt sed -e für (|) Syntax!
  - sed -i -E 's/^#?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
  - sed -i -E 's/^#?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
  - sed -i -E 's/^#?KbdInteractiveAuthentication .*/KbdInteractiveAuthentication no/' /etc/ssh/sshd_config
  - sed -i -E 's/^#?ChallengeResponseAuthentication .*/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config
  - sed -i -E 's/^#?MaxAuthTries .*/MaxAuthTries 2/' /etc/ssh/sshd_config
  - sed -i -E 's/^#?AllowTcpForwarding .*/AllowTcpForwarding yes/' /etc/ssh/sshd_config
  - sed -i -E 's/^#?X11Forwarding .*/X11Forwarding no/' /etc/ssh/sshd_config
  - sed -i -E 's/^#?AllowAgentForwarding .*/AllowAgentForwarding no/' /etc/ssh/sshd_config
  - sed -i -E 's/^#?AuthorizedKeysFile .*/AuthorizedKeysFile .ssh\/authorized_keys/' /etc/ssh/sshd_config

  # SSH ListenAddress je nach Zugriffsmode konfigurieren
<SSH_LISTEN_ADDRESS_BLOCK>

  # Nur bestimmte User erlauben
  - sed -i '/^AllowUsers/d' /etc/ssh/sshd_config
  - echo "AllowUsers holu deploy" >> /etc/ssh/sshd_config

  - systemctl restart ssh

  # ==========================================================================
  # 6. IP-Forwarding für Docker aktivieren
  # ==========================================================================
  - sed -i 's/^#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/' /etc/sysctl.conf
  - sysctl -p

  # ==========================================================================
  # 7. Neustart
  # ==========================================================================
  - cloud-init status --wait
  - reboot
