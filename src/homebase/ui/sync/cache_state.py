from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from ...cache.api import cache_delete_paths, cache_load_rows, cache_upsert_rows
from ...core.models import ProjectRow


def touch_rows_cache(
    app: Any,
    *,
    base_dir: Path,
    rows: list[ProjectRow],
    removed: list[Path] | None = None,
) -> None:
    app.cache_refresh_epoch += 1
    if app.cache_worker_running:
        app.cache_refresh_pending = True
        app.cache_refresh_pending_force = True
        app.cache_refresh_pending_reason = "local mutation"
    try:
        if rows:
            now_ts = int(time.time())
            for row in rows:
                row.last_cached_ts = now_ts
                if row.last_reconciled_ts <= 0:
                    row.last_reconciled_ts = now_ts
            ts = cache_upsert_rows(base_dir, rows, touch_refresh_ts=True)
            app.cache_last_refresh_ts = max(app.cache_last_refresh_ts, ts)
        if removed:
            ts = cache_delete_paths(base_dir, removed, touch_refresh_ts=True)
            app.cache_last_refresh_ts = max(app.cache_last_refresh_ts, ts)
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        app._log_error_counted(
            "cache_partial_update",
            f"cache partial update failed ({exc.__class__.__name__}): {exc}",
        )


def reload_rows_from_cache(app: Any, *, base_dir: Path, cache_max_age_s: int) -> bool:
    active, archived, refreshed = cache_load_rows(base_dir, cache_max_age_s)
    if not active and not archived:
        return False
    app.active_rows = active
    app.archived_rows = archived
    app._invalidate_current_rows_cache()
    app._apply_dynamic_properties_all_rows()
    app._log_row_health_issues(app.active_rows + app.archived_rows)
    app.cache_last_refresh_ts = refreshed
    return True
