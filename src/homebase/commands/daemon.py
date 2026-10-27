from __future__ import annotations

import os
import signal
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import IO

from ..cache.api import (
    cache_full_scan_ts,
    cache_last_refresh_ts,
    cache_load_rows,
    cache_store_rows_merged,
)
from ..cache.daemon_status import (
    DaemonStatus,
    clear_daemon_status,
    daemon_lock_path,
    read_daemon_status,
    write_daemon_status,
)
from ..cache.owner import (
    read_cache_owner,
    release_cache_owner,
    take_cache_refresh_request,
    try_acquire_cache_owner,
    try_flock,
)
from ..core.constants import (
    ARCHIVE_DIR_NAME,
    CACHE_MAX_AGE_S,
    DAEMON_SIGNATURE_CHECK_S,
    DAEMON_STATUS_LOG_S,
    DAEMON_TICK_S,
    PACKED_ARCHIVE_SUFFIX,
    UI_TICK_WORKTREE_HEALTH_S,
)
from ..core.models import ProjectRow
from ..core.utils import CACHE_REFRESH_ERRORS
from ..core.version import get_version
from ..workspace.health_scan import scan_worktree_health
from ..workspace.rows import collect_workspace_rows
from ..workspace.signature import workspace_quick_signature
from .raycast_snapshot import SNAPSHOT_ERRORS
from .raycast_snapshot import refresh_snapshot as refresh_raycast_snapshot

# --once waits this long for a TUI to hand over the cache owner lock.
ONCE_OWNER_WAIT_S = 10.0
# Log lines kept in memory for the status screen; the last few also go into
# daemon.json for a second `b daemon` that only views this one.
DAEMON_LOG_LINES = 200
DAEMON_STATUS_LOG_LINES = 30


@dataclass
class DaemonState:
    base_dir: Path
    started_ts: float
    version: str
    size_cache: dict[Path, tuple[int, int]] = field(default_factory=dict)
    signature: str = ""
    signature_due_at: float = 0.0
    status_log_due_at: float = 0.0
    health_due_at: float = 0.0
    health_issues: int = -1
    last_refresh_s: float = 0.0
    last_scan_started_at: float = 0.0
    refreshes: int = 0
    state: str = "starting"
    owner: IO[str] | None = None
    waiting_logged: bool = False
    # What the loop does right now ("" when idle) and since when.
    activity: str = ""
    activity_since: float = 0.0
    last_reason: str = ""
    active_rows: int = -1
    archived_rows: int = -1
    health_ts: float = 0.0
    health_took_s: float = 0.0
    echo: bool = True
    log_count: int = 0
    # Content key of raycast.json on disk; last snapshot error (logged once).
    raycast_stamp: str | None = None
    raycast_error: str = ""
    lines: deque[str] = field(default_factory=lambda: deque(maxlen=DAEMON_LOG_LINES))

    def log(self, message: str) -> None:
        line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
        self.lines.append(line)
        self.log_count += 1
        if self.echo:
            print(line, flush=True)

    def begin(self, activity: str) -> None:
        self.activity = activity
        self.activity_since = time.time()

    def end(self) -> None:
        self.activity = ""


def log(message: str) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    print(f"{stamp} {message}", flush=True)


def _signature(base_dir: Path) -> str:
    return workspace_quick_signature(
        base_dir=base_dir,
        archive_dir_name=ARCHIVE_DIR_NAME,
        packed_archive_suffix=PACKED_ARCHIVE_SUFFIX,
    )


def _size_key(path: Path) -> Path:
    try:
        return path.resolve()
    except (OSError, RuntimeError, ValueError):
        return path


def _size_cache_from_rows(rows: list[ProjectRow]) -> dict[Path, tuple[int, int]]:
    return {
        _size_key(row.path): (int(row.size_bytes), int(row.size_refresh_count))
        for row in rows
    }


def ensure_owner(st: DaemonState) -> bool:
    """Take the cache owner lock. A TUI holding it lets go once it sees
    this daemon's heartbeat, so this succeeds within a poll tick or two."""
    if st.owner is not None:
        return True
    st.owner = try_acquire_cache_owner(st.base_dir, role="daemon")
    if st.owner is None:
        st.state = "waiting"
        if not st.waiting_logged:
            st.waiting_logged = True
            st.log(f"waiting for cache owner ({read_cache_owner(st.base_dir) or '?'})")
        return False
    st.state = "idle"
    st.log("cache owner")
    return True


