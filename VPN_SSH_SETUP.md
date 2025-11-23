# VPN Setup via SSH SOCKS5 Proxy

## 🎯 Quick Overview - Was wo gemacht werden muss

### ✅ Bereits erledigt:
- **Raspberry Pi**: WireGuard Server läuft, NAT konfiguriert
- **Hetzner Server**: WireGuard Client verbunden, kann Raspberry Pi erreichen (ping 10.0.0.1)
- **GitHub**: Code ist deployed, wartet auf Container-Neustart

### 🔧 Noch zu tun:

#### **AUF DEM HETZNER SERVER** (als User `deploy`):

1. **SSH-Keys einrichten** (damit Container passwortlos auf Raspberry Pi zugreifen kann)
2. **Container neu starten** (mit neuer VPN-via-SSH Funktionalität)
3. **Testen** ob VPN funktioniert

#### **AUF DEM RASPBERRY PI**:
- ✅ **Nichts!** Alles bereits fertig.

---

## 📋 Schritt-für-Schritt Anleitung

### 🖥️ HETZNER SERVER - SSH-Key Setup

```bash
# 1. Auf Hetzner Server einloggen
ssh deploy@docker-ce-ubuntu-4gb-fsn1-1

# 2. SSH-Key generieren (wird vom Container genutzt)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_vpn -N ""
# Ausgabe: 
#   Your identification has been saved in /home/deploy/.ssh/id_ed25519_vpn
#   Your public key has been saved in /home/deploy/.ssh/id_ed25519_vpn.pub

# 3. Public Key zum Raspberry Pi kopieren
ssh-copy-id -i ~/.ssh/id_ed25519_vpn.pub pi@10.0.0.1
# Wenn nach Passwort gefragt: Raspberry Pi Passwort eingeben
# Ausgabe sollte zeigen: "Number of key(s) added: 1"

# 4. SSH-Config erstellen (vereinfacht Zugriff)
cat >> ~/.ssh/config << 'EOF'
Host raspberry-vpn
    HostName 10.0.0.1
    User pi
    IdentityFile ~/.ssh/id_ed25519_vpn
    StrictHostKeyChecking no
    UserKnownHostsFile=/dev/null
EOF

chmod 600 ~/.ssh/config

# 5. Test - sollte OHNE Passwort funktionieren!
ssh raspberry-vpn "echo SSH works!"
# Erwartete Ausgabe: "SSH works!"
```

### 🐳 HETZNER SERVER - Container Deployment

```bash
# 6. Warten bis GitHub Actions fertig ist (~2 Minuten)
# Prüfen auf: https://github.com/Wuuzzaa/Skuld/actions

# 7. Container neu starten mit neuer VPN-Funktionalität
cd /opt/skuld-vpn-test
docker-compose down
docker-compose up -d --build

# 8. Logs prüfen (sollte "SSH VPN config found" zeigen)
docker logs skuld-streamlit-vpn-test | grep -i vpn
```

### ✅ HETZNER SERVER - VPN Testen

```bash
# 9. VPN-Funktionalität direkt testen
docker exec -it skuld-streamlit-vpn-test python3 << 'PYTHON'
from vpn_manager import VPNManager
import logging
logging.basicConfig(level=logging.INFO)

with VPNManager() as vpn:
    if vpn.is_connected:
        session = vpn.get_session()
        response = session.get('https://api.ipify.org')
        print(f'\n🎉 SUCCESS! Your IP through VPN: {response.text}')
        print(f'Expected: 46.223.163.242 (your home IP)\n')
    else:
        print('❌ VPN connection failed')
PYTHON
```

**Erwartete Ausgabe:**
```
🔐 Starte SOCKS5-Proxy zu raspberry-vpn:1080...
✅ SOCKS5-Proxy aktiv. Öffentliche IP: 46.223.163.242
🎉 SUCCESS! Your IP through VPN: 46.223.163.242
Expected: 46.223.163.242 (your home IP)
🔓 Beende SOCKS5-Proxy...
✅ Proxy beendet
```

---

## 🚀 Verwendung in main.py

Nach erfolgreichem Setup wird Barchart automatisch mit VPN gescrapt:

```python
# In main.py
from src.barchart_scrapper_with_vpn import scrape_barchart_with_vpn

# Statt:
# from src.barchart_scrapper import scrape_barchart
# scrape_barchart()

# Nutze:
scrape_barchart_with_vpn()  # ← Nutzt automatisch deine Home-IP!
```

---

## 🎯 Zusammenfassung - WO WIRD WAS GEMACHT

| Aktion | Ort | Befehl |
|--------|-----|--------|
| SSH-Keys generieren | **Hetzner** (`deploy` user) | `ssh-keygen -t ed25519...` |
| Public Key kopieren | **Hetzner → Raspberry** | `ssh-copy-id pi@10.0.0.1` |
| SSH-Config erstellen | **Hetzner** | `cat >> ~/.ssh/config` |
| Container neustarten | **Hetzner** | `docker-compose up -d --build` |
| VPN testen | **Hetzner** (im Container) | `docker exec... python3` |
| NAT/WireGuard | **Raspberry** | ✅ Bereits fertig! |

