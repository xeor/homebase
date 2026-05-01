from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from textual.widgets import DataTable

from ...core.models import ProjectRow
from ...core.utils import WIDGET_API_ERRORS


def action_pick_sort(
    app: Any,
    *,
    sort_modes_for_view: Callable[[str], list[tuple[str, str]]],
    single_choice_screen: Any,
) -> None:
    options = sort_modes_for_view(app.view_mode)
    app.push_screen(single_choice_screen("Sort picker", options), app._on_pick_sort)


def on_pick_sort(
    app: Any,
    value: str | None,
    *,
    sort_modes_for_view: Callable[[str], list[tuple[str, str]]],
) -> None:
    allowed = {sid for sid, _label in sort_modes_for_view(app.view_mode)}
    if value in allowed:
        app.sort_mode = value
        app._mark_state_dirty()
        app._refresh_table()
        app._refresh_side()


def action_pick_filters(app: Any, *, mode_active: str, filter_manage_screen: Any) -> None:
    rows = app.active_rows if app.view_mode == mode_active else app.archived_rows
    app.push_screen(filter_manage_screen(app.query, app.query, rows), app._on_pick_filters)


def on_pick_filters(
    app: Any,
    value: str | None,
    *,
    normalize_filter_expression: Callable[[str], str],
) -> None:
    if value is None:
        return
    app.query = normalize_filter_expression(value.strip())
    app.filter_expr = app.query
    app.query_cursor = len(app.query)
    app._reset_query_completion()
    app._mark_state_dirty()
    app._refresh_table()
    app._refresh_side()


def action_pick_category(
    app: Any,
    *,
    suffixes: list[str],
    single_choice_screen: Any,
) -> None:
    options = [(f"set_suffix:{s}", f"set suffix .{s} on selected") for s in suffixes]
    options += [("clear_suffix", "remove configured suffix on selected")]
    app.push_screen(single_choice_screen("Suffix picker", options), app._on_pick_category)


def on_pick_category(
    app: Any,
    value: str | None,
    *,
    project_row: Callable[..., ProjectRow],
) -> None:
    if not value:
        return
    suffix: str | None = None
    if value.startswith("set_suffix:"):
        suffix = value.split(":", 1)[1]
    elif value == "clear_suffix":
        suffix = None
    else:
        return

    targets = app._target_rows()
    new_selected: set[Path] = set()
    removed_paths: list[Path] = []
    updated_rows: list[ProjectRow] = []
    for row in targets:
        new_path = app._apply_category(row, suffix)
        if not new_path:
            continue
        removed_paths.append(row.path)
        new_selected.add(new_path)
        try:
            updated_rows.append(
                project_row(
                    new_path,
                    archived=row.archived,
                    restore_target=row.restore_target,
                    archived_ts=row.archived_ts,
                )
            )
        except (OSError, ValueError, TypeError):
            pass

    app.multi_selected = new_selected
    if new_selected:
        app.selected_path = next(iter(new_selected))
    if removed_paths:
        app._remove_paths_local(removed_paths)
    for updated in updated_rows:
        app._upsert_row_local(updated)
    if updated_rows or removed_paths:
        app._touch_rows_cache(updated_rows, removed=removed_paths)
        app._start_cache_refresh("suffix update", force=False)
        app._request_tag_sync("suffix update")
    else:
        app._refresh_data()
    app._log(f"suffix update: {value}", "info")
    app._refresh_table()
    app._refresh_side()


def action_toggle_view(
    app: Any,
    *,
    normalize_sort_mode_for_view: Callable[[str, str], str],
) -> None:
    app._capture_table_position()
    app.view_mode = "archive" if app.view_mode == "active" else "active"
    app.sort_mode = normalize_sort_mode_for_view(app.view_mode, app.sort_mode)
    app._apply_view_state(app.view_mode)
    app.multi_selected.clear()
    app._configure_table_columns()
    app._mark_state_dirty()
    app._refresh_table()
    app._restore_table_position()
    app.call_after_refresh(app._restore_table_position)
    app.set_timer(0.12, app._retry_pending_restore)
    app._refresh_side()


def action_reset_view(app: Any, *, widget_projects: str) -> None:
    app.query = ""
    app.filter_expr = ""
    app.query_cursor = 0
    app._reset_query_completion()
    app.selected_path = None
    app.multi_selected.clear()
    app._mark_state_dirty()
    app._refresh_table()
    table = app.query_one(widget_projects, DataTable)
    rows = app._current_rows()
    if rows:
        app.selected_path = rows[0].path
        try:
            table.cursor_coordinate = (0, 0)
        except WIDGET_API_ERRORS:
            pass
    try:
        cur_x = int(getattr(table, "scroll_x", 0) or 0)
        table.scroll_to(x=cur_x, y=0, animate=False)
    except WIDGET_API_ERRORS:
        pass
    app._state_cursor_row = 0
    app._state_scroll_y = 0
    app._view_cursor_row[app.view_mode] = 0
    app._view_scroll_y[app.view_mode] = 0
    app._view_row_offset[app.view_mode] = 0
    app._view_selected_path[app.view_mode] = app.selected_path
    app._restore_target_path[app.view_mode] = app.selected_path
    app._restore_pending[app.view_mode] = False
    app._restore_apply_scroll[app.view_mode] = False
    app._mark_state_dirty()
    app._refresh_side()
