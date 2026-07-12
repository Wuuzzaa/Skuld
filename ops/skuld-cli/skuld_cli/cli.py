"""SKULD CLI – deploy and manage environments via GitHub Actions.

Every command triggers the corresponding GitHub Actions workflow so that
no developer needs direct SSH access or server credentials.  The only
prerequisite is an authenticated `gh` CLI (https://cli.github.com/).
"""

import json
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from . import github
from .config import get_env, get_repo, list_envs, load_config

console = Console()

ENV_NAMES = ["production", "home"]


def _ensure_gh():
    if not github.gh_available():
        console.print(
            "[red]Error:[/red] `gh` CLI not found.\n"
            "Install: https://cli.github.com/\n"
            "Then run: gh auth login"
        )
        sys.exit(1)
    if not github.check_gh_auth():
        console.print(
            "[red]Not authenticated.[/red] Run [bold]gh auth login[/bold] first."
        )
        sys.exit(1)


def _trigger_and_watch(repo: str, workflow: str, ref: str, inputs: dict, watch: bool):
    """Trigger a workflow, optionally watch it."""
    console.print(f"Triggering [bold]{workflow}[/bold] on [cyan]{ref}[/cyan] ...")
    for k, v in inputs.items():
        console.print(f"  {k} = {v}")

    # Record the time before triggering so we can identify *our* run
    # among potentially concurrent workflow runs.
    trigger_time = datetime.now(timezone.utc)

    ok = github.trigger_workflow(repo, workflow, ref=ref, inputs=inputs)
    if not ok:
        sys.exit(1)

    console.print("[green]Workflow triggered.[/green]")

    if not watch:
        console.print("Use [bold]skuld watch[/bold] or check GitHub Actions for progress.")
        return

    console.print("Waiting for run to appear ...")
    run = github.get_latest_run(repo, workflow, created_after=trigger_time)
    if not run:
        console.print("[yellow]Could not find the run. Check GitHub Actions manually.[/yellow]")
        return

    console.print(f"Run URL: {run.get('url', 'n/a')}")
    success = github.watch_run(repo, run["databaseId"])
    if success:
        console.print("[green]Done.[/green]")
    else:
        console.print("[red]Workflow failed.[/red]")
        sys.exit(1)


# ─── Main group ────────────────────────────────────────────────────────

@click.group()
@click.version_option(package_name="skuld-cli")
def main():
    """SKULD – deploy and manage environments via GitHub Actions."""


# ─── skuld deploy ──────────────────────────────────────────────────────

@main.command()
@click.argument("target", type=click.Choice(ENV_NAMES))
@click.option("--branch", "-b", default=None, help="Git ref to deploy (default: environment's default branch)")
@click.option("--watch/--no-watch", default=True, help="Stream logs until completion")
def deploy(target: str, branch: str | None, watch: bool):
    """Deploy a branch to a target environment.

    Examples:

        skuld deploy production

        skuld deploy home --branch feature/my-feature

        skuld deploy home --no-watch
    """
    _ensure_gh()
    cfg = load_config()
    env = get_env(cfg, target)
    repo = get_repo(cfg)
    ref = branch or env.get("default_branch", "master")

    inputs = {
        "target": target,  # YAML key matches workflow input (production/home)
        "ref": ref,
    }

    _trigger_and_watch(repo, "deploy.yml", ref="master", inputs=inputs, watch=watch)


# ─── skuld db ──────────────────────────────────────────────────────────

@main.group()
def db():
    """Database operations (backup, replicate, trigger jobs)."""


@db.command()
@click.argument("target", type=click.Choice(ENV_NAMES))
@click.option("--watch/--no-watch", default=True)
def backup(target: str, watch: bool):
    """Create a database backup on the target server.

    Example: skuld db backup production
    """
    _ensure_gh()
    cfg = load_config()
    env = get_env(cfg, target)
    repo = get_repo(cfg)

    inputs = {
        "target": target,  # YAML key matches workflow input
        "job": "db_backup",
    }

    _trigger_and_watch(repo, "trigger-jobs.yml", ref="master", inputs=inputs, watch=watch)


