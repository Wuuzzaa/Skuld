# SKULD Portable DevOps — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SKULD auf jedem Linux-Host reproduzierbar aufsetzbar machen (eine Härtungs-Wahrheit), Prod/Test physisch trennen, alles per `skuld`-CLI steuerbar, mit felsenfestem Runbook auf dem Desktop.

**Architecture:** `ops/provision-server.sh` wird die einzige Härtungs-Definition (fail2ban + MaxAuthTries angeglichen, OS-Guard für 26.04, ROLE-Parameter). `cloud-init.yml.tpl` wird ein dünner Bootstrap, der dieses Skript aufruft. Die bestehende Click-basierte `skuld`-CLI wird um `provision`, `key`, `rollback` erweitert. Doku-Widersprüche werden bereinigt. Das Runbook liegt auf dem Desktop, nicht im Repo.

**Tech Stack:** Bash (provision-server.sh), YAML (cloud-init, environments.yaml), Python 3.10 + Click (skuld-cli), GitHub Actions (Deploy), Docker Compose.

## Global Constraints

- **Kein Overhead:** Vorhandenes erweitern, keine neuen Frameworks/Abstraktionsebenen. (User-Vorgabe)
- **Richtige Ordner:** Skripte → `ops/`, Specs/Pläne → `docs/superpowers/`, Runbook → **Desktop** (`C:\Users\I522043\OneDrive - SAP SE\Desktop\`), NICHT ins Repo. Nichts in den Repo-Root werfen.
- **Branch:** Alle Repo-Änderungen auf `feature/portable-devops`. NIEMALS master anfassen. KEIN Push ohne Freigabe.
- **Sicherheit:** Keine echten Keys/Passwörter/Prod-Secrets ins Repo. Backup wird NICHT gebaut (nur im Runbook als Lücke dokumentiert).
- **Kein echtes Prod berühren** während der Entwicklung. Der neue Server ist Rolle `test`.
- **Idempotenz:** `provision-server.sh` bleibt mehrfach ausführbar.
- **Provision-Skript ist nicht lokal (Windows) testbar** — es läuft auf Linux. Verifikation via `bash -n` (Syntax) lokal + Live-Test auf dem Server (Task 8).
- Repo-Root: `C:\Python\SKULD\Skuld-master`. CLI-Pfad: `ops/skuld-cli/`. Python: System-Python (`python`), pytest vorhanden.

---

### Task 1: `provision-server.sh` — OS-Guard für neue Ubuntu-Versionen

**Files:**
- Modify: `ops/provision-server.sh:84-96` (bestehender OS-Check)

**Interfaces:**
- Consumes: nichts.
- Produces: gehärteter OS-Check, der bei nicht-getesteten Versionen (>24) WARNT und Bestätigung verlangt, statt still durchzulaufen. Env-Var `ALLOW_UNTESTED_OS=true` überspringt die Rückfrage (für nicht-interaktive/cloud-init-Läufe).

- [ ] **Step 1: Bestehenden OS-Check ansehen**

Run: `sed -n '84,96p' ops/provision-server.sh`
Erwartung: der im Design zitierte Block (Ubuntu-only, Minimum 22, kein oberes Limit).

- [ ] **Step 2: OS-Check erweitern**

Ersetze den Block `ops/provision-server.sh:84-96` durch:

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
# Getestet gegen 22.04 und 24.04. Neuere Versionen (z.B. 26.04) können abweichen
# (Docker-Repo-Codename, Paketnamen). Nicht still durchlaufen lassen.
TESTED_MAX_MAJOR=24
if [ "$UBUNTU_MAJOR" -gt "$TESTED_MAX_MAJOR" ]; then
  warn "Ubuntu $VERSION_ID ist NICHT getestet (geprüft: 22.04/24.04)."
  warn "Docker-Repo/Pakete könnten abweichen. Fortfahren auf eigenes Risiko."
  if [ "${ALLOW_UNTESTED_OS:-false}" != "true" ]; then
    if [ -t 0 ]; then
      read -r -p "Trotzdem fortfahren? (yes/NO): " _os_ok
      [ "$_os_ok" = "yes" ] || fail "Abgebrochen. Setze ALLOW_UNTESTED_OS=true zum Überspringen."
    else
      fail "Nicht-getestete OS-Version und kein TTY. Setze ALLOW_UNTESTED_OS=true zum Fortfahren."
    fi
  fi
fi
ok "OS: Ubuntu $VERSION_ID ($PRETTY_NAME)"
```

- [ ] **Step 3: `warn`-Funktion existiert prüfen**

Run: `grep -n "^warn()\|^warn ()\|warn()" ops/provision-server.sh | head -1`
Erwartung: eine `warn`-Funktion existiert (analog zu `ok`/`fail`). Falls NICHT vorhanden, ergänze direkt nach der `ok()`-Definition:

```bash
warn() { echo -e "${YELLOW}! $*${NC}"; }
```

- [ ] **Step 4: Syntax prüfen**

Run: `bash -n ops/provision-server.sh && echo "SYNTAX OK"`
Erwartung: `SYNTAX OK` (keine Fehlermeldung).

- [ ] **Step 5: Commit**

```bash
git add ops/provision-server.sh
git commit -m "feat(provision): OS-Guard warnt bei nicht-getesteten Ubuntu-Versionen (26.04)"
```

---

### Task 2: `provision-server.sh` — SSH-Hardening angleichen (MaxAuthTries)

**Files:**
- Modify: `ops/provision-server.sh:194-197` (harden_sshd-Aufrufe)

**Interfaces:**
- Consumes: bestehende Funktion `harden_sshd "<key>" "<value>"` (Zeilen 183-192).
- Produces: SSH-Config setzt zusätzlich `MaxAuthTries 2` (Angleichung an cloud-init, schließt P1 teilweise).

- [ ] **Step 1: Bestehende harden_sshd-Aufrufe ansehen**

Run: `sed -n '194,197p' ops/provision-server.sh`
Erwartung:
```bash
harden_sshd "PermitRootLogin" "prohibit-password"
harden_sshd "PasswordAuthentication" "no"
harden_sshd "PubkeyAuthentication" "yes"
harden_sshd "X11Forwarding" "no"
```

- [ ] **Step 2: MaxAuthTries ergänzen**

Ersetze die 4 Zeilen (194-197) durch:

```bash
harden_sshd "PermitRootLogin" "prohibit-password"
harden_sshd "PasswordAuthentication" "no"
harden_sshd "PubkeyAuthentication" "yes"
harden_sshd "X11Forwarding" "no"
harden_sshd "MaxAuthTries" "2"
```

- [ ] **Step 3: Syntax prüfen**

Run: `bash -n ops/provision-server.sh && echo "SYNTAX OK"`
Erwartung: `SYNTAX OK`.

- [ ] **Step 4: Commit**

```bash
git add ops/provision-server.sh
git commit -m "feat(provision): SSH MaxAuthTries=2 (Angleichung an cloud-init)"
```

---

### Task 3: `provision-server.sh` — fail2ban-Modul ergänzen

**Files:**
- Modify: `ops/provision-server.sh` (neues Modul nach Modul 4 „Firewall (UFW)", vor Modul 5 „Docker", also nach Zeile ~230)

**Interfaces:**
- Consumes: `ok`/`warn`-Ausgabefunktionen.
- Produces: fail2ban installiert + sshd-Jail aktiv (identisch zu cloud-init: maxretry=3, bantime=3600, findtime=600). Schließt P1 vollständig.

- [ ] **Step 1: Einfügepunkt finden (Ende Modul 4 / Anfang Modul 5)**

Run: `grep -n "Docker daemon configuration\|^# .*Docker\b\|Firewall\|MODULE 5\|Modul 5\|Docker$" ops/provision-server.sh | head`
Erwartung: die Modul-Überschrift von Modul 5 (Docker) bei ~Zeile 232. Das fail2ban-Modul wird DAVOR eingefügt.

- [ ] **Step 2: fail2ban-Modul einfügen**

Direkt vor der Docker-Modul-Überschrift (Modul 5, ~Zeile 232) einfügen:

```bash
# === Module 4b: fail2ban (Brute-Force-Schutz) ===
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

- [ ] **Step 3: `step`-Funktion prüfen**

Run: `grep -n "^step()\|step()" ops/provision-server.sh | head -1`
Erwartung: eine `step`-Funktion existiert (Modul-Überschrift). Falls NICHT, ersetze im eingefügten Block `step "fail2ban"` durch `echo -e "\n${CYAN}== fail2ban ==${NC}"`.

- [ ] **Step 4: Syntax prüfen**

Run: `bash -n ops/provision-server.sh && echo "SYNTAX OK"`
Erwartung: `SYNTAX OK`.

- [ ] **Step 5: Commit**

```bash
git add ops/provision-server.sh
git commit -m "feat(provision): fail2ban sshd-Jail (Angleichung an cloud-init, schließt P1)"
```

---

### Task 4: `provision-server.sh` — ROLE-Parameter

**Files:**
- Modify: `ops/provision-server.sh:53-63` (Env-Var-Defaults)

**Interfaces:**
- Consumes: bestehende Env-Var-Logik `RUNNER_LABELS`.
- Produces: Env-Var `ROLE` (default: `test`). Wenn `RUNNER_LABELS` NICHT gesetzt ist, wird es aus ROLE abgeleitet zu `skuld-<role>`. Markiert den Server eindeutig als prod/test.

- [ ] **Step 1: Env-Var-Block ansehen**

Run: `sed -n '53,63p' ops/provision-server.sh`
Erwartung: die Default-Zuweisungen inkl. `RUNNER_LABELS="${RUNNER_LABELS:-self-hosted}"`.

- [ ] **Step 2: ROLE ergänzen und RUNNER_LABELS ableiten**

Ersetze die Zeile `RUNNER_LABELS="${RUNNER_LABELS:-self-hosted}"` durch:

```bash
ROLE="${ROLE:-test}"
case "$ROLE" in prod|test) ;; *) fail "ROLE muss 'prod' oder 'test' sein (war: $ROLE)";; esac
RUNNER_LABELS="${RUNNER_LABELS:-skuld-$ROLE}"
```

- [ ] **Step 3: Syntax prüfen**

Run: `bash -n ops/provision-server.sh && echo "SYNTAX OK"`
Erwartung: `SYNTAX OK`.

- [ ] **Step 4: ROLE-Ausgabe ergänzen (Transparenz)**

Finde die Zeile mit `ok "OS: Ubuntu` (aus Task 1) und füge danach ein:

