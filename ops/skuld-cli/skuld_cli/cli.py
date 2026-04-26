"""SKULD CLI – deploy and manage environments via GitHub Actions.

Every command triggers the corresponding GitHub Actions workflow so that
no developer needs direct SSH access or server credentials.  The only
prerequisite is an authenticated `gh` CLI (https://cli.github.com/).
"""

import json
import sys
from datetime import datetime, timezone

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
