# SKULD Portable DevOps — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SKULD auf jedem Linux-Host reproduzierbar aufsetzbar machen (eine Härtungs-Wahrheit), Prod/Test physisch trennen, alles über einen interaktiven `skuld setup` Wizard steuerbar, mit felsenfestem Runbook auf dem Desktop.

**Architecture:** `ops/provision-server.sh` wird die einzige Härtungs-Definition (fail2ban + MaxAuthTries angeglichen, OS-Guard, ROLE-Env-Var). `cloud-init.yml.tpl` wird ein dünner Bootstrap. Die bestehende Click-basierte `skuld`-CLI wird um `setup` (Wizard), `key`, `rollback` erweitert. Doku-Widersprüche werden bereinigt. Das Runbook liegt auf dem Desktop, nicht im Repo.

**Tech Stack:** Bash (provision-server.sh), YAML (cloud-init, environments.yaml), Python 3.10 + Click (skuld-cli), GitHub Actions (Deploy), Docker Compose.

## Global Constraints

- **Kein Overhead:** Vorhandenes erweitern, keine neuen Frameworks/Abstraktionsebenen.
- **Richtige Ordner:** Skripte → `ops/`, Specs/Pläne → `docs/superpowers/`, Runbook → **Desktop** (`C:\Users\I522043\OneDrive - SAP SE\Desktop\`), NICHT ins Repo.
- **Branch:** Alle Repo-Änderungen auf `feature/portable-devops`. NIEMALS master anfassen. KEIN Push ohne Freigabe.
- **Sicherheit:** Keine echten Keys/Passwörter/Prod-Secrets ins Repo. Backup wird NICHT gebaut.
- **Kein echtes Prod berühren** während der Entwicklung. Der neue Server ist Rolle `test`.
- **Idempotenz:** `provision-server.sh` bleibt mehrfach ausführbar.
- Repo-Root: `C:\Python\SKULD\Skuld-master`. CLI-Pfad: `ops/skuld-cli/`. Python: System-Python (`python`), pytest vorhanden.

---

### Task 1: `provision-server.sh` — OS-Guard für neue Ubuntu-Versionen

**Files:**
- Modify: `ops/provision-server.sh` (bestehender OS-Check)

**Interfaces:**
- Produces: OS-Check warnt bei Ubuntu > 24.x und verlangt Bestätigung. Env-Var `ALLOW_UNTESTED_OS=true` überspringt (für cloud-init).

- [ ] **Step 1: Bestehenden OS-Check finden**

Run: `grep -n "ubuntu\|Ubuntu\|VERSION_ID\|os-release" ops/provision-server.sh | head -15`

- [ ] **Step 2: OS-Check erweitern**

Ersetze den OS-Check-Block durch:

```bash
# OS check
if [ ! -f /etc/os-release ]; then
  fail "Cannot detect OS. Only Ubuntu 22.04+ supported."
fi
source /etc/os-release
if [ "$ID" != "ubuntu" ]; then
  fail "Unsupported OS: $ID. Only Ubuntu supported."
fi
UBUNTU_MAJOR="${VERSION_ID%%.*}"
if [ "$UBUNTU_MAJOR" -lt 22 ]; then
  fail "Ubuntu $VERSION_ID too old. Minimum: 22.04"
fi
TESTED_MAX_MAJOR=24
if [ "$UBUNTU_MAJOR" -gt "$TESTED_MAX_MAJOR" ]; then
  warn "Ubuntu $VERSION_ID ist NICHT getestet (geprueft: 22.04/24.04)."
  warn "Docker-Repo/Pakete koennen abweichen. Fortfahren auf eigenes Risiko."
  if [ "${ALLOW_UNTESTED_OS:-false}" != "true" ]; then
    if [ -t 0 ]; then
      read -r -p "Trotzdem fortfahren? (yes/NO): " _os_ok
      [ "$_os_ok" = "yes" ] || fail "Abgebrochen. Setze ALLOW_UNTESTED_OS=true zum Ueberspringen."
    else
      fail "Nicht-getestete OS-Version und kein TTY. Setze ALLOW_UNTESTED_OS=true zum Fortfahren."
    fi
  fi
fi
ok "OS: Ubuntu $VERSION_ID"
```

- [ ] **Step 3: `warn`-Funktion prüfen / ergänzen**

Run: `grep -n "^warn" ops/provision-server.sh | head -3`
Falls NICHT vorhanden, nach der `ok()`-Funktion ergänzen: `warn() { echo -e "${YELLOW}! $*${NC}"; }`

- [ ] **Step 4: Syntax prüfen**

Run: `bash -n ops/provision-server.sh && echo "SYNTAX OK"`

- [ ] **Step 5: Commit**

```bash
git -C /c/Python/SKULD/Skuld-master add ops/provision-server.sh
git -C /c/Python/SKULD/Skuld-master commit -m "feat(provision): OS-Guard warnt bei nicht-getesteten Ubuntu-Versionen"
```

---

### Task 2: `provision-server.sh` — SSH MaxAuthTries + fail2ban (schließt P1)

**Files:**
- Modify: `ops/provision-server.sh`

- [ ] **Step 1: SSH-Hardening-Block finden**

Run: `grep -n "MaxAuthTries\|harden_sshd\|PasswordAuthentication" ops/provision-server.sh | head -10`

- [ ] **Step 2: MaxAuthTries ergänzen**

Nach `harden_sshd "X11Forwarding" "no"` ergänzen:
```bash
harden_sshd "MaxAuthTries" "2"
```

- [ ] **Step 3: fail2ban-Modul ergänzen**

Einfügepunkt finden: `grep -n "Docker\|MODULE 5\|Modul 5" ops/provision-server.sh | head -5`

Direkt VOR dem Docker-Modul einfügen:
```bash
# === Module: fail2ban ===
step "fail2ban"
if ! dpkg -s fail2ban &>/dev/null; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y fail2ban &>/dev/null
fi
cat > /etc/fail2ban/jail.local <<'F2B'
[sshd]
enabled = true
banaction = iptables-multiport
maxretry = 3
bantime = 3600
findtime = 600
F2B
systemctl enable fail2ban &>/dev/null
systemctl restart fail2ban &>/dev/null
ok "fail2ban aktiv (sshd-Jail: maxretry=3, bantime=1h)"
```

- [ ] **Step 4: Syntax + Commit**

```bash
bash -n /c/Python/SKULD/Skuld-master/ops/provision-server.sh && echo "SYNTAX OK"
git -C /c/Python/SKULD/Skuld-master add ops/provision-server.sh
git -C /c/Python/SKULD/Skuld-master commit -m "feat(provision): MaxAuthTries=2 + fail2ban (schließt P1)"
```

---

### Task 3: `provision-server.sh` — ROLE-Parameter

**Files:**
- Modify: `ops/provision-server.sh` (Env-Var-Defaults)

- [ ] **Step 1: Env-Var-Block finden**

Run: `grep -n "RUNNER_LABELS\|self-hosted" ops/provision-server.sh | head -5`

- [ ] **Step 2: ROLE ergänzen und RUNNER_LABELS ableiten**

Ersetze die `RUNNER_LABELS`-Zeile durch:
```bash
ROLE="${ROLE:-test}"
case "$ROLE" in prod|test) ;; *) fail "ROLE muss 'prod' oder 'test' sein (war: $ROLE)";; esac
RUNNER_LABELS="${RUNNER_LABELS:-skuld-$ROLE}"
```

- [ ] **Step 3: ROLE-Ausgabe nach OS-ok ergänzen**

Nach `ok "OS: Ubuntu $VERSION_ID"` einfügen:
```bash
ok "Rolle: $ROLE  ·  Runner-Label: $RUNNER_LABELS"
```

- [ ] **Step 4: Syntax + Commit**

```bash
bash -n /c/Python/SKULD/Skuld-master/ops/provision-server.sh && echo "SYNTAX OK"
git -C /c/Python/SKULD/Skuld-master add ops/provision-server.sh
git -C /c/Python/SKULD/Skuld-master commit -m "feat(provision): ROLE-Parameter (prod|test) leitet Runner-Label ab"
```

---

### Task 4: `cloud-init.yml.tpl` — auf dünnen Bootstrap reduzieren

**Files:**
- Modify: `ops/cloud-init.yml.tpl`
- Create: `ops/cloud-init.README.md`

- [ ] **Step 1: Aktuellen runcmd-Block ansehen**

Run: `grep -n "runcmd\|fail2ban\|MaxAuthTries\|docker" ops/cloud-init.yml.tpl | head -20`

- [ ] **Step 2: runcmd durch Bootstrap ersetzen**

Kompletten `runcmd:`-Block durch folgenden ersetzen:
```yaml
runcmd:
  # Duenner Bootstrap: provision-server.sh (die einzige Haertungs-Wahrheit) ausfuehren.
  - export ALLOW_UNTESTED_OS=true
  - export ROLE='<ROLE>'
  - export RUNNER_TOKEN='<RUNNER_TOKEN>'
  - export INSTALL_TUNNEL='<INSTALL_TUNNEL>'
  - curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/master/ops/provision-server.sh -o /root/provision-server.sh
  - bash /root/provision-server.sh 2>&1 | tee /var/log/skuld-provision.log