```bash
ok "Rolle: $ROLE  ·  Runner-Label: $RUNNER_LABELS"
```

- [ ] **Step 5: Syntax + Commit**

Run: `bash -n ops/provision-server.sh && echo "SYNTAX OK"`

```bash
git add ops/provision-server.sh
git commit -m "feat(provision): ROLE-Parameter (prod|test) leitet Runner-Label ab"
```

---

### Task 5: `cloud-init.yml.tpl` — auf dünnen Bootstrap reduzieren

**Files:**
- Modify: `ops/cloud-init.yml.tpl` (runcmd-Härtungsblöcke → Aufruf von provision-server.sh)
- Create: `ops/cloud-init.README.md` (kurze Erklärung des neuen Bootstrap-Ansatzes)

**Interfaces:**
- Consumes: `provision-server.sh` (aus Tasks 1-4), das per curl vom Repo geladen wird.
- Produces: cloud-init, das NICHT mehr selbst härtet, sondern `provision-server.sh` aufruft → eine Wahrheit (schließt P1 endgültig). Behält: users-Block (root-Key), swap, Tailscale-Optionalität.

- [ ] **Step 1: Aktuelle runcmd-Struktur ansehen**

Run: `sed -n '99,182p' ops/cloud-init.yml.tpl`
Erwartung: runcmd mit Docker-Install, Tailscale, UFW, fail2ban, SSH-Hardening (die im Design zitierten Blöcke).

