# Skuld – Hetzner Server Provisioning

Automatisches Aufsetzen und Verwalten von Hetzner Cloud Servern fuer Skuld via Cloud-Init.

Das Setup kann mit Tailscale-VPN oder ohne Tailscale betrieben werden.

## Übersicht

| Datei | Beschreibung |
|---|---|
| `ops/cloud-init.yml.tpl` | Cloud-Init Template (Docker, Tailscale, UFW, SSH-Härtung) |
| `ops/provision-hetzner.ps1` | PowerShell-Script fuer Create, Delete, Recreate und List |
| `ops/provision.local.example.json` | Beispiel fuer lokale, nicht versionierte Defaults |

## Was wird konfiguriert?

- **Docker CE** (offizielles Repository, nicht `docker.io`)
- **Tailscale VPN optional** – SSH nur ueber VPN oder alternativ oeffentlich mit Key-Auth
- **UFW Firewall** – Port 80/443 öffentlich, SSH/Registry nur Tailscale
- **Docker+UFW Fix** – `iptables: false` damit Docker die Firewall nicht umgeht
- **SSH-Härtung** – Kein Root, kein Passwort, nur Key-Auth, nur Tailscale-Interface
- **fail2ban** – Brute-Force-Schutz
- **Unattended Upgrades** – Automatische Sicherheitsupdates
- **Swap** – 2 GB Swap für kleine Instanzen
- **Docker Networks** – `web` und `postgres_setup_default` werden angelegt
- **Benutzer** – `holu` (Admin/Deploy) und `deploy` (nur Docker)

## Voraussetzungen

