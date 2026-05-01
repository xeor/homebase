from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Callable

from ...core.models import ProjectRow


def on_set_description(
    app: Any,
    value: str | None,
    *,
    save_base_description: Callable[[Path, str], None],
) -> None:
    if value is None:
        app._log("set description cancelled", "warn")
        app._refresh_side()
        return
    targets = list(app.pending_desc_targets)
    app.pending_desc_targets = []
    if not targets:
        targets = [r.path for r in app._target_rows()]
    app._busy_start("updating descriptions")
    try:
        for path in targets:
            app._busy_tick()
            save_base_description(path, value)
    finally:
        app._busy_stop()
    changed_rows: list[ProjectRow] = []
    for path in targets:
        hit = app._find_row(path)
        if hit is None:
            continue
        rows, idx = hit
        rows[idx].description = value
        rows[idx].stale = False
        rows[idx].cache_age_s = 0
        changed_rows.append(rows[idx])
    if changed_rows:
        app._touch_rows_cache(changed_rows)
        app._start_cache_refresh("description update", force=False)
    else:
        app._refresh_data()
    app._refresh_table()
    app._log(f"description updated on {len(targets)} item(s)", "info")
    app._refresh_side()


def on_rename_item(
    app: Any,
    value: str | None,
    *,
    project_row: Callable[..., ProjectRow],
) -> None:
    current = app.pending_rename_target
    app.pending_rename_target = None
    if current is None:
        return
    if value is None:
        app._log("rename cancelled", "warn")
        app._refresh_side()
        return
    new_name = value.strip()
    if not new_name:
        app._log("rename failed: empty name", "error")
        app._refresh_side()
        return
    if "/" in new_name or "\\" in new_name:
        app._log("rename failed: name must not contain path separators", "error")
        app._refresh_side()
        return

    hit = app._find_row(current)
    if hit is None:
        app._log("rename failed: source row not found", "error")
        app._refresh_side()
        return
    rows, idx = hit
    source_row = rows[idx]

    target = current.parent / new_name
    if target == current:
        app._log("rename skipped: unchanged", "warn")
        app._refresh_side()
        return
    if target.exists():
        app._log(f"rename failed: target exists ({target.name})", "error")
        app._refresh_side()
        return

    try:
        current.rename(target)
    except (OSError, ValueError) as exc:
        app._log(f"rename failed: {exc}", "error")
        app._refresh_side()
        return

    try:
        updated = project_row(
            target,
            archived=source_row.archived,
            restore_target=source_row.restore_target,
            archived_ts=source_row.archived_ts,
        )
    except (
        OSError,
        ValueError,
        TypeError,
        subprocess.SubprocessError,
        sqlite3.Error,
    ) as exc:
        app._log(f"rename warning: row refresh failed ({exc})", "warn")
        app._refresh_data()
        app._refresh_table()
        app._refresh_side()
        return

    app._remove_paths_local([current])
    app._upsert_row_local(updated)
    app.multi_selected = {(target if app._same_path(p, current) else p) for p in app.multi_selected}
    app.selected_path = target
    app._touch_rows_cache([updated], removed=[current])
    app._start_cache_refresh("rename item", force=False)
    if not updated.archived:
        app._request_tag_sync("rename item")
    app._refresh_table()
    app._log(f"renamed: {current.name} -> {target.name}", "info")
    app._refresh_side()