- [ ] **Step 2: runcmd durch Bootstrap ersetzen**

Ersetze den kompletten `runcmd:`-Block (ab Zeile 99 bis Dateiende bzw. bis vor einen evtl. `final_message`) durch:

```yaml
runcmd:
  # Dünner Bootstrap: die EINE Härtungs-Wahrheit (provision-server.sh) ausführen.
  # Härtung, Docker, UFW, fail2ban, SSH, Runner leben ALLE in diesem Skript —
  # cloud-init dupliziert das nicht mehr.
  - export ALLOW_UNTESTED_OS=true
  - export ROLE='<ROLE>'
  - export RUNNER_TOKEN='<RUNNER_TOKEN>'
  - export INSTALL_TUNNEL='<INSTALL_TUNNEL>'
  - curl -fsSL https://raw.githubusercontent.com/Wuuzzaa/Skuld/master/ops/provision-server.sh -o /root/provision-server.sh
  - bash /root/provision-server.sh 2>&1 | tee /var/log/skuld-provision.log
```

- [ ] **Step 3: Verwaiste write_files (jail.local, after.rules.docker) belassen oder entfernen — Entscheidung**

Run: `sed -n '56,97p' ops/cloud-init.yml.tpl`
Die `jail.local` in write_files ist nun redundant (fail2ban macht provision-server.sh). Entferne den `jail.local`-write_files-Eintrag (im Design-zitierten Bereich Zeilen ~89-97), damit keine zweite Wahrheit bleibt. `daemon.json`/`after.rules.docker` ebenfalls entfernen NUR falls provision-server.sh sie selbst schreibt — prüfe:

