# Developer Setup Guide

Schritt-fuer-Schritt Anleitung fuer neue Entwickler (Windows + Mac).

> **Kurzversion:** Git + Python + Docker + GitHub CLI installieren, Repo klonen,
> `skuld doctor` ausfuehren. Alles weitere steht im [README](../README.md).

## 1. Tools installieren

### Windows

```powershell
winget install Git.Git
winget install Docker.DockerDesktop
winget install GitHub.cli
```

Python 3.10+ von https://python.org/downloads installieren.

### Mac

```bash
brew install git python@3.13 gh
brew install --cask docker
```

## 2. GitHub CLI authentifizieren

```bash
gh auth login
```

Waehle: **GitHub.com** > **HTTPS** > **Login with a web browser**

> **Windows PowerShell Tipp:** Falls `gh` nicht erkannt wird:
> ```powershell
> & "C:\Program Files\GitHub CLI\gh.exe" auth login
> ```

## 3. Repo klonen

```bash
git clone https://github.com/Wuuzzaa/Skuld.git
cd Skuld
```

## 4. Python-Umgebung einrichten

```bash
python -m venv .venv
```

Aktivieren:

```bash
# Windows PowerShell
.venv\Scripts\activate

# Mac / Linux
source .venv/bin/activate
```

Dependencies:

```bash
pip install -r requirements.txt
```

## 5. skuld-cli installieren

```bash
cd ops/skuld-cli
pip install -e .
cd ../..
```

## 6. Setup pruefen

```bash
skuld doctor
```

Erwartete Ausgabe:

```
OK  gh CLI found
OK  gh authenticated
OK  Repository Wuuzzaa/Skuld accessible
All checks passed.
```

## 7. Deployen

Siehe [README.md](../README.md#deployment) fuer alle Befehle. Kurzfassung:

```bash
# Production: einfach auf master pushen
git push origin master

# Staging: beliebigen Branch auf Heimserver deployen
skuld deploy home --branch mein-feature

# DB von Prod auf Staging kopieren
skuld db replicate --source production
```

## 8. Lokale Datenbank (optional)

Fuer lokale Entwicklung ohne Server-Zugang:

```powershell
# Windows
.\setup_scripts\manage_local_db.ps1
# Waehle Option 3: "Start with EMPTY database"
```

| Service | URL / Port |
|---------|-----------|
| PostgreSQL | `localhost:5432` (User: `dev`, Pass: `dev`, DB: `skuld_dev`) |
| PgAdmin | http://localhost:5051 (Login: `admin@admin.com` / `admin`) |

Fuer lokale Entwicklung **mit Production-Daten** (ca. 17 GB) wird SSH-Zugang zum
Production-Server benoetigt. SSH-Key generieren und Public Key an Admin schicken:

```bash
ssh-keygen -t ed25519 -C "dein.name@email.com"
cat ~/.ssh/id_ed25519.pub  # An Admin schicken
```

## 9. App lokal starten

```bash
streamlit run Skuld/app.py
```

Laeuft auf http://localhost:8501 (braucht laufende PostgreSQL-DB aus Schritt 8).

## 10. Tests

```bash
pytest
```
