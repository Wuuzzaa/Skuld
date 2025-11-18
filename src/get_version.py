import subprocess
from datetime import datetime

def get_version(cwd):
    """Get detailed version with commit count, hash, date and time."""
    try:
        count_result = subprocess.run(
            ['git', 'rev-list', '--count', 'HEAD'],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5
        )

        hash_result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5
        )

        date_result = subprocess.run(
            ['git', 'log', '-1', '--format=%ci'],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5
        )

        if all(r.returncode == 0 for r in [count_result, hash_result, date_result]):
            count = count_result.stdout.strip()
            hash_short = hash_result.stdout.strip()
            date_str = date_result.stdout.strip()

            # Parse datetime including time
            commit_datetime = datetime.fromisoformat(date_str.rsplit(' ', 1)[0])
            date_formatted = commit_datetime.strftime('%Y-%m-%d %H:%M')

            return f"{count}-{hash_short} ({date_formatted})"
    except Exception:
        pass

    return "(unknown)"