```

- [ ] **Step 3: Redundante write_files entfernen**

Run: `grep -n "jail.local\|daemon.json" ops/provision-server.sh`
Falls `provision-server.sh` diese selbst schreibt: entsprechende `write_files`-Blöcke aus cloud-init entfernen.

- [ ] **Step 4: `ops/cloud-init.README.md` schreiben**

Kurze Erklärung: cloud-init ist jetzt nur Bootstrap, führt provision-server.sh aus. Platzhalter-Liste. Hinweis auf Weg A als Fallback.

- [ ] **Step 5: Commit**

```bash
git -C /c/Python/SKULD/Skuld-master add ops/cloud-init.yml.tpl ops/cloud-init.README.md
git -C /c/Python/SKULD/Skuld-master commit -m "refactor(cloud-init): dünner Bootstrap ruft provision-server.sh (eine Wahrheit)"
```

---

### Task 5: `skuld setup` — interaktiver Wizard (Kernstück)

**Files:**
- Modify: `ops/skuld-cli/skuld_cli/cli.py` (neues `setup`-Kommando)
- Modify: `ops/environments.yaml` (neuer Umgebungs-Eintrag vom Wizard geschrieben)
- Test: `ops/skuld-cli/tests/test_setup_wizard.py` (Create)

**Wizard-Ablauf:**
1. IP, SSH-User (default: root), SSH-Key-Pfad (default: ~/.ssh/id_ed25519)
2. Umgebungs-Name, Rolle (prod/test)
3. Web-Domain, Auth-Domain (schlägt `auth.<web-domain>` vor, Enter = bestätigen)
4. Authelia (ja/nein)
5. Härten: ruft `provision-server.sh` per SSH-pipe mit `ROLE=<role>`
6. DB-Befüllung: leer / lokaler Dump
   - Bei Dump: Pfad abfragen, `scp` zum Server, `docker exec psql` restore
   - Bestätigungs-String vor Dump-Restore
7. environments.yaml-Eintrag schreiben
8. Abschluss-Meldung mit DNS-Hinweis + `skuld deploy <name>`

- [ ] **Step 1: Bestehende CLI-Struktur ansehen**

Run: `sed -n '1,80p' /c/Python/SKULD/Skuld-master/ops/skuld-cli/skuld_cli/cli.py`

- [ ] **Step 2: Smoke-Test schreiben (failing)**

Create `ops/skuld-cli/tests/test_setup_wizard.py`:

```python
from click.testing import CliRunner
from skuld_cli.cli import main


