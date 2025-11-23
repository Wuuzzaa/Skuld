# VPN Test Deployment

## 🎯 Übersicht

Dieser Branch (`wireguard-vpn-setup`) deployt einen **separaten Test-Container** mit VPN-Funktionalität.

### Unterschiede zum Production-Container:

| | **Production** | **VPN Test** |
|---|---|---|
| **Branch** | `docker_trial` / `master` | `wireguard-vpn-setup` |
| **Deployment-Pfad** | `/opt/skuld` | `/opt/skuld-vpn-test` |
| **Container-Name** | `skuld-streamlit` | `skuld-streamlit-vpn-test` |
| **Domain** | `app.skuld-options.com` | `vpn-test.skuld-options.com` |
| **VPN Support** | ❌ Nein | ✅ Ja (WireGuard) |

---

## 🚀 Automatisches Deployment

### Trigger:
- **Git Push** auf Branch `wireguard-vpn-setup`
- GitHub Action deployt automatisch nach `/opt/skuld-vpn-test/`

### Was passiert:
```bash
1. Code wird nach /opt/skuld-vpn-test/ synchronisiert
2. WireGuard Keys werden NICHT überschrieben (exclude)
3. Docker Container wird neu gebaut
4. Container startet als skuld-streamlit-vpn-test
5. Erreichbar unter: https://vpn-test.skuld-options.com/
```

---

## 📦 Manuelles Setup (einmalig auf Server)

### 1. Verzeichnis vorbereiten

```bash
ssh user@server

# Verzeichnis erstellen
sudo mkdir -p /opt/skuld-vpn-test/wireguard
sudo chown -R $USER:$USER /opt/skuld-vpn-test
```

### 2. WireGuard Keys generieren

```bash
cd /opt/skuld-vpn-test

# Keys generieren
wg genkey | tee wireguard/server_privatekey | wg pubkey > wireguard/server_publickey

# Keys anzeigen
echo "=== PRIVATE KEY ==="
cat wireguard/server_privatekey

echo "=== PUBLIC KEY ==="
cat wireguard/server_publickey
```

### 3. WireGuard Config erstellen

Nach dem ersten Deployment:

```bash
cd /opt/skuld-vpn-test

# Template kopieren
cp wireguard/wg0.conf.template wireguard/wg0.conf

# Bearbeiten - Private Key eintragen
nano wireguard/wg0.conf

# Berechtigungen setzen
chmod 600 wireguard/wg0.conf
```

### 4. Raspberry Pi Peer-Config updaten

```bash
# SSH auf Raspberry Pi
ssh pi@192.168.0.84

sudo nano /etc/wireguard/wg0.conf
```

Am Ende hinzufügen:
```ini
[Peer]
PublicKey = DEIN_SERVER_PUBLIC_KEY
AllowedIPs = 10.0.0.2/32
```

Restart:
```bash
sudo systemctl restart wg-quick@wg0
```

### 5. DNS konfigurieren

Erstelle einen DNS A-Record:
```
vpn-test.skuld-options.com → [Deine Server-IP]
```

Traefik generiert automatisch ein SSL-Zertifikat.

---

## 🧪 VPN testen

```bash
# In Test-Container gehen
docker exec -it skuld-streamlit-vpn-test bash

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

---

## 🔄 Workflow

### Änderungen testen:

```bash
# Lokal in Branch
git checkout wireguard-vpn-setup

# Code ändern
# ...

# Committen & Pushen
git add .
git commit -m "Test VPN feature"
git push origin wireguard-vpn-setup
```

→ GitHub Action deployt automatisch nach `/opt/skuld-vpn-test/`
→ Kein Einfluss auf Production-Container!

### Bei Erfolg mergen:

```bash
git checkout master  # oder docker_trial
git merge wireguard-vpn-setup
git push origin master
```

---

## 📊 Container-Status prüfen

```bash
# Beide Container anzeigen
docker ps | grep skuld

# Sollte zeigen:
# skuld-streamlit         (Production)
# skuld-streamlit-vpn-test (VPN Test)

# Logs VPN Test
docker logs -f skuld-streamlit-vpn-test

# Logs Production
docker logs -f skuld-streamlit
```

---

## 🗑️ Test-Container entfernen

Falls du den Test nicht mehr brauchst:

```bash
cd /opt/skuld-vpn-test
sudo docker compose down
sudo rm -rf /opt/skuld-vpn-test
```

---

## ⚠️ Wichtig

- ✅ Production-Container läuft weiter unter `app.skuld-options.com`
- ✅ Test-Container läuft parallel unter `vpn-test.skuld-options.com`
- ✅ Beide Container sind unabhängig
- ✅ WireGuard Keys bleiben nach Rebuilds erhalten
- ⚠️ Test-Container nutzt gleiche Datenbank (wenn nicht geändert)

---

## 📝 Checkliste

- [ ] `/opt/skuld-vpn-test/` existiert auf Server
- [ ] WireGuard Keys generiert
- [ ] `wireguard/wg0.conf` erstellt (ohne .template)
- [ ] Raspberry Pi Peer-Config aktualisiert
- [ ] DNS Record für `vpn-test.skuld-options.com` erstellt
- [ ] Erster Deploy via Git Push erfolgreich
- [ ] VPN-Test erfolgreich
- [ ] Container läuft parallel zu Production

---

**Bei Fragen siehe:** `WIREGUARD_SETUP.md`