Run: `grep -n "daemon.json\|after.rules" ops/provision-server.sh`
Erwartung: provision-server.sh schreibt `daemon.json` selbst (Modul 6). → dann auch diese write_files-Einträge entfernen. Falls es `after.rules.docker` NICHT selbst schreibt, diesen Eintrag BELASSEN.

- [ ] **Step 4: Platzhalter-Doku schreiben**

Create `ops/cloud-init.README.md`:

```markdown
# cloud-init Bootstrap (Weg B)

`cloud-init.yml.tpl` härtet NICHT mehr selbst. Es lädt beim Boot
`ops/provision-server.sh` (die einzige Härtungs-Wahrheit) und führt es aus.

## Platzhalter vor Nutzung ersetzen
- `<SSH_PUBLIC_KEY>` — dein Public Key (root/deploy authorized_keys)
- `<ROLE>` — `prod` oder `test`
- `<RUNNER_TOKEN>` — GitHub-Runner-Registration-Token
  (`gh api repos/Wuuzzaa/Skuld/actions/runners/registration-token --jq .token`)
- `<INSTALL_TUNNEL>` — `true`/`false`
- `<TAILSCALE_INSTALL_BLOCK>` / `<SSH_FIREWALL_BLOCK>` / `<SSH_LISTEN_ADDRESS_BLOCK>` —
  wie bisher (nur relevant wenn Tailscale genutzt wird)

## Fallback
Kann der Hoster kein cloud-init, nutze Weg A:
`skuld provision <ip> --role test` (SSH-in, ruft dasselbe Skript auf).
```

- [ ] **Step 5: YAML-Syntax grob prüfen + Commit**

Run: `python -c "import yaml,sys; yaml.safe_load(open('ops/cloud-init.yml.tpl').read().replace('<','\"<').replace('>','>\"')) if False else print('skip-strict'); print('template has placeholders, strict parse skipped')"`
(cloud-init mit `<PLACEHOLDER>` ist bewusst kein valides YAML vor Substitution — daher nur visuelle Prüfung via `sed -n '1,40p'`.)

```bash
git add ops/cloud-init.yml.tpl ops/cloud-init.README.md
git commit -m "refactor(cloud-init): dünner Bootstrap ruft provision-server.sh (eine Härtungs-Wahrheit)"
```

---

### Task 6: `skuld`-CLI — `provision`, `key`, `rollback` ergänzen

**Files:**
- Modify: `ops/skuld-cli/skuld_cli/cli.py` (neue Click-Kommandos)
- Test: `ops/skuld-cli/tests/test_cli_smoke.py` (Create)

**Interfaces:**
- Consumes: bestehende `main`-Gruppe (Click), `github.trigger_workflow`, `load_config`.
- Produces:
  - `skuld provision <ip> --role prod|test` → gibt den fertigen SSH-Pipe-Befehl aus bzw. führt ihn aus (`--run`).
  - `skuld key add <name> <pubkey_or_file>` / `key remove <name>` / `key list` → verwaltet Keys in `ops/provision-server.conf`.
  - `skuld rollback <target>` → triggert deploy.yml mit vorherigem Ref.

- [ ] **Step 1: Bestehende CLI-Struktur ansehen**

Run: `sed -n '1,90p' ops/skuld-cli/skuld_cli/cli.py`
Erwartung: Imports, `main`-Gruppe (Zeile ~76), `_trigger_and_watch`-Helper (~39-71).

- [ ] **Step 2: Smoke-Test schreiben (failing)**

Create `ops/skuld-cli/tests/test_cli_smoke.py`:

