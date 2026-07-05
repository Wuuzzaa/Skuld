# Slim DB Download — Design (Revised)

**Status:** Approved 2026-07-05, revised after failed first attempt
**Scope:** New feature in `setup_scripts/manage_local_db.sh` + `manage_local_db.ps1`
**Non-Goal:** No changes to server-side backup logic (`backup_db.py`, cronjobs, `replicate-db-to-home.yml`).

---

## Problem

Prod dump is ~16 GB gzipped / ~50 GB uncompressed. Every local `manage_local_db` run pulls the full dump; Docker then consumes multiples of that on disk. For dev/debug/backtest work, a recent slice of history is enough.

**94 % of the size** lives in three tables:

| Table | Data size | Index size |
|---|---|---|
| OptionDataMassiveHistoryDaily | 19 GB | 10 GB |
| StockPricesYahooHistoryDaily | 10 GB | 1.5 GB |
| TechnicalIndicatorsCalculatedHistoryDaily | 7 GB | 0.7 GB |

All 15 `*HistoryDaily` tables share a uniform date column: `snapshot_date (date)`.

## First attempt: what went wrong

The first implementation used

```bash
EXCLUDE_FLAGS="$EXCLUDE_FLAGS --exclude-table-data=public.\"$tbl\""
```

which produces the literal `--exclude-table-data=public."OptionDataMassiveHistoryDaily"`. When this string is later passed through `bash -c "…"` on the remote host, **the outer bash strips the double quotes**, and `pg_dump` sees `--exclude-table-data=public.OptionDataMassiveHistoryDaily`. Postgres identifier folding then interprets the unquoted name as lowercase `optiondatamassivehistorydaily`, which does not match the actual table `OptionDataMassiveHistoryDaily`. The pattern silently matches nothing, and the flag has no effect.

**Consequence:** the 1-day slim test produced 8.8 GB gzipped after 21 min and was not yet finished — because it was effectively running a full dump, not a slim one.

## Fix: correct escaping for mixed-case identifiers

Per PostgreSQL 15 docs (`pg_dump` `-t`/`--exclude-table-data` pattern rules):

> To specify an upper-case or mixed-case name in `-t` and related switches, you need to double-quote the name; else it will be folded to lower case … `pg_dump -t '"MixedCaseTable"' mydb`

So the correct shell form is:

```bash
--exclude-table-data='"OptionDataMassiveHistoryDaily"'
```

Single-quoting the whole value protects the inner double quotes from shell interpretation. `pg_dump` receives `--exclude-table-data="OptionDataMassiveHistoryDaily"` and matches case-sensitively.

## Goal

An additional menu entry that produces a slim dump of the last N days (default 60) on demand and imports it.

**Expected numbers** (based on Prod-DB sizes, not measured yet):

- Non-HistoryDaily data: ~3.2 GB uncompressed → ~1 GB gzipped
- Sixty days of the three big HistoryDaily tables (assume ~16 % of full history): ~5 GB uncompressed → ~1.5 GB gzipped
- **Slim dump total: ~2.5 GB gzipped (versus 16 GB full)**
- **Local Docker DB size after restore: ~15 GB (versus ~50 GB)**

These are estimates. They must be validated by a manual test run (see "Verification" section).

## User Flow

New menu entry in `setup_scripts/manage_local_db.sh` and `.ps1`:

```
No dump file provided via arguments.
1) Select local file path
2) Download latest FULL dump from Remote Server (91.98.156.116)
3) Download SLIM dump (last N days) from Remote Server              ← NEW
4) Start with EMPTY database (Cancel/Skip)
Choose option [1/2/3/4]:
```

On option **3**:

1. Prompt `Days to include (Default: 60):` — default from `.env` (`SLIM_DAYS=60`).
2. Same SSH-config prompts as option 2 (host/user/key with defaults from `.env`).
3. Server creates `/tmp/skuld_slim_<TS>_<N>d.sql.gz` (see "Slim dump construction").
4. SCP to local `~/Downloads/skuld_slim_<TS>_<N>d.sql.gz`.
5. Server-side temp file is deleted **immediately** after successful SCP.
6. Restore proceeds identically to the full dump path: DROP+CREATE against the **local** `skuld-local-db` container, then `gunzip | psql`.

## Slim dump construction

**Two phases, streamed into one gzip file on the server:**

Phase 1 — schema + all non-HistoryDaily data:
```bash
docker exec postgres_setup-db-1 pg_dump -U admin \
  --exclude-table-data='"OptionDataMassiveHistoryDaily"' \
  --exclude-table-data='"StockPricesYahooHistoryDaily"' \
  --exclude-table-data='"TechnicalIndicatorsCalculatedHistoryDaily"' \
  ...  # dynamically for every *HistoryDaily table
  Skuld
```

Phase 2 — append last-N-days data for every `*HistoryDaily` table:
```sql
COPY "TableName" FROM stdin;
<rows from \COPY (SELECT * FROM "TableName" WHERE snapshot_date >= CURRENT_DATE - INTERVAL 'N days') TO STDOUT>
\.
```

