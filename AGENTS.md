# AGENTS.md: instructions for AI coding assistants

Read this file before changing anything in this repository.

## What Skuld is

Skuld is an options trading analysis platform: a Streamlit frontend on top of PostgreSQL, fed by scheduled data-collection jobs.

| Path | Purpose |
|------|---------|
| `app.py` | Streamlit entry point. Registers every page in `st.navigation` |
| `pages/*.py` | One file per page. Pages read data and render it. They do not collect data |
| `main.py --mode <job>` | Data collection. Started by cron (`crontab` → `run_data_collection.sh`) in the backend container |
| `src/` | Shared logic: calculations, data loaders, DB access (`src/database.py`) |
| `db/SQL/query/*.sql` | Read queries used by pages, loaded via `select_into_dataframe(sql_file_path=...)` |
| `db/SQL/migrations/<n>.sql` | Numbered schema migrations, applied automatically |
| `config.py` | Constants (table/view names) and env vars. Loads `.env` |
| `ops/`, `.github/workflows/` | Servers, deployment, `skuld` CLI |

## Hard rules

1. **Never push to `master`.** A push to `master` deploys to production. Work on a feature branch and leave merging to a human.
2. **Do not touch the database and pipeline layer** unless the task explicitly says so. A separate developer owns it:
   - `src/database.py`, `src/historization.py`, `src/data_aging.py`
   - `db/SQL/migrations/`, `db/SQL/tables/`, `db/SQL/views/`
   - `db_setup()` and the job modes in `main.py`
3. **Do not hand-edit generated SQL.** `src/historization.py` writes the files under `db/SQL/tables/create_table/history/` and `db/SQL/views/**/history/` at runtime.
4. **Never commit secrets.** Secrets live encrypted with SOPS + age in `secrets/`. Do not create `.env` files with real values, hard-code API keys, or print secrets in logs.
5. **Do not run destructive job modes** (`all`, `historical_full`, `only_run_migrations`) or any `skuld db replicate` / `skuld deploy production` command.
6. **Before deleting anything, prove it is unused:** grep for the module path, the file name and any string references (for example `"pages/x.py"` in `app.py`, `-m src.x` in `crontab`). If you find any reference you did not expect, stop and report it instead of deleting.

## How to work

- **Setup:** `python -m venv .venv`, then `pip install -r requirements.txt`. Use a local DB via `setup_scripts/manage_local_db.sh` (or the `.ps1` script on Windows).
- **Run:** `streamlit run app.py` from the repo root.
- **Test:** `pytest tests/`. Run it before and after every change and report the results. Some tests need a running DB. Say so if they fail for that reason instead of "fixing" them.
- **Keep changes small:** one logical change per commit, with a clear message. Do not refactor unrelated code on the way.
- **Do not change behavior silently:** a cleanup must not change what a page shows or what a job writes.

## Conventions

- **New page:** create `pages/<name>.py` and register it in `app.py`.
- **SQL:** put it in `db/SQL/query/<name>.sql`, not inline in Python.
- **Reuse before adding:** check `src/` first (for example Black-Scholes is in `src/black_scholes.py`, table display helpers in `src/page_display_dataframe.py`).
- **Table and view names:** use the constants from `config.py`.
- **New dependencies:** add them to `requirements.txt` with a pinned version, and only if they are actually imported.
- **Language:** new documentation and comments are in English.

## When you are done

Report three things:
- what you changed
- what you verified (tests, app start, greps)
- anything you found but deliberately left alone
