# WireGuard VPN Setup für Barchart Scraping

## 📋 Übersicht

Diese Anleitung hilft dir, WireGuard VPN zwischen deinem Hetzner Server und Raspberry Pi einzurichten, damit Barchart Scraping über deine Home-IP läuft.

---

## ✅ Was bereits erledigt ist:

### Raspberry Pi (VPN-Server)
- ✅ WireGuard installiert
- ✅ Läuft auf `192.168.0.84`
- ✅ VPN-IP: `10.0.0.1`
- ✅ Public Key: `2PjU2No7D98ZA8s8kdRruRp8zWAGW3lUZWCYpGQeISs=`
- ✅ IPv6 Host Exposure konfiguriert
- ✅ Port 51820 UDP offen

---

## 🚀 Server Setup (Hetzner)

### 1. Keys generieren

Auf dem Server (im Projektverzeichnis):

```bash
cd ~/skuld  # Oder dein Projektpfad

# Keys generieren
wg genkey | tee wireguard/server_privatekey | wg pubkey > wireguard/server_publickey

# Keys anzeigen
echo "=== SERVER PRIVATE KEY ==="
cat wireguard/server_privatekey
echo ""
echo "=== SERVER PUBLIC KEY ==="
cat wireguard/server_publickey
```

**📝 Notiere beide Keys!**

### 2. WireGuard Config erstellen

```bash
# Template kopieren
cp wireguard/wg0.conf.template wireguard/wg0.conf

# Config bearbeiten
nano wireguard/wg0.conf
```

Ersetze `SERVER_PRIVATE_KEY_HIER_EINFUEGEN` mit deinem Private Key von oben.

**Speichern:** `Ctrl+X` → `Y` → `Enter`

```bash
# Berechtigungen setzen (wichtig!)
chmod 600 wireguard/wg0.conf
```

### 3. Raspberry Pi Config aktualisieren

SSH auf Raspberry Pi und füge den Server als Peer hinzu:

```bash
sudo nano /etc/wireguard/wg0.conf
```

Am Ende hinzufügen:

```ini
[Peer]
PublicKey = DEIN_SERVER_PUBLIC_KEY
AllowedIPs = 10.0.0.2/32
```

**Speichern und WireGuard neu starten:**

```bash
sudo systemctl restart wg-quick@wg0
sudo wg show
```

### 4. Docker Container bauen

Auf dem Server:

```bash
# Container neu bauen mit WireGuard Support
docker-compose build

# Container starten
docker-compose up -d
```

---

## 🧪 VPN testen

### Test 1: VPN im Container starten

```bash
# In den Container gehen
docker exec -it skuld-streamlit bash

# VPN starten
wg-quick up wg0

# Status prüfen
wg show

# IP prüfen (sollte Home-IP sein)
curl https://api.ipify.org

# Raspberry Pi anpingen
ping -c 3 10.0.0.1

# VPN beenden
wg-quick down wg0
exit
```

### Test 2: Python VPN Manager nutzen

```python
from vpn_manager import VPNManager

# VPN für Scraping verwenden
with VPNManager() as vpn:
    if vpn.is_connected:
        # Hier dein Scraping-Code
        from src.barchart_scrapper import scrape_barchart
        scrape_barchart()
```

---

## 📦 Integration in main.py

**WICHTIG:** VPN wird **on-demand** genutzt, nicht dauerhaft!

### Konzept:
- Container startet **ohne** VPN
- VPN wird nur für **Barchart Scraping** aktiviert
- Nach Scraping wird VPN **automatisch beendet**
- ✅ Bei jedem Rebuild: Keys bleiben erhalten (Volume Mount)
- ✅ Täglich neue IP durch täglichen Scraping-Lauf

### Option 1: Barchart Scraper direkt anpassen

In `src/barchart_scrapper.py` am Anfang hinzufügen:

```python
from vpn_manager import VPNManager

def scrape_barchart():
    """Scrapt Barchart mit VPN"""
    
    with VPNManager() as vpn:
        if not vpn.is_connected:
            logger.error("VPN failed, skipping Barchart")
            return
        
        # Dein bestehender Scraping-Code hier
        # ...
```

### Option 2: Wrapper nutzen (empfohlen)

Verwende `src/barchart_scrapper_with_vpn.py`:

```python
from src.barchart_scrapper_with_vpn import scrape_barchart_with_vpn

# In main.py oder Cron-Job
scrape_barchart_with_vpn()  # Baut VPN automatisch auf & ab
```

---

## ⏰ Cron Job anpassen

Damit VPN täglich neu verbindet (neue IP):

1. Data Collection läuft einmal täglich
2. Jedes Mal neue VPN-Verbindung = neue Home-IP

Bereits konfiguriert in `crontab`:
```
0 3 * * * cd /app/Skuld && python main.py
```

---

## 🔄 Container Rebuilds & VPN

### Was passiert bei Container-Rebuilds?

✅ **Bleibt erhalten:**
- WireGuard Config (`wireguard/wg0.conf`) - als Volume gemountet
- Keys (liegen außerhalb des Containers)
- Raspberry Pi Konfiguration

❌ **Wird neu erstellt:**
- Container selbst
- WireGuard Installation (automatisch)

### Bei täglichem Rebuild:

```bash
# Container wird neu gebaut
docker-compose up -d --build

# VPN-Config bleibt erhalten (Volume Mount)
# Bei nächstem Scraping: VPN wird automatisch aufgebaut
```

### Best Practice:

**Täglicher Ablauf:**
```
03:00 - Cron Job startet Data Collection
      → VPN wird aufgebaut (neue IP)
      → Barchart Scraping läuft
      → VPN wird beendet
      → Andere Scraper laufen (ohne VPN)
```

**Container-Rebuilds:**
- Manuell nur bei Code-Änderungen
- Automatisch nicht nötig für IP-Rotation
- VPN-Keys bleiben immer erhalten

---

## 🔍 Troubleshooting

### VPN startet nicht

```bash
# Im Container debuggen
docker exec -it skuld-streamlit bash
wg-quick up wg0

# Fehler analysieren
journalctl -xe
```

### Falsche IP wird verwendet

```bash
# Route prüfen
ip route show

# Sollte zeigen:
# default via 10.0.0.1 dev wg0
```

### Raspberry Pi nicht erreichbar

```bash
# Auf Raspberry Pi prüfen
sudo wg show
sudo systemctl status wg-quick@wg0

# Firewall prüfen
sudo ip6tables -L -v -n
```

---

## 📊 IP-Rotation testen

```bash
# Tag 1
docker exec skuld-streamlit curl https://api.ipify.org

# Router neu verbinden (oder warten bis automatisch passiert)

# Tag 2
docker exec skuld-streamlit curl https://api.ipify.org

# IPs sollten unterschiedlich sein!
```

---

## ✅ Checkliste

- [ ] Server Keys generiert
- [ ] `wireguard/wg0.conf` erstellt (ohne .template)
- [ ] Raspberry Pi Peer-Config aktualisiert
- [ ] Docker Container neu gebaut
- [ ] VPN-Test erfolgreich
- [ ] Barchart Scraping funktioniert
- [ ] IP ändert sich täglich

---

## 🎯 Produktiv-Setup

1. **Automatische VPN-Nutzung** in `src/barchart_scrapper.py` integrieren
2. **Error Handling** für VPN-Fehler
3. **Monitoring** der VPN-Verbindungen
4. **Logging** der verwendeten IPs

---

**Bei Fragen oder Problemen siehe Logs:**

```bash
# Container Logs
docker logs skuld-streamlit -f

# VPN Status
docker exec skuld-streamlit wg show
```