def test_setup_command_exists():
    r = CliRunner().invoke(main, ["setup", "--help"])
    assert r.exit_code == 0
    assert "ip" in r.output.lower() or "wizard" in r.output.lower() or "setup" in r.output.lower()


def test_setup_dry_run_shows_provision_command():
    # --dry-run: zeigt was gemacht würde, ohne wirklich SSH aufzurufen
    r = CliRunner().invoke(main, [
        "setup", "--dry-run",
        "--ip", "203.0.113.9",
        "--role", "test",
        "--domain", "test.<your-domain>.com",
        "--env-name", "test1",
        "--db", "empty",
    ])
    assert r.exit_code == 0
    assert "provision-server.sh" in r.output
    assert "ROLE=test" in r.output
    assert "test.<your-domain>.com" in r.output


def test_setup_auth_domain_derived():
    r = CliRunner().invoke(main, [
        "setup", "--dry-run",
        "--ip", "203.0.113.9",
        "--role", "test",
        "--domain", "test.<your-domain>.com",
        "--env-name", "test1",
        "--db", "empty",
    ])
    assert "auth.test.<your-domain>.com" in r.output
```

- [ ] **Step 3: Test ausführen (muss fehlschlagen)**

Run: `cd /c/Python/SKULD/Skuld-master/ops/skuld-cli && python -m pytest tests/test_setup_wizard.py -q`

- [ ] **Step 4: `setup`-Kommando implementieren**

Am Ende von `ops/skuld-cli/skuld_cli/cli.py` ergänzen:

```python
import shlex
import subprocess
import shutil
from pathlib import Path


