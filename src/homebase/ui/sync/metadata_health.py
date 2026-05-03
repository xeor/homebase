from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable


def maybe_refresh_metadata_health(
    app: Any,
    *,
    base_meta_health: Callable[[Path], tuple[str, str]],
) -> None:
    if app.fast_exit_requested:
        return
    if app._critical_job_active():
        return
    if app.metadata_health_refresh_running:
        return
    now = time.time()
    if now < float(app.metadata_health_refresh_next_due_at):
        return
    if now - app.metadata_health_refresh_last_ts < app._metadata_health_min_interval_s():
        return

    rows = app._current_rows()
    if not rows:
        return
    ttl_s = app._metadata_health_ttl_s()
    batch_size = app._metadata_health_batch_size()
    scan_limit = max(batch_size * 5, batch_size)

    due_paths: list[Path] = []
    for row in rows[:scan_limit]:
        cached = app.metadata_health_cache.get(row.path)
        if cached is None or now >= float(cached[1]):
            due_paths.append(row.path)
            if len(due_paths) >= batch_size:
                break
    if not due_paths:
        app.metadata_health_refresh_next_due_at = now + app._metadata_health_interval_s()
        return

    app.metadata_health_refresh_running = True
    app.metadata_health_refresh_last_ts = now
    app.metadata_health_refresh_next_due_at = now + app._metadata_health_interval_s()

    def worker() -> None:
        updated: list[tuple[Path, str, float]] = []
        now_local = time.time()
        expires_at = now_local + ttl_s
        for path in due_paths:
            try:
                level, _msg = base_meta_health(path)
                updated.append((path, str(level).strip().lower(), expires_at))
            except (OSError, ValueError, TypeError):
                continue
        app.call_from_thread(app._on_metadata_health_refresh_done, updated)

    threading.Thread(target=worker, daemon=True).start()


def on_metadata_health_refresh_done(app: Any, updated: list[tuple[Path, str, float]]) -> None:
    app.metadata_health_refresh_running = False
    app.metadata_health_refresh_last_ts = time.time()
    for path, level, expires_at in updated:
        app.metadata_health_cache[path] = (level, float(expires_at))
