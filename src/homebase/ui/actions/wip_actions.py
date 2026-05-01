from __future__ import annotations

import json
from typing import Any, Callable

import yaml


def action_toggle_wip(
    app: Any,
    *,
    mode_active: str,
    save_base_wip: Callable[[object, bool], None],
) -> None:
    row = app._selected_row()
    if not row:
        return
    was_wip = row.wip
    if row.archived:
        app._log("wip toggle ignored in archive view", "warn")
        app._refresh_side()
        return
    if not row.wip and len(app._wip_rows_sorted()) >= 9:
        app._log("wip limit reached (max 9)", "warn")
        app._refresh_side()
        return
    try:
        save_base_wip(row.path, not row.wip)
    except (
        OSError,
        yaml.YAMLError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as exc:
        app._show_runtime_error("toggle WIP", exc)
        app._refresh_side()
        return
    hit = app._find_row(row.path)
    if hit is not None:
        rows, idx = hit
        rows[idx].wip = not was_wip
        rows[idx].stale = False
        rows[idx].cache_age_s = 0
        app._invalidate_current_rows_cache()
        app._touch_rows_cache([rows[idx]])
    else:
        app._refresh_data()

    if app.view_mode == mode_active and app._table_pin_wip_top_enabled():
        app._restore_apply_scroll[app.view_mode] = True
        app._view_row_offset[app.view_mode] = 0

    app._refresh_table()
    app._log(f"wip {'enabled' if not was_wip else 'disabled'}: {row.name}", "info")
    app._refresh_side()


def action_refresh_details(app: Any) -> None:
    app._refresh_selected_details(log_success=True)
    app._refresh_side()


def action_open_wip_index(app: Any, idx: int) -> None:
    app._open_wip_index(idx)