def refresh_reason(st: DaemonState, now: float) -> str | None:
    """Why the cache needs a full rescan now, or None."""
    request = take_cache_refresh_request(st.base_dir)
    # A request older than the last scan start is already covered by it.
    if request is not None and request[1] >= st.last_scan_started_at:
        return f"requested: {request[0]}"
    # Single-row writes touch last_refresh_ts, so age is measured from the
    # last full rescan only.
    last_scan = cache_full_scan_ts(st.base_dir)
    if last_scan <= 0:
        return "no full scan yet"
    if now - last_scan > CACHE_MAX_AGE_S:
        return "max age"
    if now < st.signature_due_at:
        return None
    st.signature_due_at = now + DAEMON_SIGNATURE_CHECK_S
    sig = _signature(st.base_dir)
    changed = bool(st.signature) and sig != st.signature
    st.signature = sig
    return "workspace changed" if changed else None


def refresh(st: DaemonState, reason: str) -> bool:
    """Full rescan (git status included) + store. Rows another process
    wrote during the scan are newer than the scan and are kept."""
    st.last_scan_started_at = time.time()
    scan_started_ts = int(st.last_scan_started_at)
    t0 = time.monotonic()
    st.state = "refreshing"
    st.last_reason = reason
    st.begin(f"full scan ({reason})")
    try:
        active, archived = collect_workspace_rows(
            st.base_dir,
            include_git_dirty=True,
            size_cache=st.size_cache,
        )
        cache_store_rows_merged(
            st.base_dir, active, archived, scan_started_ts=scan_started_ts
        )
    except CACHE_REFRESH_ERRORS as exc:
        st.state = "error"
        st.log(f"refresh failed reason={reason!r} {exc.__class__.__name__}: {exc}")
        return False
    finally:
        st.end()
    took = time.monotonic() - t0
    st.last_refresh_s = took
    st.state = "idle"
    st.refreshes += 1
    st.active_rows = len(active)
    st.archived_rows = len(archived)
    st.size_cache = _size_cache_from_rows(active + archived)
    st.signature = _signature(st.base_dir)
    st.log(
        f"refresh ok reason={reason!r} active={len(active)} archived={len(archived)} took={took:.1f}s"
    )
    return True


def sweep_worktree_health(st: DaemonState, now: float) -> None:
    if now < st.health_due_at:
        return
    st.health_due_at = now + UI_TICK_WORKTREE_HEALTH_S
    st.begin("worktree health sweep")
    t0 = time.monotonic()
    try:
        issues, _remaining, _visited, _ts = scan_worktree_health(
            st.base_dir, [], budget_s=None
        )
    except (OSError, ValueError) as exc:
        st.log(f"worktree health failed {exc.__class__.__name__}: {exc}")
        return
    finally:
        st.end()
    st.health_ts = time.time()
    st.health_took_s = time.monotonic() - t0
    if len(issues) != st.health_issues:
        st.health_issues = len(issues)
        st.log(f"worktree health issues={len(issues)}")


def update_raycast_snapshot(st: DaemonState) -> None:
    """Keep raycast.json current; cheap when nothing changed."""
    try:
        stamp = refresh_raycast_snapshot(st.base_dir, st.raycast_stamp)
    except SNAPSHOT_ERRORS as exc:
        error = f"{exc.__class__.__name__}: {exc}"
        if error != st.raycast_error:
            st.raycast_error = error
            st.log(f"raycast snapshot failed {error}")
        return
    st.raycast_error = ""
    if stamp != st.raycast_stamp:
        if st.raycast_stamp is None:
            st.log("raycast snapshot written")
        st.raycast_stamp = stamp


def status_of(st: DaemonState, now: float | None = None) -> DaemonStatus:
    return DaemonStatus(
        pid=os.getpid(),
        version=st.version,
        started_ts=st.started_ts,
        heartbeat_ts=time.time() if now is None else now,
        last_refresh_ts=cache_last_refresh_ts(st.base_dir),
        last_refresh_s=st.last_refresh_s,
        refreshes=st.refreshes,
        state=st.state,
        role="owner" if st.owner is not None else "waiting",
        activity=st.activity,
        activity_since=st.activity_since,
        last_reason=st.last_reason,
        active_rows=st.active_rows,
        archived_rows=st.archived_rows,
        health_issues=st.health_issues,
        health_ts=st.health_ts,
        health_took_s=st.health_took_s,
        recent=tuple(list(st.lines)[-DAEMON_STATUS_LOG_LINES:]),
    )