@db.command()
@click.option("--source", "-s", type=click.Choice(["production"]), default="production",
              help="Source environment for the backup")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@click.option("--watch/--no-watch", default=True)
def replicate(source: str, confirm: bool, watch: bool):
    """Replicate (copy) database from source to home server.

    Downloads the latest backup from source and restores it on the home
    server.  This REPLACES the home database.

    Example: skuld db replicate --source production
    """
    _ensure_gh()
    cfg = load_config()
    repo = get_repo(cfg)

    if not confirm:
        click.confirm(
            f"This will REPLACE the home-server database with data from {source}. Continue?",
            abort=True,
        )

    inputs = {
        "source": source,
        "confirm_restore": "RESTORE_HOME_DB",
        "restart_app": "true",
    }

    _trigger_and_watch(repo, "replicate-db-to-home.yml", ref="master", inputs=inputs, watch=watch)


@db.command()
@click.argument("target", type=click.Choice(ENV_NAMES))
@click.option("--watch/--no-watch", default=True)
def healthcheck(target: str, watch: bool):
    """Run a database health check on the target server.

    Example: skuld db healthcheck production
    """
    _ensure_gh()
    cfg = load_config()
    env = get_env(cfg, target)
    repo = get_repo(cfg)

    inputs = {
        "target": target,  # YAML key matches workflow input
        "job": "db_healthcheck",
    }

    _trigger_and_watch(repo, "trigger-jobs.yml", ref="master", inputs=inputs, watch=watch)


# ─── skuld jobs ────────────────────────────────────────────────────────

@main.group()
def jobs():
    """Trigger data collection jobs."""


@jobs.command(name="run")
@click.argument("target", type=click.Choice(ENV_NAMES))
@click.argument("job", type=click.Choice([
    "saturday_night", "option_data", "market_start_mid_end",
    "stock_data_daily", "historization",
]))
@click.option("--dry-run", is_flag=True, help="Show command without executing")
@click.option("--watch/--no-watch", default=True)
def run_job(target: str, job: str, dry_run: bool, watch: bool):
    """Trigger a data collection job on a target server.

    Examples:

        skuld jobs run production option_data

        skuld jobs run home saturday_night --dry-run
    """
    _ensure_gh()
    cfg = load_config()
    env = get_env(cfg, target)
    repo = get_repo(cfg)

    inputs = {
        "target": target,  # YAML key matches workflow input
        "job": job,
        "dry_run": str(dry_run).lower(),
    }

    _trigger_and_watch(repo, "trigger-jobs.yml", ref="master", inputs=inputs, watch=watch)


# ─── skuld status ──────────────────────────────────────────────────────

