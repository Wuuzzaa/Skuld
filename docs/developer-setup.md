# Developer Setup Guide

Schritt-fuer-Schritt Anleitung fuer neue Entwickler.

## Voraussetzungen

- **Git** + Push-Zugang zum Repo `Wuuzzaa/Skuld`
- **Python 3.10+**
- **Docker Desktop** (installiert und gestartet)
- **GitHub CLI** (`gh`): https://cli.github.com/ (nur fuer Deployments)

## 1. Repo klonen

```bash
git clone https://github.com/Wuuzzaa/Skuld.git
cd Skuld
```

## 2. Python-Umgebung einrichten

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
```

## 3. Lokale Datenbank starten

### Option A: Leere DB (schnell, kein SSH noetig)

```powershell
.\setup_scripts\manage_local_db.ps1
# Waehle Option 3: "Start with EMPTY database"
```

Das startet PostgreSQL + PgAdmin lokal in Docker:

| Service | URL / Port |
|---------|-----------|
| PostgreSQL | `localhost:5432` (User: `dev`, Pass: `dev`, DB: `skuld_dev`) |
| PgAdmin | `http://localhost:5051` (Login: `admin@admin.com` / `admin`) |

### Option B: Mit Production-Daten (braucht SSH-Zugang)

Die Produktions-DB ist ~17 GB (6 GB komprimiert). Der Download dauert je nach Leitung 10-30 Minuten.

**Einmalig: SSH-Zugang einrichten**

1. SSH-Key generieren (falls noch keiner existiert):
   ```bash
   ssh-keygen -t ed25519 -C "dein.name@firma.com"
   ```

2. Public Key an Daniel schicken:
   ```bash
   cat ~/.ssh/id_ed25519.pub
   ```
   Daniel hinterlegt den Key auf dem Production-Server. Danach:

3. Testen:
   ```bash
   ssh deploy@91.98.156.116 "echo OK"
   ```

**DB herunterladen und importieren:**

```powershell
.\setup_scripts\manage_local_db.ps1
# Waehle Option 2: "Download latest from Remote Server"
# Host: 91.98.156.116 (Enter fuer Default)
# User: deploy (Enter fuer Default)
# Path: (Enter fuer Default)
# SSH Key: Pfad zu deinem Private Key, z.B. C:\Users\DeinName\.ssh\id_ed25519
```

Die `.env`-Datei speichert die Defaults, damit du sie nicht jedes Mal eingeben musst:

```dotenv
# .env (wird automatisch erstellt)
REMOTE_DB_HOST=91.98.156.116
REMOTE_DB_USER=deploy
REMOTE_DB_PATH=/home/deploy/backups/postgres
SSH_KEY_PATH=C:\Users\DeinName\.ssh\id_ed25519
```

## 4. Streamlit-App starten

```bash
streamlit run Skuld/app.py
```

Die App laeuft dann auf `http://localhost:8501`.

> **Hinweis:** Die App erwartet eine laufende PostgreSQL-Datenbank (Schritt 3).

## 5. Tests ausfuehren

```bash
pytest
```

## 6. Deployen (optional)

Fuer Deployments brauchst du die GitHub CLI und Push-Rechte:

```bash
# Einmalig
gh auth login

# CLI installieren
cd ops/skuld-cli
pip install -e .
skuld doctor

# Deployen
skuld deploy production              # Production (Hetzner)
skuld deploy home --branch feature/x # Staging (Heimserver)
```

Kein SSH-Key noetig — alles geht ueber GitHub Actions.

Siehe `ops/skuld-cli/README.md` fuer alle Befehle.

## SSH-Key Onboarding (fuer Admins)

Um den Public Key eines neuen Entwicklers auf dem Production-Server zu hinterlegen:

```bash
# Vom Heimserver aus (hat bereits deploy_key Zugang):
./ops/add-developer-key.sh "ssh-ed25519 AAAAC3Nza... developer@laptop"

# Oder:
cat developer_key.pub | ./ops/add-developer-key.sh
```

## Architektur-Ueberblick

```
Entwickler-Laptop              GitHub Actions              Server
──────────────────            ──────────────              ──────
git push master ────────> deploy.yml ───────────> Production (Hetzner)
                                                  91.98.156.116

skuld deploy home ──────> deploy.yml ───────────> Staging (Heimserver)
                           (self-hosted runner)   192.168.0.235

manage_local_db.ps1 ──── SCP ──────────────────> Production Backup
                          (SSH direkt)            ~/backups/postgres/
```

Alle Secrets liegen als GitHub Repository Secrets. Environment-spezifische Konfiguration steht in `ops/environments.yaml`.