PROVISION_SCRIPT = Path(__file__).resolve().parents[2] / "provision-server.sh"
ENVIRONMENTS_YAML = Path(__file__).resolve().parents[2] / "environments.yaml"


def _derive_auth_domain(domain: str) -> str:
    return f"auth.{domain}"


def _confirm(prompt: str, expected: str) -> bool:
    val = click.prompt(prompt)
    return val.strip() == expected


@main.command()
@click.option("--ip", prompt="Server IP", help="IP-Adresse des neuen Servers")
@click.option("--ssh-user", default="root", show_default=True, prompt="SSH-User")
@click.option("--ssh-key", default=str(Path.home() / ".ssh" / "id_ed25519"),
              show_default=True, prompt="Pfad zum SSH-Private-Key")
@click.option("--env-name", prompt="Umgebungs-Name (z.B. prod2, test1)",
              help="Neuer Eintrag in environments.yaml")
@click.option("--role", type=click.Choice(["prod", "test"]), default="test",
              show_default=True, prompt="Rolle")
@click.option("--domain", prompt="Web-Domain (z.B. app.<your-domain>.com)")
@click.option("--auth-domain", default=None,
              help="Auth-Domain (default: auth.<domain>)")
@click.option("--db", type=click.Choice(["empty", "dump"]), default="empty",
              show_default=True, prompt="DB-Befüllung (empty=leer starten, dump=lokaler pg_dump)")
@click.option("--dump-path", default=None,
              help="Pfad zum pg_dump-File (nur wenn --db dump)")