@main.command()
def status():
    """Show configured environments and recent workflow runs."""
    _ensure_gh()
    cfg = load_config()
    repo = get_repo(cfg)

    # Show environments
    table = Table(title="Environments")
    table.add_column("Name", style="bold")
    table.add_column("Host")
    table.add_column("Skuld Env")
    table.add_column("Domain")

    for name, env in list_envs(cfg).items():
        table.add_row(
            name,
            env.get("host", ""),
            env.get("skuld_env", ""),
            env.get("domain", ""),
        )
    console.print(table)

    # Show recent deploy runs
    console.print("\n[bold]Recent deploys:[/bold]")
    result = github._run_gh(
        ["run", "list", "--repo", repo, "--workflow", "deploy.yml",
         "--limit", "5", "--json", "databaseId,status,conclusion,headBranch,createdAt,displayTitle"],
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        runs = json.loads(result.stdout)
        run_table = Table()
        run_table.add_column("ID")
        run_table.add_column("Status")
        run_table.add_column("Branch")
        run_table.add_column("Title")
        run_table.add_column("Created")
        for r in runs:
            status_str = r.get("conclusion") or r.get("status", "?")
            style = "green" if status_str == "success" else "red" if status_str == "failure" else "yellow"
            run_table.add_row(
                str(r["databaseId"]),
                f"[{style}]{status_str}[/{style}]",
                r.get("headBranch", "?"),
                r.get("displayTitle", "?"),
                r.get("createdAt", "?")[:19],
            )
        console.print(run_table)
    else:
        console.print("[dim]No recent runs found.[/dim]")


# ─── skuld doctor ──────────────────────────────────────────────────────

@main.command()
def doctor():
    """Check that all prerequisites are met.

    Verifies that `gh` is installed, authenticated, and can reach the
    SKULD repository.  Run this first if something doesn't work.
    """
    cfg = load_config()
    repo = get_repo(cfg)
    ok = True

    # 1. gh installed?
    if github.gh_available():
        console.print("[green]OK[/green]  gh CLI found")
    else:
        console.print("[red]FAIL[/red]  gh CLI not found – install from https://cli.github.com/")
        ok = False

    # 2. gh authenticated?
    if ok and github.check_gh_auth():
        console.print("[green]OK[/green]  gh authenticated")
    elif ok:
        console.print("[red]FAIL[/red]  gh not authenticated – run: gh auth login")
        ok = False

    # 3. Can reach the repo?
    if ok:
        result = github._run_gh(
            ["repo", "view", repo, "--json", "name"], check=False,
        )
        if result.returncode == 0:
            console.print(f"[green]OK[/green]  Repository {repo} accessible")
        else:
            console.print(f"[red]FAIL[/red]  Cannot access {repo} – do you have push rights?")
            ok = False

    # 4. Can list workflows?
    if ok:
        result = github._run_gh(
            ["workflow", "list", "--repo", repo, "--limit", "3",
             "--json", "name,state"], check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            workflows = json.loads(result.stdout)
            for wf in workflows:
                state = wf.get("state", "?")
                style = "green" if state == "active" else "yellow"
                console.print(f"  [{style}]{state}[/{style}]  {wf['name']}")
        else:
            console.print("[yellow]WARN[/yellow]  Could not list workflows")

    if ok:
        console.print("\n[green bold]All checks passed.[/green bold] You're ready to use skuld.")
    else:
        console.print("\n[red bold]Some checks failed.[/red bold] Fix the issues above.")
        sys.exit(1)


# ─── skuld setup ───────────────────────────────────────────────────────

_PROVISION_SCRIPT = Path(__file__).resolve().parents[2] / "provision-server.sh"
_ENVIRONMENTS_YAML = Path(__file__).resolve().parents[2] / "environments.yaml"


def _derive_auth_domain(domain: str) -> str:
    return f"auth.{domain}"


def _ssh_cmd(ip: str, key: str, user: str) -> list:
    return ["ssh", "-i", key, "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=15", f"{user}@{ip}"]


@main.command()
@click.option("--dry-run", is_flag=True, help="Zeige was gemacht würde, ohne auszuführen")
def setup(dry_run: bool):
    """Interaktiver Wizard: neuen Server einrichten, DB befüllen, environments.yaml updaten.

    Fuehrt durch: IP/Rolle/Domain abfragen, Server haerten, DB befuellen, Config schreiben.
    """
    console.rule("[bold cyan]SKULD Setup Wizard[/bold cyan]")
    if dry_run:
        console.print("[yellow]DRY-RUN — es wird nichts ausgeführt.[/yellow]\n")

    # ── Phase 0: Verbindungsdaten ──────────────────────────────────────
    console.print("[bold]Phase 1 — Server[/bold]")
    ip = click.prompt("  Server IP")
    ssh_user = click.prompt("  SSH-User", default="root")
    default_key = str(Path.home() / ".ssh" / "id_ed25519_ionos")
    if not Path(default_key).exists():
        default_key = str(Path.home() / ".ssh" / "id_ed25519")
    ssh_key = click.prompt("  SSH-Key (Pfad)", default=default_key)

    if not Path(ssh_key).exists():
        console.print(f"[red]Key nicht gefunden: {ssh_key}[/red]")
        sys.exit(1)

    # Verbindung testen
    if not dry_run:
        console.print(f"\n  Teste Verbindung zu {ip} ...")
        test = subprocess.run(
            _ssh_cmd(ip, ssh_key, ssh_user) + ["echo OK"],
            capture_output=True, text=True
        )
        if test.returncode != 0 or "OK" not in test.stdout:
            console.print(f"[red]SSH-Verbindung fehlgeschlagen:[/red] {test.stderr.strip()}")
            console.print("  Tipp: Phase 0 (Key in Web-Console hinterlegen) abgeschlossen?")
            sys.exit(1)
        console.print("  [green]Verbindung OK[/green]")

    # ── Phase 1: Umgebungs-Details ─────────────────────────────────────
    console.print("\n[bold]Phase 2 — Umgebung[/bold]")
    env_name = click.prompt("  Umgebungs-Name (z.B. prod2, test1)")
    role = click.prompt("  Rolle", type=click.Choice(["prod", "test"]), default="test")

    console.print("\n[bold]Phase 3 — Domain[/bold]")
    domain = click.prompt("  Web-Domain (z.B. app.<deine-domain>.com)")
    proposed_auth = _derive_auth_domain(domain)
    auth_domain = click.prompt("  Auth-Domain", default=proposed_auth)

    # ── Phase 2: Runner Token ──────────────────────────────────────────
    console.print("\n[bold]Phase 4 — GitHub Runner Token[/bold]")
    console.print("  Token holen mit:")
    console.print("  [dim]gh api repos/Wuuzzaa/Skuld/actions/runners/registration-token --jq .token[/dim]")
    runner_token = click.prompt("  Runner Token (leer = Runner überspringen)", default="")
    install_runner = bool(runner_token)

    # ── Phase 3: SSH-Keys für deploy-User ─────────────────────────────
    authorized_keys = ""
    conf_path = _PROVISION_SCRIPT.parent / "provision-server.conf"
    if conf_path.exists():
        m = re.search(r'SSH_AUTHORIZED_KEYS="\n(.*?)\n"', conf_path.read_text(), flags=re.S)
        if m:
            authorized_keys = m.group(1).strip()

    # ── Phase 4: Härtung ──────────────────────────────────────────────
    console.print("\n[bold]Phase 5 — Server härten[/bold]")
    env_vars = f"ROLE={role} RUNNER_LABELS=skuld-{role} INSTALL_RUNNER={'true' if install_runner else 'false'}"
    if runner_token:
        env_vars += f" RUNNER_TOKEN={shlex.quote(runner_token)}"
    if authorized_keys:
        # Übergabe als Env-Var ist komplex bei Newlines — schreibe temporäre Datei
        env_vars += " INSTALL_EXTRA_KEYS=false"  # Skript liest conf direkt wenn vorhanden

    provision_cmd = (
        f"ssh -i {shlex.quote(ssh_key)} -o StrictHostKeyChecking=accept-new "
        f"{ssh_user}@{ip} {shlex.quote(env_vars + ' bash -s')} "
        f"< {shlex.quote(str(_PROVISION_SCRIPT))}"
    )
    console.print(f"  Befehl: [dim]{provision_cmd}[/dim]")

    if not dry_run:
        if not _PROVISION_SCRIPT.exists():
            console.print(f"[red]provision-server.sh nicht gefunden: {_PROVISION_SCRIPT}[/red]")
            sys.exit(1)
        result = subprocess.run(provision_cmd, shell=True)
        if result.returncode != 0:
            console.print("[red]Härtung fehlgeschlagen. Abbruch.[/red]")
            sys.exit(result.returncode)
        console.print("[green]Härtung abgeschlossen.[/green]")
    else:
        console.print("[dim]DRY-RUN: provision-server.sh würde ausgeführt.[/dim]")

    # ── Phase 5: DB-Befüllung ──────────────────────────────────────────
    console.print("\n[bold]Phase 6 — Datenbank[/bold]")
    db_choice = click.prompt(
        "  DB-Befüllung",
        type=click.Choice(["empty", "dump"]),
        default="empty",
    )

    if db_choice == "dump":
        dump_path = Path(click.prompt("  Pfad zur lokalen pg_dump-Datei")).expanduser()
        if not dry_run and not dump_path.exists():
            console.print(f"[red]Datei nicht gefunden: {dump_path}[/red]")
            sys.exit(1)

        confirm_str = f"restore-to-{env_name}"
        console.print(f"\n  [yellow]Achtung:[/yellow] DB wird auf {ip} eingespielt (nur Ziel-Server, nie Prod).")
        typed = click.prompt(f'  Bestätigung — tippe "{confirm_str}"')
        if typed.strip() != confirm_str:
            console.print("[yellow]Abgebrochen.[/yellow]")
            sys.exit(0)

        remote_dump = f"/tmp/skuld_restore_{env_name}.sql.gz"
        scp_cmd = (
            f"scp -i {shlex.quote(ssh_key)} "
            f"{shlex.quote(str(dump_path))} {ssh_user}@{ip}:{remote_dump}"
        )
        restore_cmd = (
            f"ssh -i {shlex.quote(ssh_key)} {ssh_user}@{ip} "
            f"'gunzip -c {remote_dump} | docker exec -i skuld_db psql -U skuld skuld && rm {remote_dump}'"
        )

        if not dry_run:
            console.print("  Kopiere Dump ...")
            subprocess.run(scp_cmd, shell=True, check=True)
            console.print("  Spiele ein ...")
            subprocess.run(restore_cmd, shell=True, check=True)
            console.print("[green]DB-Restore abgeschlossen.[/green]")
        else:
            console.print(f"[dim]DRY-RUN: scp {dump_path} → {ip}, dann restore[/dim]")

    # ── Phase 6: environments.yaml updaten ────────────────────────────
    console.print("\n[bold]Phase 7 — environments.yaml[/bold]")
    new_entry = (
        f"\n{env_name}:\n"
        f"  host: {ip}\n"
        f"  role: {role}\n"
        f"  domain: {domain}\n"
        f"  auth_domain: {auth_domain}\n"
        f"  runner_label: skuld-{role}\n"
        f"  default_branch: master\n"
        f"  compose_file: docker-compose.yml\n"
    )
    console.print(new_entry)

    if not dry_run:
        with open(_ENVIRONMENTS_YAML, "a") as f:
            f.write(new_entry)
        console.print(f"[green]Eintrag '{env_name}' in environments.yaml geschrieben.[/green]")

    # ── Abschluss ──────────────────────────────────────────────────────
    console.rule("[green]Setup abgeschlossen[/green]")
    console.print(f"\n[bold]Nächste Schritte:[/bold]")
    console.print(f"  1. DNS: {domain} → {ip} zeigen lassen (Cloudflare)")
    console.print(f"  2. Deploy starten:  skuld deploy {env_name}")
    console.print()


# ─── skuld watch ───────────────────────────────────────────────────────

@main.command()
@click.argument("workflow", default="deploy.yml")
def watch(workflow: str):
    """Watch the latest run of a workflow.

    Example: skuld watch deploy.yml
    """
    _ensure_gh()
    cfg = load_config()
    repo = get_repo(cfg)

    run = github.get_latest_run(repo, workflow, wait_appear=0)
    if not run:
        console.print("[yellow]No recent run found.[/yellow]")
        return

    console.print(f"Watching run {run['databaseId']} ({run.get('url', '')}) ...")
    success = github.watch_run(repo, run["databaseId"])
    if success:
        console.print("[green]Done.[/green]")
    else:
        console.print("[red]Run failed.[/red]")
        sys.exit(1)