1. **Hetzner Cloud API Token** (Read/Write)  
   → [Hetzner Cloud Console](https://console.hetzner.cloud/) → Projekt → API Tokens

2. **Tailscale Auth Key** nur falls du Tailscale nutzen willst  
   → In Tailscale einloggen  
   → Admin Console  
   → Settings → Keys → `Generate auth key`  
   → Empfehlung: `Reusable = No`, `Ephemeral = Yes`

3. **SSH Public Key** (Standard: `~/.ssh/id_ed25519.pub`)
   Falls keiner existiert, bietet das Script an, lokal automatisch einen neuen `ed25519`-Key zu erzeugen.

## Verwendung

### Variante 1: PowerShell-Script (empfohlen)

```powershell
# Interaktiv starten
.\ops\provision-hetzner.ps1

# Neuen Server in Falkenstein aufsetzen
.\ops\provision-hetzner.ps1 -Action Create -ServerName "skuld-prod" -ServerType "cx23" -Location "fsn1"

# Neuen Server ohne Tailscale aufsetzen
.\ops\provision-hetzner.ps1 -Action Create -AccessMode PublicSsh -ServerName "skuld-prod" -Location "fsn1"

# Bestehenden Server gezielt loeschen
.\ops\provision-hetzner.ps1 -Action Delete -ServerName "skuld-prod"

# Bestehenden Server loeschen und direkt neu aufsetzen
.\ops\provision-hetzner.ps1 -Action Recreate -ServerName "skuld-prod" -Location "fsn1"

# Alle Server auflisten
.\ops\provision-hetzner.ps1 -Action List

# Alle Parameter
.\ops\provision-hetzner.ps1 `
   -Action Create `
   -AccessMode Tailscale `
    -ServerName "skuld-prod" `
    -ServerType "cx32" `
    -Location "fsn1" `
    -Image "ubuntu-24.04" `
    -SshPublicKeyPath "$env:USERPROFILE\.ssh\id_ed25519.pub"
```

### Script starten

Im Projektordner in PowerShell:

```powershell
cd C:\Python\SKULD\Skuld-master
.\ops\provision-hetzner.ps1
```

Falls PowerShell das Ausfuehren blockiert:

```powershell
powershell -ExecutionPolicy Bypass -File .\ops\provision-hetzner.ps1
```

### Lokale Defaults ohne Secrets im Repo

Wenn das Repo oeffentlich sein soll, hinterlegst du Secrets nicht im Script und nicht in committeten Dateien.

1. [ops/provision.local.example.json](ops/provision.local.example.json) nach `ops/provision.local.json` kopieren
2. Eigene Werte lokal eintragen
3. Die Datei bleibt durch `.gitignore` unversioniert

Alternativ kannst du Tokens auch nur fuer die aktuelle PowerShell-Session setzen:

```powershell
$env:HETZNER_API_TOKEN = "..."
$env:TAILSCALE_AUTH_KEY = "..."
.\ops\provision-hetzner.ps1
```

## Wie Tailscale funktioniert

Tailscale ist ein VPN-Mesh. Praktisch heisst das:

1. Du installierst Tailscale auf deinem PC.
2. Das Provisioning-Script installiert Tailscale auf dem Server.
3. Dein PC und der Server melden sich im gleichen Tailscale-Netz an.
4. Danach bekommt der Server eine interne Tailscale-IP.
5. Du verbindest dich per SSH ueber diese interne IP statt ueber die oeffentliche Hetzner-IP.

### Auf deinem PC

1. Tailscale installieren
2. Mit dem gleichen Account oder der gleichen Organisation anmelden, die auch den Server verwaltet
3. Pruefen, dass Tailscale verbunden ist

### Auf dem Server

Wenn du im Script `AccessMode Tailscale` waehlst, passiert das automatisch per Cloud-Init:

- Tailscale wird installiert
- `tailscale up --authkey=...` wird ausgefuehrt
- SSH wird auf Tailscale beschraenkt

### Verbindung vom PC zum Server

Nach dem Setup:

```bash
ssh holu@<TAILSCALE_IP>
```

Oder, falls MagicDNS aktiv ist:

```bash
ssh holu@skuld-prod
```

### Variante 2: Hetzner Console (manuell)

1. Server erstellen → Ubuntu 24.04
2. Unter "Cloud config" den Inhalt von `ops/cloud-init.yml.tpl` einfuegen
3. Vorher alle `<PLACEHOLDER>` Werte ersetzen

### Variante 3: hcloud CLI

```bash
hcloud server create \
    --name skuld-prod \
   --type cx23 \
    --location fsn1 \
    --image ubuntu-24.04 \
    --user-data-from-file ops/cloud-init.yml
```

## Server-Typen (Hetzner)

| Typ | vCPU | RAM | SSD | Preis/Monat |
|---|---|---|---|---|
| cx23 | 2 | 4 GB | 40 GB | ~€4 |
| cx32 | 4 | 8 GB | 80 GB | ~€8 |
| cx42 | 8 | 16 GB | 160 GB | ~€15 |

## Locations

| Code | Stadt |
|---|---|
| `fsn1` | Falkenstein (Deutschland) |
| `nbg1` | Nürnberg (Deutschland) |
| `hel1` | Helsinki (Finnland) |
| `ash` | Ashburn (USA) |

## Nach dem Provisioning

1. **2-3 Minuten warten** bis Cloud-Init fertig ist
2. **Tailscale prüfen**: Der Server sollte im [Tailscale Admin Panel](https://login.tailscale.com/admin/machines) erscheinen
3. **SSH testen**:
   ```bash
   ssh holu@<TAILSCALE_IP>
   # oder
   ssh holu@skuld-prod  # wenn Tailscale MagicDNS aktiv
   ```
4. **Cloud-Init Log prüfen** (falls Probleme):
   ```bash
   sudo cloud-init status
   sudo cat /var/log/cloud-init-output.log
   ```
5. **Skuld deployen**

## Typische Ablaeufe

### 1. Alten Helsinki-Server ersetzen und in Falkenstein neu aufsetzen

```powershell
.\ops\provision-hetzner.ps1 -Action Recreate -AccessMode Tailscale -ServerName "skuld-prod" -Location "fsn1"
```

Wenn es mehrere Server gibt und du dir nicht sicher bist, starte einfach ohne Parameter und waehle den Server interaktiv aus.

### 2. Erst nur schauen, was aktuell existiert

```powershell
.\ops\provision-hetzner.ps1 -Action List
```

### 3. Einen beliebigen bestehenden Server platt machen

```powershell
.\ops\provision-hetzner.ps1 -Action Delete
```

Das Script listet dir dann die vorhandenen Server und fragt, welchen es loeschen soll.

## Schutzlogik

- Bei `Delete` und `Recreate` musst du standardmaessig den exakten Servernamen bestaetigen.
- Bei produktionsaehnlichen Namen wie `prod`, `live`, `main` gibt es eine zweite Schutzabfrage.
- Nur mit `-Force` werden diese Abfragen uebersprungen.

## Bekannte Hinweise

- **Mit Tailscale** ist SSH nach Cloud-Init nur ueber Tailscale erreichbar.
- **Ohne Tailscale** bleibt SSH auf Port 22 offen, aber Passwort-Login ist deaktiviert und nur SSH-Key-Auth erlaubt.
- **Tailscale Auth Key** ist ein Einmal-Key und wird bei jedem neuen Server neu erzeugt.
- **Docker + UFW**: Durch `"iptables": false` in `/etc/docker/daemon.json` umgeht Docker die Firewall nicht. Container-zu-Container Kommunikation wird über explizite UFW-Regeln für die Docker-Subnetze erlaubt.