@click.option("--dry-run", is_flag=True, help="Nichts ausführen, nur anzeigen was gemacht würde")
def setup(ip, ssh_user, ssh_key, env_name, role, domain, auth_domain, db, dump_path, dry_run):
    """Interaktiver Wizard: neuen Server einrichten, DB befüllen, environments.yaml updaten."""

    # Auth-Domain ableiten / bestätigen
    proposed_auth = _derive_auth_domain(domain)
    if not auth_domain:
        auth_domain = click.prompt(
            f"Auth-Domain",
            default=proposed_auth,
        )

    console.rule("[bold]SKULD Setup Wizard[/bold]")
    console.print(f"  Server:     {ssh_user}@{ip}")
    console.print(f"  Umgebung:   {env_name}  (Rolle: {role})")
    console.print(f"  Domain:     {domain}")
    console.print(f"  Auth:       {auth_domain}")
    console.print(f"  DB:         {db}" + (f"  ← {dump_path}" if dump_path else ""))
    console.print()

    # Phase 1: Härtung
    remote_cmd = f"ROLE={role} bash -s"
    provision_cmd = (
        f"ssh -i {shlex.quote(ssh_key)} -o StrictHostKeyChecking=accept-new "
        f"{ssh_user}@{ip} {shlex.quote(remote_cmd)} < {shlex.quote(str(PROVISION_SCRIPT))}"
    )
    console.print(f"[bold]Phase 1 — Härtung:[/bold]\n{provision_cmd}\n")

    if not dry_run:
        if not PROVISION_SCRIPT.exists():
            console.print(f"[red]FEHLER: {PROVISION_SCRIPT} nicht gefunden.[/red]")
            raise SystemExit(1)
        result = subprocess.run(provision_cmd, shell=True)
        if result.returncode != 0:
            console.print("[red]Härtung fehlgeschlagen. Abbruch.[/red]")
            raise SystemExit(result.returncode)
        console.print("[green]Härtung abgeschlossen.[/green]\n")

    # Phase 2: DB-Befüllung
    if db == "dump":
        if not dump_path:
            dump_path = click.prompt("Pfad zur lokalen pg_dump-Datei")
        dump_file = Path(dump_path).expanduser()
        if not dry_run and not dump_file.exists():
            console.print(f"[red]FEHLER: Dump-Datei nicht gefunden: {dump_file}[/red]")
            raise SystemExit(1)

        console.print(f"[bold]Phase 2 — DB-Restore:[/bold]")
        console.print(f"  Quelle: {dump_file}")
        console.print(f"  Ziel:   {ip} (nur auf diesen Server — niemals Richtung Prod!)")
        console.print()
        if not dry_run:
            confirm_str = f"restore-to-{env_name}"
            if not _confirm(
                f'Bestätigung: Tippe "{confirm_str}" um fortzufahren',
                confirm_str,
            ):
                console.print("[yellow]Abgebrochen.[/yellow]")
                raise SystemExit(0)
            remote_dump = f"/tmp/skuld_restore_{env_name}.sql.gz"
            scp_cmd = (
                f"scp -i {shlex.quote(ssh_key)} {shlex.quote(str(dump_file))} "
                f"{ssh_user}@{ip}:{remote_dump}"
            )
            console.print(f"Kopiere Dump: {scp_cmd}")
            subprocess.run(scp_cmd, shell=True, check=True)
            restore_cmd = (
                f"ssh -i {shlex.quote(ssh_key)} {ssh_user}@{ip} "
                f"'gunzip -c {remote_dump} | docker exec -i skuld_db psql -U skuld skuld'"
            )
            console.print(f"Restore: {restore_cmd}")
            subprocess.run(restore_cmd, shell=True, check=True)
            console.print("[green]DB-Restore abgeschlossen.[/green]\n")
        else:
            console.print(f"[dim]DRY-RUN: scp {dump_file} → {ip}, dann restore in skuld_db[/dim]\n")

    # Phase 3: environments.yaml updaten
    console.print(f"[bold]Phase 3 — environments.yaml aktualisieren:[/bold]")
    new_entry = (
        f"\n{env_name}:\n"
        f"  host: {ip}\n"
        f"  role: {role}\n"
        f"  domain: {domain}\n"
        f"  auth_domain: {auth_domain}\n"
        f"  runner_label: skuld-{role}\n"
        f"  compose_file: docker-compose.yml\n"
    )
    console.print(new_entry)
    if not dry_run:
        with open(ENVIRONMENTS_YAML, "a") as f:
            f.write(new_entry)
        console.print(f"[green]Eintrag '{env_name}' in environments.yaml geschrieben.[/green]\n")

    # Abschluss
    console.rule("[green]Setup abgeschlossen[/green]")
    console.print(f"\n[bold]Nächste Schritte:[/bold]")
    console.print(f"  1. DNS: Cloudflare → {domain} auf {ip} zeigen lassen")
    console.print(f"  2. Deploy:  skuld deploy {env_name}")
    console.print()
```

- [ ] **Step 5: Tests ausführen (müssen grün sein)**

Run: `cd /c/Python/SKULD/Skuld-master/ops/skuld-cli && python -m pytest tests/test_setup_wizard.py -q`
Falls Import-Fehler: `pip install -e . -q` dann erneut.

- [ ] **Step 6: Commit**

```bash
git -C /c/Python/SKULD/Skuld-master add ops/skuld-cli/
git -C /c/Python/SKULD/Skuld-master commit -m "feat(cli): skuld setup Wizard (SSH-Härtung + DB-Dump + environments.yaml)"
```

---

### Task 6: `skuld key` + `skuld rollback` ergänzen

**Files:**
- Modify: `ops/skuld-cli/skuld_cli/cli.py`
- Test: `ops/skuld-cli/tests/test_cli_smoke.py` (Create)

- [ ] **Step 1: Smoke-Tests schreiben**

Create `ops/skuld-cli/tests/test_cli_smoke.py`:

```python
from click.testing import CliRunner
from skuld_cli.cli import main


def test_key_group_has_add_remove_list():
    r = CliRunner().invoke(main, ["key", "--help"])
    assert r.exit_code == 0
    for sub in ("add", "remove", "list"):
        assert sub in r.output


def test_rollback_requires_target_and_ref():
    r = CliRunner().invoke(main, ["rollback"])
    assert r.exit_code != 0
