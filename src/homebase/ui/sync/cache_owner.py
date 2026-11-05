from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from textual.css.query import NoMatches

from ...cache.api import cache_full_scan_ts
from ...cache.daemon_status import daemon_alive
from ...cache.owner import (
    release_cache_owner,
    take_cache_refresh_request,
    try_acquire_cache_owner,
)
from ...core.constants import UI_TICK_CACHE_OWNER_POLL_S
from ...core.utils import WIDGET_API_ERRORS


def is_cache_owner(app: Any, *, base_dir: Path, now: float | None = None) -> bool:
    """True while this TUI holds the cache owner lock (see cache.owner).

    Re-evaluated at most once per poll tick: a live `b daemon` always wins
    and the TUI lets go; without one the TUI takes the lock when free."""
    current = time.time() if now is None else now
    handle = getattr(app, "cache_owner_handle", None)
    checked_at = float(getattr(app, "cache_owner_checked_at", 0.0))
    if checked_at > 0 and current - checked_at < UI_TICK_CACHE_OWNER_POLL_S:
        return handle is not None
    app.cache_owner_checked_at = current
    if daemon_alive(base_dir, current):
        if handle is not None:
            release_cache_owner(handle)
            app.cache_owner_handle = None
            app._worker_debug("cache owner: handed over to b daemon")
        return False
    if handle is None:
        handle = try_acquire_cache_owner(base_dir, role="tui")
        if handle is None:
            return False
        app.cache_owner_handle = handle
        app._worker_debug("cache owner: this b")
    return True


def poll_cache_owner(app: Any, *, base_dir: Path) -> None:
    """Owner: run rescans other processes asked for. Others: reload rows
    after each full rescan newer than the rows shown."""
    if app.fast_exit_requested:
        return
    if is_cache_owner(app, base_dir=base_dir):
        request = take_cache_refresh_request(base_dir)
        if request is not None:
            app._start_cache_refresh(f"requested: {request[0]}", force=True)
        return
    full_scan_ts = cache_full_scan_ts(base_dir)
    if full_scan_ts <= app.full_scan_seen_ts:
        return
    app.full_scan_seen_ts = full_scan_ts
    if not app._reload_rows_from_cache():
        return
    app._worker_debug(
        f"cache reloaded after owner rescan: active={len(app.active_rows)} archive={len(app.archived_rows)}"
    )
    try:
        app._refresh_table()
        app._restore_table_position()
        app._refresh_side()
    except (*WIDGET_API_ERRORS, NoMatches):
        pass
