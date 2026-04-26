"""GitHub Actions helper – wraps `gh` CLI calls."""

import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from rich.console import Console

console = Console()


def gh_available() -> bool:
    """Return True if `gh` is on PATH."""
    return shutil.which("gh") is not None


def _run_gh(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a `gh` command and return the result."""
    cmd = ["gh"] + args
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, check=check,
        )
    except FileNotFoundError:
        console.print(
            "[red]Error:[/red] `gh` CLI not found. "
            "Install it from https://cli.github.com/ and run `gh auth login`."
        )
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]gh failed:[/red] {exc.stderr.strip()}")
        raise


def check_gh_auth() -> bool:
    """Return True if the user is authenticated with gh."""
    result = _run_gh(["auth", "status"], check=False)
    return result.returncode == 0


def trigger_workflow(
    repo: str,
    workflow: str,
    ref: str = "master",
    inputs: Optional[dict[str, str]] = None,
) -> bool:
    """Trigger a GitHub Actions workflow_dispatch and return True on success."""
    args = ["workflow", "run", workflow, "--repo", repo, "--ref", ref]
    for key, value in (inputs or {}).items():
        args += ["-f", f"{key}={value}"]

    result = _run_gh(args, check=False)
    if result.returncode != 0:
        console.print(f"[red]Failed to trigger workflow:[/red] {result.stderr.strip()}")
        return False
    return True


def get_latest_run(
    repo: str,
    workflow: str,
    wait_appear: float = 15.0,
    created_after: Optional[datetime] = None,
) -> Optional[dict]:
    """Get the most recent run for a workflow that was created after *created_after*.

    Polls for up to *wait_appear* seconds to give GitHub time to register
    the run after a workflow_dispatch trigger.
    """
    deadline = time.time() + wait_appear
    while True:
        result = _run_gh(
            ["run", "list", "--repo", repo, "--workflow", workflow,
             "--limit", "1", "--json", "databaseId,status,conclusion,headBranch,createdAt,url"],
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            runs = json.loads(result.stdout)
            if runs:
                run = runs[0]
                # Guard against picking up an older run that was already
                # present before we triggered.
                if created_after is not None:
                    run_created = run.get("createdAt", "")
                    try:
                        run_dt = datetime.fromisoformat(run_created.replace("Z", "+00:00"))
                        if run_dt < created_after:
                            # This run existed before our trigger – keep waiting.
                            if time.time() >= deadline:
                                return None
                            time.sleep(2)
                            continue
                    except (ValueError, TypeError):
                        pass  # Couldn't parse – fall through and return it.
                return run
        if time.time() >= deadline:
            return None
        time.sleep(2)


def watch_run(repo: str, run_id: int) -> bool:
    """Stream workflow run logs to the terminal and return True on success.

    Uses `gh run watch` with live output piped directly to the console so
    that the user sees progress in real time.
    """
    proc = subprocess.run(
        ["gh", "run", "watch", str(run_id), "--repo", repo, "--exit-status"],
        # Let stdout/stderr flow straight to the terminal.
        stdin=subprocess.DEVNULL,
    )
    return proc.returncode == 0
