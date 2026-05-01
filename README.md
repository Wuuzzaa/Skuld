# Skuld

Options-Trading-Plattform mit Streamlit + PostgreSQL.

**Production:** https://app.skuld-options.com/

## Quick Start (fuer Entwickler)

### 1. Voraussetzungen installieren

| Tool | Windows | Mac |
|------|---------|-----|
| **Git** | `winget install Git.Git` | `brew install git` |
| **Python 3.10+** | https://python.org/downloads | `brew install python@3.13` |
| **Docker Desktop** | `winget install Docker.DockerDesktop` | `brew install --cask docker` |
| **GitHub CLI** | `winget install GitHub.cli` | `brew install gh` |

### 2. GitHub CLI authentifizieren

```bash
gh auth login
```

Waehle: **GitHub.com** > **HTTPS** > **Login with a web browser**

> **Windows PowerShell Tipp:** Falls `gh` nicht erkannt wird:
> ```powershell
> & "C:\Program Files\GitHub CLI\gh.exe" auth login
> ```

### 3. Repo klonen und Python-Umgebung einrichten

```bash
git clone https://github.com/Wuuzzaa/Skuld.git
cd Skuld
python -m venv .venv
```

Aktivieren:

```bash
# Windows PowerShell
.venv\Scripts\activate

# Mac / Linux
source .venv/bin/activate
```

Dependencies installieren:

```bash
pip install -r requirements.txt
```

### 4. skuld-cli installieren

```bash
cd ops/skuld-cli
pip install -e .
cd ../..
```

Pruefen ob alles funktioniert:

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

## Deployment

### Wie funktioniert Deployment?

```
git push master  ───────>  Automatisches Production-Deployment (Hetzner)

skuld deploy home  ─────>  Manuelles Staging-Deployment (Heimserver)
```

- **Push auf `master`** = automatisches Production-Deployment. Kein manueller Schritt noetig.
- **Push auf andere Branches** = es passiert NICHTS. Kein Deployment.
- **Staging-Deployment** = immer manuell ueber das CLI-Tool.

### Production deployen

```bash
git checkout master
git merge feature/mein-feature
git push origin master
# -> Production-Deployment startet automatisch
```

### Staging deployen (beliebigen Branch)

```bash
# Aktuellen Branch auf Staging testen
skuld deploy home --branch feature/mein-feature

# Master auf Staging deployen
skuld deploy home
```

### Deployment beobachten

```bash
skuld watch deploy.yml
# oder
skuld status
```

## Datenbank

### DB von Production auf Staging replizieren

Kopiert die komplette Production-DB auf den Heimserver (ERSETZT die Staging-DB):

```bash
skuld db replicate --source production
```

### DB Backup erstellen

```bash
skuld db backup production
skuld db backup home
```

### DB Health Check

```bash
skuld db healthcheck production
skuld db healthcheck home
```

### Lokale Datenbank (fuer Entwicklung)

Die Produktions-DB ist ca. 17 GB (6 GB komprimiert). Fuer lokale Entwicklung:

**Option A: Leere DB (schnell, kein SSH noetig)**

```powershell
# Windows
.\setup_scripts\manage_local_db.ps1
# Waehle Option 3: "Start with EMPTY database"
```

**Option B: Mit Production-Daten (braucht SSH-Zugang)**

1. SSH-Key generieren:
   ```bash
   ssh-keygen -t ed25519 -C "dein.name@email.com"
   ```
2. Public Key an Admin schicken: `cat ~/.ssh/id_ed25519.pub`
3. Nach Freischaltung:
   ```powershell
   .\setup_scripts\manage_local_db.ps1
   # Waehle Option 2: "Download latest from Remote Server"
   ```

**Lokale DB-Verbindung:**

| Service | URL / Port |
|---------|-----------|
| PostgreSQL | `localhost:5432` (User: `dev`, Pass: `dev`, DB: `skuld_dev`) |
| PgAdmin | http://localhost:5051 (Login: `admin@admin.com` / `admin`) |

## Jobs (Datensammlung)

Jobs werden auf den Servern ausgefuehrt, nicht lokal:

```bash
# Verfuegbare Jobs
skuld jobs run <target> <job>

# Beispiele
skuld jobs run home option_data          # Option-Daten laden
skuld jobs run home saturday_night       # Samstag-Nacht Job
skuld jobs run home stock_data_daily     # Taegliche Stock-Daten
skuld jobs run production option_data    # Auf Production ausfuehren
```

Verfuegbare Jobs: `saturday_night`, `option_data`, `market_start_mid_end`, `stock_data_daily`, `historization`

## Alle CLI-Befehle

| Befehl | Beschreibung |
|--------|-------------|
| `skuld doctor` | Pruefen ob alles eingerichtet ist |
| `skuld status` | Environments + letzte Workflow-Runs |
| `skuld deploy production` | Production deployen (= `git push master`) |
| `skuld deploy home` | Master auf Staging deployen |
| `skuld deploy home --branch xyz` | Branch `xyz` auf Staging deployen |
| `skuld db replicate --source production` | Prod-DB auf Staging kopieren |
| `skuld db backup production` | Backup auf Production erstellen |
| `skuld db healthcheck home` | DB-Status auf Staging pruefen |
| `skuld jobs run home option_data` | Job auf Staging ausfuehren |
| `skuld watch deploy.yml` | Laufenden Workflow beobachten |

## App lokal starten

```bash
streamlit run Skuld/app.py
```

Die App laeuft auf http://localhost:8501 (braucht laufende PostgreSQL-DB).

## Tests

```bash
pytest
```

## Architektur

```
Entwickler-Laptop              GitHub Actions              Server
──────────────────            ──────────────              ──────
git push master ────────> deploy.yml ───────────> Production (Hetzner)
                                                  91.98.156.116

skuld deploy home ──────> deploy.yml ───────────> Staging (Heimserver)
                           (self-hosted runner)   192.168.0.235
```

- **Secrets:** GitHub Repository Secrets (9 Stueck, keine per-Environment Secrets)
- **Config:** `ops/environments.yaml` (Single Source of Truth fuer alle Environments)
- **CLI:** `ops/skuld-cli/` (Wrapper um GitHub Actions Workflows)

## Troubleshooting

| Problem | Loesung |
|---------|---------|
| `skuld: command not found` | `cd ops/skuld-cli && pip install -e .` |
| `gh: command not found` | `winget install GitHub.cli` (Win) / `brew install gh` (Mac) |
| `gh not authenticated` | `gh auth login` |
| PowerShell erkennt `gh` nicht | `& "C:\Program Files\GitHub CLI\gh.exe" auth login` |
| Deploy auf Staging schlaegt fehl | `skuld db healthcheck home` pruefen |
| DB Replikation timeout | Backup ist ~6 GB, kann 15-20 Min dauern |