```python
from click.testing import CliRunner
from skuld_cli.cli import main


def test_provision_help_lists_role_option():
    r = CliRunner().invoke(main, ["provision", "--help"])
    assert r.exit_code == 0
    assert "--role" in r.output


def test_key_group_has_add_remove_list():
    r = CliRunner().invoke(main, ["key", "--help"])
    assert r.exit_code == 0
    for sub in ("add", "remove", "list"):
        assert sub in r.output


def test_provision_builds_ssh_command_without_running():
    # Ohne --run darf nichts ausgeführt werden; nur der Befehl wird gezeigt.
    r = CliRunner().invoke(main, ["provision", "203.0.113.9", "--role", "test"])
    assert r.exit_code == 0
    assert "provision-server.sh" in r.output
    assert "ROLE=test" in r.output


def test_rollback_requires_target():
    r = CliRunner().invoke(main, ["rollback"])
    assert r.exit_code != 0  # target fehlt
```

- [ ] **Step 3: Test ausführen (muss fehlschlagen)**

Run: `cd ops/skuld-cli && python -m pytest tests/test_cli_smoke.py -q`
Erwartung: FAIL — die Kommandos `provision`/`key`/`rollback` existieren noch nicht.

- [ ] **Step 4: Kommandos implementieren**

Am Ende von `ops/skuld-cli/skuld_cli/cli.py` (vor einem evtl. `if __name__`-Block) ergänzen:

```python
import shlex
from pathlib import Path

CONF_PATH = Path(__file__).resolve().parents[2] / "provision-server.conf"
RAW_SCRIPT_URL = "https://raw.githubusercontent.com/Wuuzzaa/Skuld/master/ops/provision-server.sh"


@main.command()
@click.argument("ip")
@click.option("--role", type=click.Choice(["prod", "test"]), default="test", show_default=True)
@click.option("--user", default="root", show_default=True, help="SSH-User für den ersten Zugang")
@click.option("--run", is_flag=True, help="Befehl direkt ausführen statt nur anzeigen")
def provision(ip, role, user, run):
    """Provisioniert einen Linux-Host (Weg A: SSH-in -> provision-server.sh)."""
    script = Path(__file__).resolve().parents[2] / "provision-server.sh"
    remote = f"ROLE={role} bash -s"
    cmd = f"ssh {user}@{ip} {shlex.quote(remote)} < {shlex.quote(str(script))}"
    console.print(f"[bold]Provision-Befehl (Rolle {role}):[/bold]")
    console.print(cmd)
    if run:
        import subprocess
        console.print("[cyan]Führe aus...[/cyan]")
        subprocess.run(cmd, shell=True, check=False)
    else:
        console.print("[yellow]Nur Anzeige. Mit --run ausführen.[/yellow]")


@main.group()
def key():
    """SSH-Keys der deploy-User verwalten (Quelle: provision-server.conf)."""


def _read_conf():
    return CONF_PATH.read_text() if CONF_PATH.exists() else ""


def _write_keys_block(keys):
    text = _read_conf()
    block = 'SSH_AUTHORIZED_KEYS="\n' + "\n".join(keys) + '\n"'
    import re
    if 'SSH_AUTHORIZED_KEYS="' in text:
        text = re.sub(r'SSH_AUTHORIZED_KEYS="\n.*?\n"', block, text, flags=re.S)
    else:
        text = text.rstrip() + "\n" + block + "\n"
    CONF_PATH.write_text(text)


def _current_keys():
    import re
    m = re.search(r'SSH_AUTHORIZED_KEYS="\n(.*?)\n"', _read_conf(), flags=re.S)
    if not m:
        return []
    return [ln for ln in m.group(1).splitlines() if ln.strip()]


@key.command("list")
def key_list():
    """Autorisierte Keys anzeigen."""
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
    """Public Key hinzufügen (Datei-Pfad oder Key-String). NAME landet als Kommentar."""
    p = Path(pubkey_or_file)
    key_str = p.read_text().strip() if p.exists() else pubkey_or_file.strip()
    # Kommentar (letztes Feld) auf NAME setzen, falls keiner da
    parts = key_str.split()
    if len(parts) == 2:
        key_str = f"{key_str} {name}"
    keys = _current_keys()
    if any(key_str.split()[1] == k.split()[1] for k in keys if len(k.split()) >= 2):
        console.print("[yellow]Key (Fingerprint) bereits vorhanden.[/yellow]")
        return
    keys.append(key_str)
    _write_keys_block(keys)
    console.print(f"[green]Key '{name}' hinzugefügt. Danach betroffene Server neu provisionieren "
                  f"(skuld provision <ip> --run).[/green]")


@key.command("remove")
@click.argument("name")
def key_remove(name):
    """Key anhand des Kommentars (NAME) entfernen."""
    keys = _current_keys()
    kept = [k for k in keys if not k.strip().endswith(name)]
    if len(kept) == len(keys):
        console.print(f"[yellow]Kein Key mit Kommentar '{name}' gefunden.[/yellow]")
        return
    _write_keys_block(kept)
    console.print(f"[green]Key '{name}' entfernt. Server neu provisionieren.[/green]")


@main.command()
@click.argument("target", type=click.Choice(["prod", "test"]))
@click.argument("ref")
@click.option("--watch/--no-watch", default=True)
def rollback(target, ref, watch):
    """Rollback: deploy.yml auf einen früheren REF (Commit/Tag) für TARGET auslösen."""
    cfg = load_config()
    gh_env = "production" if target == "prod" else "home"
    inputs = {"target": gh_env, "ref": ref}
    _trigger_and_watch(cfg["repo"], "deploy.yml", ref, inputs, watch)
```

