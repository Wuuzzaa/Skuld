import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

LOGS_BASE = Path(__file__).resolve().parent.parent / "logs"
RETENTION_DAYS = 14


def cleanup_old_logs(retention_days: int = RETENTION_DAYS) -> None:
    """Delete log files older than retention_days. Removes empty date directories."""
    if not LOGS_BASE.exists():
        return

    cutoff = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    deleted_files = 0
    deleted_dirs = 0

    for component_dir in LOGS_BASE.iterdir():
        if not component_dir.is_dir():
            continue
        for date_dir in sorted(component_dir.iterdir()):
            if not date_dir.is_dir():
                continue
            if date_dir.name >= cutoff:
                continue
            for log_file in date_dir.iterdir():
                try:
                    log_file.unlink()
                    deleted_files += 1
                except Exception as e:
                    logger.warning(f"Could not delete {log_file}: {e}")
            try:
                date_dir.rmdir()
                deleted_dirs += 1
            except OSError:
                pass  # not empty, skip

    if deleted_files:
        logger.info(f"Log cleanup: removed {deleted_files} files in {deleted_dirs} dirs older than {retention_days} days")
    else:
        logger.info("Log cleanup: nothing to remove")