---

## Übersicht

Statt WireGuard direkt im Container zu nutzen, verwenden wir einen **SSH-Tunnel mit SOCKS5-Proxy** zum Raspberry Pi. Das ist einfacher und zuverlässiger.

## Voraussetzungen

1. ✅ WireGuard läuft auf dem Hetzner Host: `sudo wg show` zeigt Verbindung
2. ✅ Raspberry Pi ist über VPN erreichbar: `ping 10.0.0.1` funktioniert
3. 🔧 **SSH-Keys müssen eingerichtet werden** (siehe unten)

## SSH-Key Setup auf Hetzner Server

```bash
# 1. SSH-Key generieren (falls noch nicht vorhanden)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_vpn -N ""

# 2. Public Key zum Raspberry Pi kopieren
ssh-copy-id -i ~/.ssh/id_ed25519_vpn.pub pi@10.0.0.1

# 3. Testen (sollte OHNE Passwort funktionieren)
ssh -i ~/.ssh/id_ed25519_vpn pi@10.0.0.1 "echo SSH works!"

# 4. SSH-Config erstellen für einfacheren Zugriff
cat >> ~/.ssh/config << 'EOF'
Host raspberry-vpn
    HostName 10.0.0.1
    User pi
    IdentityFile ~/.ssh/id_ed25519_vpn
    StrictHostKeyChecking no
    UserKnownHostsFile=/dev/null
EOF

chmod 600 ~/.ssh/config

# 5. Test mit Alias
ssh raspberry-vpn "echo SSH config works!"
```

## Python Code Anpassung für SSH-Config

Die `vpn_manager.py` nutzt jetzt:
```python
ssh raspberry-vpn  # Statt pi@10.0.0.1
```

## WireGuard auf Host permanent aktivieren

```bash
# WireGuard beim Boot starten
sudo systemctl enable wg-quick@wg0

# Manuell starten (falls noch nicht aktiv)
sudo wg-quick up wg0

# Status prüfen
sudo systemctl status wg-quick@wg0
```

## Funktionsweise

1. **Hetzner Server** hat WireGuard-Verbindung zum Raspberry Pi (10.0.0.1)
2. **Python Code** erstellt SSH-Tunnel: `ssh -D 1080 pi@10.0.0.1`
3. **Requests** nutzen SOCKS5-Proxy: `socks5h://127.0.0.1:1080`
4. **Traffic** geht: Hetzner → VPN → Raspberry Pi → Internet (mit Home-IP!)

## Verwendung im Code

```python
from vpn_manager import VPNManager

# Mit Context Manager (automatisches Cleanup)
with VPNManager() as vpn:
    if vpn.is_connected:
        # Session mit Proxy holen
        session = vpn.get_session()
        
        # Scraping mit Home-IP
        response = session.get('https://www.barchart.com/...')
        
# VPN wird automatisch beendet
```

## Barchart Scraping mit VPN

```python
from src.barchart_scrapper_with_vpn import scrape_barchart_with_vpn

# Scrapt alle Symbols mit Home-IP
result = scrape_barchart_with_vpn()
```

## Troubleshooting

### SSH-Verbindung schlägt fehl
```bash
# Prüfen ob WireGuard läuft
sudo wg show

# Prüfen ob Raspberry Pi erreichbar ist
ping -c 3 10.0.0.1

# SSH manuell testen
ssh -v pi@10.0.0.1
```

### Proxy funktioniert nicht
```bash
# SOCKS5-Proxy manuell testen
ssh -D 1080 -f -N pi@10.0.0.1

# Mit curl testen
curl --socks5-hostname 127.0.0.1:1080 https://api.ipify.org
# Sollte 46.223.163.242 (deine Home-IP) zeigen

# Proxy-Prozess beenden
pkill -f "ssh.*10.0.0.1"
```

### IP wird nicht gewechselt
```bash
# Ohne Proxy
curl https://api.ipify.org
# Zeigt Hetzner-IP

# Mit Proxy
curl --socks5-hostname 127.0.0.1:1080 https://api.ipify.org
# Sollte Home-IP zeigen (46.223.163.242)
```

## Vorteile dieser Lösung

✅ **Einfach**: Keine komplexen Routing-Regeln
✅ **Sicher**: SSH-Verschlüsselung on top von WireGuard
✅ **Flexibel**: Nur Barchart-Traffic durch VPN
✅ **Stabil**: Kein SSH-Disconnect, keine Host-Routing-Probleme
✅ **On-Demand**: VPN nur wenn gebraucht

## Integration in main.py / Cron

```python
# main.py - Data Collection
from src.barchart_scrapper_with_vpn import scrape_barchart_with_vpn

def collect_data():
    # ... andere Scraper ...
    
    # Barchart mit VPN
    scrape_barchart_with_vpn()
    
    # ... weitere Scraper ...
```

## Automatische IP-Rotation

Da Vodafone täglich neue IPs vergibt, bekommst du automatisch jeden Tag eine neue IP ohne zusätzliche Konfiguration! 🎉