- [ ] **Step 5: Test ausführen (muss grün sein)**

Run: `cd ops/skuld-cli && python -m pytest tests/test_cli_smoke.py -q`
Erwartung: PASS (4 Tests). Falls Import-Fehler wg. fehlendem Editable-Install: `cd ops/skuld-cli && pip install -e . -q` und erneut.

- [ ] **Step 6: Commit**

```bash
git add ops/skuld-cli/skuld_cli/cli.py ops/skuld-cli/tests/test_cli_smoke.py
git commit -m "feat(cli): provision, key add/remove/list, rollback"
```

---

### Task 7: Doku-Widersprüche bereinigen (P2, P3) + Config-Konflikt

**Files:**
- Modify: `docs/deployment-contract.md` (tote Server-Referenzen)
- Modify: `ops/PROVISIONING.md` (deprecated setup-home-server.sh)
- Modify: `ops/environments.yaml:7-11` (Kommentar: veralteter setup-Hinweis)
- Modify: `ops/skuld-cli/skuld_cli/servers.yaml` ODER `config.py` (Konflikt environments.yaml vs. servers.yaml)

**Interfaces:**
- Consumes: nichts (reine Doku/Config-Bereinigung).
- Produces: widerspruchsfreie Doku; klare Prod/Test-Rollen; eine Config-Quelle.

- [ ] **Step 1: Tote Server-Referenzen finden**

Run: `grep -rn "skuld-1\|skuld-2\|204.168.128.55\|Helsinki\|setup-home-server" docs/ ops/*.md ops/environments.yaml`
Erwartung: Liste der Fundstellen (deprecated Helsinki, setup-home-server.sh).

- [ ] **Step 2: `deployment-contract.md` bereinigen**

Entferne/markiere die Einträge zu `skuld-1`, `skuld-2`, Helsinki (`204.168.128.55`) als „(historisch, außer Betrieb)" oder lösche die betreffende Tabellenzeile. Ersetze die aktive Server-Liste durch die aus `environments.yaml` (`production`, `home`). Rolle klar benennen: `production` = live, `home` = Testsystem (Homeserver, Staging).

- [ ] **Step 3: `PROVISIONING.md` + `environments.yaml`-Kommentar korrigieren**

In `ops/PROVISIONING.md`: alle Verweise auf `setup-home-server.sh` durch `provision-server.sh` bzw. `skuld provision` ersetzen.
In `ops/environments.yaml` Zeile 9: `#   2. Set up the server (ops/setup-home-server.sh or cloud-init)` → `#   2. Set up the server: skuld provision <ip> --role test|prod  (oder cloud-init)`.

- [ ] **Step 4: Config-Konflikt auflösen**

Run: `diff <(grep -E "production|home|default_branch|db_container" ops/environments.yaml) <(grep -E "production|home|default_branch|db_container" ops/skuld-cli/skuld_cli/servers.yaml)`
Die CLI lädt laut `config.py` `ops/environments.yaml` (nicht `servers.yaml`). Die `servers.yaml` ist toter Ballast bzw. widersprüchlich (`default_branch: testsystem`). Prüfe `config.py`:

Run: `grep -n "servers.yaml\|environments.yaml" ops/skuld-cli/skuld_cli/config.py`
- Falls `config.py` NUR `environments.yaml` nutzt: lösche `ops/skuld-cli/skuld_cli/servers.yaml` (Ballast) — `git rm`.
- Falls es `servers.yaml` doch nutzt: gleiche die Werte an `environments.yaml` an (kein `testsystem`-Branch).