Both phases are written sequentially into `gzip > /tmp/skuld_slim_<TS>_<N>d.sql.gz`.

**HistoryDaily table list is discovered dynamically** at runtime:

```sql
SELECT tablename FROM pg_tables
WHERE schemaname='public' AND tablename LIKE '%HistoryDaily'
ORDER BY tablename;
```

Future-proof against new history tables.

## Safety guards (top priority: never harm the Prod DB)

Layered defenses; a single mistake must not slip through.

### assert_readonly_sql (case-sensitive keyword check)

Refuses any SQL payload about to be sent to the remote host that contains destructive keywords. Case-sensitive on uppercase SQL keywords to avoid false positives from shell flags like `-delete` or table names containing `update`.

```bash
assert_readonly_sql() {
    local sql="$1"
    if echo "$sql" | grep -qE '\b(DROP|DELETE|TRUNCATE|INSERT|UPDATE|ALTER|GRANT|REVOKE)\s+(TABLE|DATABASE|SCHEMA|ROLE|USER|INDEX|VIEW|FROM|INTO|ON|ALL)\b'; then
        echo "SAFETY ABORT: destructive SQL detected in remote command" >&2
        exit 1
    fi
    if echo "$sql" | grep -qE '\bCREATE\s+(DATABASE|ROLE|USER|SCHEMA)\b'; then
        echo "SAFETY ABORT: destructive DDL detected in remote command" >&2
        exit 1
    fi
    if echo "$sql" | grep -qiE '\bpg_restore\b'; then
        echo "SAFETY ABORT: pg_restore detected in remote command" >&2
        exit 1
    fi
}
```

Verified against six test cases (three positive, three negative).

### assert_local_container

DROP/CREATE DATABASE must ONLY hit the local `skuld-local-db` container.

```bash
assert_local_container() {
    if [ "$CONTAINER_NAME" != "skuld-local-db" ]; then
        echo "SAFETY ABORT: destructive op targets non-local container '$CONTAINER_NAME'" >&2
        exit 1
    fi
}
```

### Read-only on Prod

Remote script also sets `PGOPTIONS='-c default_transaction_read_only=on'` for every `docker exec … pg_dump`/`psql` call. Even if a bug slipped past the guards, the Postgres session cannot write.

### Temp file discipline

Slim file lives only in `/tmp/skuld_slim_*.sql.gz` on the server. `trap 'rm -f "$REMOTE_TMP"' EXIT` cleans up on abort. A `find /tmp -maxdepth 1 -name 'skuld_slim_*.sql.gz' -mmin +60 -delete` runs at the start of every remote invocation as janitor.

### Full separation Local ↔ Remote

- **Prod (remote):** `pg_dump`, `psql -c "SELECT …"`, `\COPY … TO STDOUT`, `ls`, `stat`, `scp` (server → client) only.
- **Local:** all destructive operations (`DROP DATABASE`, `CREATE DATABASE`, `psql -f`, `docker exec skuld-local-db …`).

### Server backup scripts untouched

`backup_db.py`, cronjobs, `replicate-db-to-home.yml` remain unchanged. This is a pure client feature that reads from Prod.

## Verification plan

Because live Prod tests are expensive and risky, verification happens in a defined, agreed-upon sequence:

1. Guard unit tests (local, no server contact) — 6 cases: three legitimate payloads must pass, three destructive payloads must fail.
2. Bash syntax check: `bash -n manage_local_db.sh`.
3. PowerShell parser check: `[System.Management.Automation.Language.Parser]::ParseFile`.
4. **Manual slim-dump test with N=1** — user-triggered, notified to Kollege in advance, output size and duration measured. Expected: <500 MB, <5 min. If exceeded by a factor of >2, stop and reassess.
5. **Only after test 4 passes:** N=60 real run.

Under no circumstances does the tooling repeatedly hammer Prod during design/dev.

## Configuration (.env)

New default in the auto-init block:
```
# Slim Download Config
SLIM_DAYS=60
```

Existing variables (`REMOTE_DB_HOST`, `REMOTE_DB_USER`, `REMOTE_DB_PATH`, `SSH_KEY_PATH`) are reused.

## Failure and abort behavior

- SSH failure → abort with clear message, no local DROP, no restore attempt.
- SCP failure → abort; remote temp file cleaned up by trap.
- Local slim file already exists (re-run): behave like full-dump mode ("Using existing file"), skip download, go to restore.
- Restore failure → local container left in incomplete state (same as existing behavior for full-dump path); not changed by this feature.

## Platforms

Both `manage_local_db.sh` (bash, macOS/Linux) and `manage_local_db.ps1` (PowerShell, Windows) receive the same feature. Guards implemented in both languages. SSH/SCP expected in both environments (Windows: OpenSSH built-in since Windows 10).

## Out of scope

- No changes to weekly/monthly history data structure (they are tiny and remain complete).
- No changes to master-data tables (kept complete; required for symbol resolution).
- No post-trim of the full-dump path.
- No CI test — first slim-dump run is manually verified with the user and colleague in the loop.