```

- [ ] **Step 2: `key`-Gruppe + `rollback` implementieren**

```python
import re

CONF_PATH = Path(__file__).resolve().parents[2] / "provision-server.conf"


@main.group()
def key():
    """SSH-Keys der deploy-User verwalten (Quelle: provision-server.conf)."""


def _read_conf():
    return CONF_PATH.read_text() if CONF_PATH.exists() else ""


def _current_keys():
    m = re.search(r'SSH_AUTHORIZED_KEYS="\n(.*?)\n"', _read_conf(), flags=re.S)
    if not m:
        return []
    return [ln for ln in m.group(1).splitlines() if ln.strip()]


def _write_keys_block(keys):
    text = _read_conf()
    block = 'SSH_AUTHORIZED_KEYS="\n' + "\n".join(keys) + '\n"'
    if 'SSH_AUTHORIZED_KEYS="' in text:
        text = re.sub(r'SSH_AUTHORIZED_KEYS="\n.*?\n"', block, text, flags=re.S)
    else:
        text = text.rstrip() + "\n" + block + "\n"
    CONF_PATH.write_text(text)


@key.command("list")
def key_list():
    keys = _current_keys()
    if not keys:
        console.print("[yellow]Keine Keys in provision-server.conf.[/yellow]")
        return
    for k in keys:
        console.print(k)


@key.command("add")
@click.argument("name")
@click.argument("pubkey_or_file")
def key_add(name, pubkey_or_file):
    """Public Key hinzufügen. NAME wird als Kommentar gesetzt."""
    p = Path(pubkey_or_file)
    key_str = p.read_text().strip() if p.exists() else pubkey_or_file.strip()
    parts = key_str.split()
    if len(parts) == 2:
        key_str = f"{key_str} {name}"
    keys = _current_keys()
    if any(key_str.split()[1] == k.split()[1] for k in keys if len(k.split()) >= 2):
        console.print("[yellow]Key bereits vorhanden.[/yellow]")
        return
    keys.append(key_str)
    _write_keys_block(keys)
    console.print(f"[green]Key '{name}' hinzugefügt. Server neu provisionieren.[/green]")


@key.command("remove")
@click.argument("name")
def key_remove(name):
    """Key anhand des Kommentars (NAME) entfernen."""
    keys = _current_keys()
    kept = [k for k in keys if not k.strip().endswith(name)]
    if len(kept) == len(keys):
        console.print(f"[yellow]Kein Key '{name}' gefunden.[/yellow]")
        return
    _write_keys_block(kept)
    console.print(f"[green]Key '{name}' entfernt. Server neu provisionieren.[/green]")


@main.command()
@click.argument("target", type=click.Choice(["prod", "test"]))
@click.argument("ref")
@click.option("--watch/--no-watch", default=True)
def rollback(target, ref, watch):
    """Rollback auf früheren REF (Commit/Tag) für TARGET auslösen."""
    cfg = load_config()
    gh_env = "production" if target == "prod" else "home"
    inputs = {"target": gh_env, "ref": ref}
    _trigger_and_watch(cfg["repo"], "deploy.yml", ref, inputs, watch)
