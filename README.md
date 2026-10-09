# Skuld

Options-Trading-Plattform mit Streamlit + PostgreSQL.

**Production:** https://app.skuld-options.com/

## Setup

```bash
git clone https://github.com/Wuuzzaa/Skuld.git
cd Skuld
python -m venv .venv
# Windows: .venv\Scripts\activate  |  Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
cd ops/skuld-cli && pip install -e . && cd ../..
```

## Run

```bash
streamlit run app.py          # needs a running PostgreSQL DB
```

Local DB setup: `setup_scripts/manage_local_db.ps1` (Windows) or `manage_local_db.sh`.

## Test

```bash
pytest tests/
```

## Deploy

A push to `master` deploys to production automatically via GitHub Actions.
Use `skuld deploy home` to deploy a branch to staging.

See `ops/skuld-cli/` for all CLI commands.

## For contributors

Read `AGENTS.md` before changing anything.
