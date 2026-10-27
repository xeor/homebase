from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from ..core.constants import (
    DAEMON_LOCK_FILE_NAME,
    DAEMON_STALE_S,
    DAEMON_STATUS_FILE_NAME,
)
from .owner import pid_alive, runtime_dir


@dataclass(frozen=True)
class DaemonStatus:
    pid: int
    version: str
    started_ts: float
    heartbeat_ts: float
    last_refresh_ts: int
    last_refresh_s: float
    refreshes: int
    state: str
    # Extra detail for the status screen; older files lack it.
    role: str = ""
    activity: str = ""
    activity_since: float = 0.0
    last_reason: str = ""
    active_rows: int = -1
    archived_rows: int = -1
    health_issues: int = -1
    health_ts: float = 0.0
    health_took_s: float = 0.0
    recent: tuple[str, ...] = ()


def daemon_status_path(base_dir: Path) -> Path:
    return runtime_dir(base_dir) / DAEMON_STATUS_FILE_NAME


def daemon_lock_path(base_dir: Path) -> Path:
    return runtime_dir(base_dir) / DAEMON_LOCK_FILE_NAME


def write_daemon_status(base_dir: Path, status: DaemonStatus) -> None:
    path = daemon_status_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{status.pid}.tmp")
    tmp.write_text(json.dumps(asdict(status), sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def read_daemon_status(base_dir: Path) -> DaemonStatus | None:
    try:
        raw = json.loads(daemon_status_path(base_dir).read_text(encoding="utf-8"))
        return DaemonStatus(
            pid=int(raw["pid"]),
            version=str(raw["version"]),
            started_ts=float(raw["started_ts"]),
            heartbeat_ts=float(raw["heartbeat_ts"]),
            last_refresh_ts=int(raw["last_refresh_ts"]),
            last_refresh_s=float(raw["last_refresh_s"]),
            refreshes=int(raw["refreshes"]),
            state=str(raw["state"]),
            role=str(raw.get("role", "")),
            activity=str(raw.get("activity", "")),
            activity_since=float(raw.get("activity_since", 0.0)),
            last_reason=str(raw.get("last_reason", "")),
            active_rows=int(raw.get("active_rows", -1)),
            archived_rows=int(raw.get("archived_rows", -1)),
            health_issues=int(raw.get("health_issues", -1)),
            health_ts=float(raw.get("health_ts", 0.0)),
            health_took_s=float(raw.get("health_took_s", 0.0)),
            recent=tuple(str(line) for line in raw.get("recent", ())),
        )
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def clear_daemon_status(base_dir: Path, pid: int) -> None:
    status = read_daemon_status(base_dir)
    if status is not None and status.pid != pid:
        return
    try:
        daemon_status_path(base_dir).unlink()
    except FileNotFoundError:
        pass


def daemon_status_alive(status: DaemonStatus | None, now: float | None = None) -> bool:
    if status is None:
        return False
    current = time.time() if now is None else now
    if current - status.heartbeat_ts > DAEMON_STALE_S:
        return False
    return pid_alive(status.pid)


def daemon_alive(base_dir: Path, now: float | None = None) -> bool:
    return daemon_status_alive(read_daemon_status(base_dir), now)