```

- [ ] **Step 3: Tests + Commit**

```bash
cd /c/Python/SKULD/Skuld-master/ops/skuld-cli && python -m pytest tests/ -q
git -C /c/Python/SKULD/Skuld-master add ops/skuld-cli/
git -C /c/Python/SKULD/Skuld-master commit -m "feat(cli): key add/remove/list, rollback"
```

---

### Task 7: Doku-Widersprüche bereinigen (P2, P3)

**Files:**
- Modify: `docs/deployment-contract.md`
- Modify: `ops/PROVISIONING.md`
- Modify: `ops/environments.yaml`

- [ ] **Step 1: Tote Referenzen finden**

Run: `grep -rn "skuld-1\|skuld-2\|<alte-ip>\|Helsinki\|setup-home-server" docs/ ops/*.md ops/environments.yaml`

- [ ] **Step 2: `deployment-contract.md` bereinigen** — tote Server als „(historisch)" markieren oder entfernen, aktive Server-Tabelle aus `environments.yaml` eintragen.

- [ ] **Step 3: `PROVISIONING.md` + `environments.yaml`-Kommentar** — `setup-home-server.sh` durch `skuld setup` ersetzen.

- [ ] **Step 4: Commit**

```bash
git -C /c/Python/SKULD/Skuld-master add docs/ ops/PROVISIONING.md ops/environments.yaml
git -C /c/Python/SKULD/Skuld-master commit -m "docs: tote Server-Referenzen bereinigt, Prod/Test-Rollen klar (P2/P3)"
```

---

### Task 8: Runbook auf dem Desktop schreiben

**Files:**
- Create: `C:\Users\I522043\OneDrive - SAP SE\Desktop\SKULD-RUNBOOK.md` (NICHT im Repo!)

- [ ] **Step 1: Runbook schreiben** mit folgenden Abschnitten (alle mit Copy-Paste-Befehlen):

  1. Überblick & Server-Landschaft (Tabelle aus environments.yaml)
  2. Phase 0 — Fuß in die Tür (ssh-keygen, Web-Console, Test)
  3. Phase 1 — Wizard starten: `skuld setup` (alle Fragen erklärt)
  4. Phase 2 — Zugangs-Übergang (deploy-Key testen → root bleibt auf prohibit-password; Web-Console als Notfall)
  5. Deploy & Betrieb (`skuld deploy`, `skuld status`, Logs)
  6. Rollback (`skuld rollback test <sha>`)
  7. SSH-Key-Verwaltung (`skuld key add/remove/list`)
  8. Secrets (vollständige Liste aller benötigten GitHub-Secrets + Rotations-Hinweis via `gh secret set`)
  9. Katastrophenfall — ⚠️ LÜCKE ehrlich benennen: aktuell kein Off-Site-Backup; Nachrüst-Weg beschreiben (pg_dump | gpg | rclone → Backblaze B2)
  10. Fehlerbehebung (Docker-Repo, UFW, Runner, Cert/Domain)

- [ ] **Step 2: Verifizieren, dass Runbook NICHT im Repo liegt**

Run: `git -C /c/Python/SKULD/Skuld-master status --short | grep -i runbook || echo "OK: Runbook nicht im Repo"`

---

### Task 9: Live-Test auf dem neuen Server (Definition of Done)

**Voraussetzung:** User hat Phase 0 erledigt (`ssh root@<ip>` klappt ohne Passwort).

- [ ] **Step 1: Mit User klären** — IP des neuen Servers, Phase 0 erledigt?, Runner-Token vorhanden?

- [ ] **Step 2: Wizard starten**

```bash
cd /c/Python/SKULD/Skuld-master/ops/skuld-cli
python -m skuld_cli.cli setup
```

Wizard fragt durch: IP, Umgebung `<env-name>`, Rolle `test`, Domain, DB-Wahl.

- [ ] **Step 3: Härtung verifizieren**

```bash
ssh deploy@<ip> 'sshd -T | grep -E "maxauthtries|permitrootlogin|passwordauthentication"; systemctl is-active fail2ban; ufw status'
```
Erwartung: `maxauthtries 2`, `permitrootlogin prohibit-password`, fail2ban `active`, UFW `active`.

- [ ] **Step 4: SKULD deployen**

DNS auf neue IP zeigen lassen, dann: `skuld deploy <env-name>`

- [ ] **Step 5: Isolation bestätigen** — bestehendes Prod unberührt, `skuld status` zeigt beide getrennt.

- [ ] **Step 6: Abschluss** — finishing-a-development-branch aufrufen.

---

## Self-Review

- Baustein 1 (eine Härtungs-Wahrheit) → Tasks 1-3 (OS-Guard, MaxAuthTries, fail2ban, ROLE) ✓
- Baustein 2 (zwei Wege) → Task 4 (cloud-init Bootstrap) + Task 5 (`skuld setup` = Weg A) ✓
- Baustein 3 (skuld setup Wizard) → Task 5 ✓
- Baustein 4 (Prod/Test getrennt) → Task 3 (ROLE) + Task 7 (Rollen-Doku) + Task 9 Step 5 ✓
- Baustein 5 (Runbook Desktop) → Task 8 ✓
- P1 (Divergenz) → Tasks 2+4 ✓ · P2/P3 (Doku) → Task 7 ✓ · P5 (Backup-Lücke) → Task 8 ✓
- DoD Live-Test → Task 9 ✓