def heartbeat(st: DaemonState) -> None:
    write_daemon_status(st.base_dir, status_of(st))


def _log_status(st: DaemonState, now: float) -> None:
    if now < st.status_log_due_at:
        return
    st.status_log_due_at = now + DAEMON_STATUS_LOG_S
    age = int(now - cache_full_scan_ts(st.base_dir))
    st.log(
        f"status {st.state} scan_age={age}s refreshes={st.refreshes} "
        f"last_took={st.last_refresh_s:.1f}s"
    )


def _heartbeat_loop(st: DaemonState, stop: threading.Event) -> None:
    # Own thread: a full rescan blocks the main loop for many seconds and
    # clients must not take that as a dead daemon.
    while not stop.wait(DAEMON_TICK_S):
        try:
            heartbeat(st)
        except OSError as exc:
            st.log(f"heartbeat failed {exc.__class__.__name__}: {exc}")


def _run_once(st: DaemonState, stop: threading.Event) -> int:
    deadline = time.monotonic() + ONCE_OWNER_WAIT_S
    while not ensure_owner(st):
        if stop.is_set() or time.monotonic() >= deadline:
            st.log("gave up waiting for cache owner")
            return 1
        stop.wait(0.5)
    ok = refresh(st, "once")
    sweep_worktree_health(st, time.time())
    update_raycast_snapshot(st)
    return 0 if ok else 1


def _run_loop(st: DaemonState, stop: threading.Event) -> None:
    while not stop.is_set():
        if ensure_owner(st):
            now = time.time()
            reason = refresh_reason(st, now)
            if reason is not None:
                refresh(st, reason)
            sweep_worktree_health(st, time.time())
        update_raycast_snapshot(st)
        _log_status(st, time.time())
        stop.wait(DAEMON_TICK_S)


def acquire_daemon_lock(base_dir: Path) -> IO[str] | None:
    """One daemon per base; None (and a log line) when one already runs."""
    lock = try_flock(daemon_lock_path(base_dir), str(os.getpid()))
    if lock is None:
        other = read_daemon_status(base_dir)
        pid = other.pid if other is not None else "?"
        log(f"already running pid={pid} base={base_dir}")
    return lock


def new_daemon_state(base_dir: Path, *, echo: bool = True) -> DaemonState:
    st = DaemonState(
        base_dir=base_dir, started_ts=time.time(), version=get_version(), echo=echo
    )
    active, archived, _ts = cache_load_rows(base_dir)
    st.active_rows = len(active)
    st.archived_rows = len(archived)
    st.size_cache = _size_cache_from_rows(active + archived)
    st.signature = _signature(base_dir)
    st.log(
        f"start pid={os.getpid()} version={st.version} base={base_dir} "
        f"cached_rows={len(active) + len(archived)}"
    )
    return st


def run_daemon(st: DaemonState, stop: threading.Event, *, once: bool = False) -> int:
    """Heartbeat thread + main loop until ``stop``; releases the owner lock
    and status file on the way out. Caller holds the daemon lock."""
    # Heartbeat first: it is what makes a TUI release the owner lock.
    heartbeat(st)
    beat = threading.Thread(target=_heartbeat_loop, args=(st, stop), daemon=True)
    beat.start()
    rc = 0
    try:
        if once:
            rc = _run_once(st, stop)
        else:
            _run_loop(st, stop)
    finally:
        stop.set()
        beat.join(timeout=DAEMON_TICK_S * 2)
        release_cache_owner(st.owner)
        st.owner = None
        st.state = "stopped"
        clear_daemon_status(st.base_dir, os.getpid())
        st.log("stop")
    return rc


def cmd_daemon(base_dir: Path, *, once: bool = False) -> int:
    lock = acquire_daemon_lock(base_dir)
    if lock is None:
        return 1
    stop = threading.Event()
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, lambda *_args: stop.set())
    try:
        return run_daemon(new_daemon_state(base_dir), stop, once=once)
    finally:
        lock.close()