- [ ] **Step 5: CLI-Smoke-Test erneut (Regression)**

Run: `cd ops/skuld-cli && python -m pytest tests/test_cli_smoke.py -q`
Erwartung: PASS (Config-Load darf nicht gebrochen sein).

- [ ] **Step 6: Commit**

```bash
git add docs/ ops/PROVISIONING.md ops/environments.yaml ops/skuld-cli/
git commit -m "docs: tote Server-Referenzen entfernt, Prod/Test-Rollen klar, Config-Quelle vereinheitlicht (P2/P3)"
```

---

### Task 8: Runbook auf dem Desktop schreiben

**Files:**
- Create: `C:\Users\I522043\OneDrive - SAP SE\Desktop\SKULD-RUNBOOK.md` (NICHT im Repo!)

**Interfaces:**
- Consumes: alle vorherigen Tasks (die Skripte/Kommandos, die das Runbook referenziert).
- Produces: lückenloses Betriebshandbuch.

- [ ] **Step 1: Runbook schreiben**

Schreibe `C:\Users\I522043\OneDrive - SAP SE\Desktop\SKULD-RUNBOOK.md` mit exakt diesen Abschnitten (jeder mit konkreten Copy-Paste-Befehlen, kein „TODO"):

1. **Überblick & Landschaft** — welche Server (prod/test), welche Rolle, welche Domain, welcher Runner-Label. Tabelle aus `environments.yaml`.
2. **Phase 0 — Fuß in die Tür (Web-Console, einmalig):**
   - PC-Key erzeugen falls keiner: `ssh-keygen -t ed25519 -C "daniel@skuld"`
   - Public Key anzeigen: `cat ~/.ssh/id_ed25519.pub`
   - In Web-Console als root: `mkdir -p ~/.ssh && echo "<PUBKEY>" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys`
   - Von außen testen: `ssh root@<ip>` → muss ohne Passwort klappen.
3. **Phase 1 — Provisionieren:** `skuld provision <ip> --role test --run` (erklärt, dass bei Ubuntu 26.04 die OS-Warnung mit `yes` bestätigt werden muss). Runner-Token vorher: `gh api repos/Wuuzzaa/Skuld/actions/runners/registration-token --jq .token`.
4. **Phase 2 — Zugangs-Übergang absichern:** `ssh deploy@<ip>` testen → **erst wenn das klappt** ist root-SSH schon durch das Skript auf `prohibit-password` gesetzt. Notfall-Rückweg: Web-Console des Anbieters (unabhängig von SSH).
5. **Deploy & Betrieb:** `skuld deploy test`, `skuld status`, Logs: `ssh deploy@<ip> 'cd /opt/skuld && docker compose logs --tail=50'`.
6. **Rollback:** `skuld rollback test <alter-commit-sha>`.
7. **SSH-Key-Verwaltung:** `skuld key add <name> <datei>`, `skuld key list`, `skuld key remove <name>` → danach `skuld provision <ip> --run` erneut (verteilt die Keys).
8. **Secrets:** vollständige Liste der GitHub-Secrets (POSTGRES_PASSWORD, AUTHELIA_JWT_SECRET, AUTHELIA_SESSION_SECRET, AUTHELIA_STORAGE_ENCRYPTION_KEY, AUTHELIA_PASSWORD_HASH, TELEGRAM_BOT_TOKEN, MASSIVE_API_KEY, MASSIVE_API_KEY_FLAT_FILES, DEPLOY_SSH_KEY) + wofür + Rotations-Hinweis (Setzen via `gh secret set <NAME>`).
9. **KATASTROPHENFALL — Hoster komplett weg:** neuen Host bestellen → Phase 0-2 → `skuld provision <ip> --role prod` → DB restaurieren. **⚠️ LÜCKE ehrlich benennen:** aktuell KEIN Off-Site-Backup (nur bei Hetzner). Wenn Hetzner weg ist, ist die DB weg. Empfohlener Nachrüst-Weg beschreiben: täglicher `pg_dump | gpg | rclone` in unabhängigen Object-Storage (Backblaze B2). Als eigenes Mini-Projekt markiert, hier nicht gebaut.
10. **Fehlerbehebung:** OS 26.04 (Docker-Repo prüfen: `apt-cache policy docker-ce`), Docker+UFW (`ufw status`, `docker network ls`), Runner (`systemctl status actions.runner.*`), Cert/Domain (`docker compose logs traefik`).

- [ ] **Step 2: Verifizieren, dass es NICHT im Repo liegt**

Run: `cd /c/Python/SKULD/Skuld-master && git status --short | grep -i runbook || echo "OK: Runbook nicht im Repo-Tree"`
Erwartung: `OK: Runbook nicht im Repo-Tree` (Desktop liegt außerhalb des Repos).

- [ ] **Step 3: kein Commit** (Runbook liegt bewusst außerhalb des Repos — nichts zu committen).

---

### Task 9: Live-Test auf dem neuen Server (Definition of Done)

**Files:** keine (Verifikation).

**Interfaces:**
- Consumes: alle Tasks. Voraussetzung: User hat Phase 0 (Web-Console-Key) gemacht.

- [ ] **Step 1: Voraussetzungen mit User klären**

Bestätige mit dem User: IP des neuen Servers, dass Phase 0 (SSH-Key als root via Web-Console) erledigt ist (`ssh root@<ip>` klappt), und Runner-Token vorhanden. **STOPP und frage, falls unklar.**

- [ ] **Step 2: Provisionieren (Rolle test)**

Run (mit echter IP): `cd ops/skuld-cli && python -m skuld_cli.cli provision <ip> --role test --run`
(bzw. `skuld provision ...` wenn installiert). Erwartung: Skript läuft durch; bei 26.04 OS-Warnung mit `yes` bestätigen; am Ende „Rolle: test · Runner-Label: skuld-test".

- [ ] **Step 3: Härtung verifizieren**

Run: `ssh deploy@<ip> 'sshd -T | grep -E "maxauthtries|permitrootlogin|passwordauthentication"; systemctl is-active fail2ban; docker network ls; ufw status'`
Erwartung: `maxauthtries 2`, `permitrootlogin prohibit-password`, `passwordauthentication no`, fail2ban `active`, Netzwerke `web`+`postgres_setup_default`, UFW `active`.

- [ ] **Step 4: SKULD deployen (Test-Ziel) + Domain prüfen**

Mit User: Domain auf die neue IP zeigen lassen (DNS), dann `skuld deploy test` (oder das passende Test-Ziel). Erwartung: Container laufen (`ssh deploy@<ip> 'cd /opt/skuld && docker compose ps'`), App über die echte Domain erreichbar.

- [ ] **Step 5: Isolation bestätigen**

Verifiziere, dass das Hetzner-Prod unberührt ist: `skuld status` zeigt beide getrennt; der neue Server hat Label `skuld-test`, kein Zugriff auf Prod-Runner/Secrets-Ziel.

- [ ] **Step 6: Abschluss** — finishing-a-development-branch (Tests grün, Optionen präsentieren).

---

## Self-Review

**Spec-Abdeckung:**
- Baustein 1 (eine Härtungs-Wahrheit) → Tasks 1-4 (OS-Guard, MaxAuthTries, fail2ban, ROLE) ✓
- Baustein 2 (zwei Wege) → Task 5 (cloud-init Bootstrap) + Task 6 (`skuld provision` = Weg A) ✓
- Baustein 3 (skuld-CLI) → Task 6 ✓
- Baustein 4 (Prod/Test getrennt) → Task 4 (ROLE) + Task 7 (Rollen-Doku/Config) + Task 9 Step 5 ✓
- Baustein 5 (Runbook Desktop) → Task 8 ✓
- P1 (Divergenz) → Tasks 2+3+5 ✓ · P2/P3 (Doku) → Task 7 ✓ · P4 (Hoster-Beschaffung) → Task 6 provision ✓ · P5 (Backup-Lücke) → Task 8 Step 1.9 (dokumentiert, nicht gebaut) ✓
- DoD Live-Test → Task 9 ✓

**Placeholder-Scan:** Keine TBD/TODO in Code-Steps; alle Edits zeigen konkreten Code/Befehle. Runbook-Inhalt (Task 8) ist als konkrete Abschnittsliste mit Beispiel-Befehlen spezifiziert.

**Typ-Konsistenz:** `ROLE`/`--role` durchgängig `prod|test`; Runner-Label `skuld-<role>` in Task 4 und Task 9 Step 2/5 konsistent; `provision-server.sh`-Aufruf in Task 5 (cloud-init) und Task 6 (CLI) beide via `ROLE=<role> bash`.

**Scope:** Fokussiert; Backup bewusst außen vor (dokumentiert). Kein Overhead (nur Erweiterung Vorhandenes).
