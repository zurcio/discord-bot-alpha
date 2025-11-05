import os
import time
import gzip
from datetime import datetime, timezone, timedelta


def _ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)


def _ts() -> str:
    # UTC timestamp for filenames
    return datetime.utcnow().strftime("%Y%m%d-%H%M%S")


def backup_file(src_path: str, backup_dir: str, prefix: str = "players") -> str | None:
    """
    Create a gzip'd timestamped backup copy of src_path in backup_dir.
    Returns the backup file path or None if source doesn't exist.
    """
    if not os.path.exists(src_path):
        return None
    _ensure_dir(backup_dir)
    name = f"{prefix}-{_ts()}.json.gz"
    dst = os.path.join(backup_dir, name)
    with open(src_path, "rb") as fsrc, gzip.open(dst, "wb", compresslevel=6) as fdst:
        fdst.write(fsrc.read())
    return dst


def rotate_backups(backup_dir: str, prefix: str = "players", keep: int = 14) -> int:
    """
    Keep only the newest `keep` backup files matching prefix; delete older ones.
    Returns number of files deleted.
    """
    if keep <= 0 or not os.path.isdir(backup_dir):
        return 0
    files = [
        os.path.join(backup_dir, f)
        for f in os.listdir(backup_dir)
        if f.startswith(prefix + "-") and f.endswith(".json.gz")
    ]
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    to_delete = files[keep:]
    deleted = 0
    for p in to_delete:
        try:
            os.remove(p)
            deleted += 1
        except Exception:
            pass
    return deleted


def seconds_until(hour_utc: int = 4, minute: int = 0) -> float:
    """Seconds until next occurrence of hour:minute UTC from now."""
    now = datetime.now(timezone.utc)
    target = now.replace(hour=hour_utc, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return (target - now).total_seconds()


async def run_daily_players_backup(players_file: str, backup_dir: str, keep: int = 14, hour_utc: int = 4, logger=print):
    """
    Background task: wait until the next hour:minute UTC, then every ~24h
    back up players_file into backup_dir and rotate old backups.
    """
    try:
        # Initial delay to scheduled time
        delay = max(1.0, seconds_until(hour_utc, 0))
        logger(f"[backup] First backup in ~{int(delay)}s (UTC {hour_utc:02d}:00)")
        await __import__("asyncio").sleep(delay)
        while True:
            path = backup_file(players_file, backup_dir, prefix="players")
            if path:
                logger(f"[backup] Wrote {path}")
            else:
                logger(f"[backup] Skipped: source not found {players_file}")
            n = rotate_backups(backup_dir, prefix="players", keep=keep)
            if n:
                logger(f"[backup] Rotated {n} old backups (kept {keep})")
            # Sleep ~24h until next run time
            await __import__("asyncio").sleep(24 * 3600)
    except Exception as e:
        logger(f"[backup] Task error: {e}")
