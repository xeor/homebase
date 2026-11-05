"""Single writer for background cache work.

One process per base holds the owner lock: `b daemon` while it runs, else
the first TUI that gets it. Only the owner runs full rescans, reconcile and
the git / worktree-health sweeps. Other processes read the cache, write rows
for the user's own actions, and ask the owner for a rescan through the
request file."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
from typing import IO

from ..core.constants import (
    CACHE_OWNER_LOCK_FILE_NAME,
    CACHE_REFRESH_REQUEST_FILE_NAME,
    HOMEBASE_DIR_NAME,
    RUNTIME_DIR_NAME,
)


def runtime_dir(base_dir: Path) -> Path:
    return base_dir / HOMEBASE_DIR_NAME / RUNTIME_DIR_NAME


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def try_flock(path: Path, payload: str) -> IO[str] | None:
    """Non-blocking exclusive lock on ``path``; the handle holds it until
    closed (or the process exits). The file is only rewritten once locked,
    so a failed attempt never wipes the holder's payload."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    handle = os.fdopen(fd, "r+", encoding="utf-8")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(payload)
    handle.flush()
    return handle


def cache_owner_lock_path(base_dir: Path) -> Path:
    return runtime_dir(base_dir) / CACHE_OWNER_LOCK_FILE_NAME


def try_acquire_cache_owner(base_dir: Path, *, role: str) -> IO[str] | None:
    return try_flock(cache_owner_lock_path(base_dir), f"{os.getpid()} {role}")


def release_cache_owner(handle: IO[str] | None) -> None:
    if handle is None:
        return
    try:
        handle.close()
    except OSError:
        pass


def read_cache_owner(base_dir: Path) -> str:
    """'<pid> <role>' of the last owner, for log lines; '' when unknown."""
    try:
        return cache_owner_lock_path(base_dir).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def cache_refresh_request_path(base_dir: Path) -> Path:
    return runtime_dir(base_dir) / CACHE_REFRESH_REQUEST_FILE_NAME


def request_cache_refresh(base_dir: Path, reason: str) -> None:
    """Ask the cache owner for a full rescan on its next tick."""
    path = cache_refresh_request_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(reason, encoding="utf-8")


def peek_cache_refresh_request(base_dir: Path) -> str | None:
    """Reason of a pending rescan request, left in place."""
    try:
        return cache_refresh_request_path(base_dir).read_text(encoding="utf-8").strip() or "requested"
    except FileNotFoundError:
        return None
    except OSError:
        return None


def take_cache_refresh_request(base_dir: Path) -> tuple[str, float] | None:
    """Pop a pending rescan request: (reason, requested_at)."""
    path = cache_refresh_request_path(base_dir)
    try:
        requested_at = path.stat().st_mtime
        reason = path.read_text(encoding="utf-8").strip() or "requested"
        path.unlink()
    except FileNotFoundError:
        return None
    return reason, requested_at
