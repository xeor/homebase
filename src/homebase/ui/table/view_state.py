from __future__ import annotations

from typing import Any

from textual.widgets import DataTable


def capture_table_position(app: Any, *, widget_projects: str) -> bool:
    if app._restore_pending.get(app.view_mode, False) or app._restore_apply_scroll.get(
        app.view_mode, False
    ):
        return False
    changed = False
    prev_selected = app._view_selected_path.get(app.view_mode)
    if app.selected_path != prev_selected:
        app._view_selected_path[app.view_mode] = app.selected_path
        app._restore_target_path[app.view_mode] = app.selected_path
        changed = True
    try:
        table = app.query_one(widget_projects, DataTable)
    except (
        LookupError,
        KeyError,
        IndexError,
        AttributeError,
        RuntimeError,
        ValueError,
        TypeError,
    ):
        return changed

    cur_row = int(getattr(table, "cursor_row", app._state_cursor_row) or 0)
    cur_scroll = int(getattr(table, "scroll_y", app._state_scroll_y) or 0)
    if cur_row != app._state_cursor_row:
        app._state_cursor_row = cur_row
        changed = True
    if cur_scroll != app._state_scroll_y:
        app._state_scroll_y = cur_scroll
        changed = True

    if app._view_cursor_row.get(app.view_mode, 0) != app._state_cursor_row:
        app._view_cursor_row[app.view_mode] = app._state_cursor_row
        changed = True
    if app._view_scroll_y.get(app.view_mode, 0) != app._state_scroll_y:
        app._view_scroll_y[app.view_mode] = app._state_scroll_y
        changed = True
    rows = app._current_rows()
    selected_idx = -1
    if app.selected_path is not None:
        selected_idx = next(
            (i for i, row in enumerate(rows) if app._same_path(row.path, app.selected_path)),
            -1,
        )
    if selected_idx < 0:
        selected_idx = app._state_cursor_row
    row_offset = max(0, selected_idx - app._state_scroll_y)
    if app._view_row_offset.get(app.view_mode, 0) != row_offset:
        app._view_row_offset[app.view_mode] = row_offset
        changed = True
    return changed


def retry_pending_restore(app: Any) -> None:
    if app.fast_exit_requested:
        return
    if app._restore_retry_left <= 0:
        for view in ("active", "archive"):
            app._restore_pending[view] = False
            app._restore_apply_scroll[view] = False
        app._mark_state_dirty()
        return
    if not any(app._restore_pending.values()):
        return
    app._restore_retry_left -= 1
    if app._restore_pending.get(app.view_mode, False):
        app._restore_table_position()
    app.set_timer(0.08, app._retry_pending_restore)


def cancel_restore_for_current_view(app: Any) -> None:
    view = app.view_mode
    app._restore_pending[view] = False
    app._restore_apply_scroll[view] = False
    app._restore_retry_left = 0


def apply_view_state(app: Any, view: str) -> None:
    app.selected_path = app._view_selected_path.get(view)
    app._state_cursor_row = int(app._view_cursor_row.get(view, 0) or 0)
    app._state_scroll_y = int(app._view_scroll_y.get(view, 0) or 0)
    app._restore_target_path[view] = app.selected_path
    app._restore_pending[view] = app.selected_path is not None
    app._restore_apply_scroll[view] = True
    app._restore_retry_left = 32


def state_snapshot(
    app: Any,
    *,
    state_key_side_main: str,
    state_key_side_selected: str,
    state_key_side_info: str,
    state_key_side_settings: str,
    state_key_hotbar_slot_index: str,
) -> dict[str, object]:
    app._capture_table_position()
    active_selected = app._view_selected_path.get("active")
    archive_selected = app._view_selected_path.get("archive")
    return {
        "view": app.view_mode,
        "sort": app.sort_mode,
        "query": app.query,
        state_key_side_main: app.side_main_tab,
        state_key_side_selected: app.side_selected_tab,
        state_key_side_info: app.side_info_tab,
        state_key_side_settings: app.side_settings_tab,
        state_key_hotbar_slot_index: int(max(0, app.hotbar_selected_index)),
        "selected_path": str(app.selected_path) if app.selected_path is not None else "",
        "cursor_row": app._state_cursor_row,
        "scroll_y": app._state_scroll_y,
        "selected_path_active": str(active_selected) if active_selected is not None else "",
        "selected_path_archive": str(archive_selected)
        if archive_selected is not None
        else "",
        "cursor_row_active": int(app._view_cursor_row.get("active", 0) or 0),
        "cursor_row_archive": int(app._view_cursor_row.get("archive", 0) or 0),
        "scroll_y_active": int(app._view_scroll_y.get("active", 0) or 0),
        "scroll_y_archive": int(app._view_scroll_y.get("archive", 0) or 0),
        "row_offset_active": int(app._view_row_offset.get("active", 0) or 0),
        "row_offset_archive": int(app._view_row_offset.get("archive", 0) or 0),
    }


def restore_table_position(app: Any, *, widget_projects: str) -> None:
    try:
        _ = app.query_one(widget_projects, DataTable)
    except (
        LookupError,
        KeyError,
        IndexError,
        AttributeError,
        RuntimeError,
        ValueError,
        TypeError,
    ):
        return
    rows = app._current_rows()
    if not rows:
        return

    idx = 0
    if app.selected_path is not None:
        idx = next(
            (i for i, row in enumerate(rows) if app._same_path(row.path, app.selected_path)),
            -1,
        )
    if idx < 0:
        target = app._restore_target_path.get(app.view_mode)
        target_idx = (
            next(
                (i for i, row in enumerate(rows) if app._same_path(row.path, target)),
                -1,
            )
            if target is not None
            else -1
        )
        if target_idx >= 0:
            idx = target_idx
            app.selected_path = rows[idx].path
            app._view_selected_path[app.view_mode] = app.selected_path
            app._restore_target_path[app.view_mode] = app.selected_path
        elif app._restore_pending.get(app.view_mode, False):
            return
        else:
            idx = min(max(0, app._state_cursor_row), len(rows) - 1)
            app.selected_path = rows[idx].path

    target_idx = idx
    saved_offset = max(0, int(app._view_row_offset.get(app.view_mode, 0) or 0))
    target_scroll_y = max(0, target_idx - saved_offset)

    def _apply_position() -> None:
        try:
            t = app.query_one(widget_projects, DataTable)
        except (
            LookupError,
            KeyError,
            IndexError,
            AttributeError,
            RuntimeError,
            ValueError,
            TypeError,
        ):
            return
        try:
            t.cursor_coordinate = (target_idx, 0)
        except (
            LookupError,
            KeyError,
            IndexError,
            AttributeError,
            RuntimeError,
            ValueError,
            TypeError,
        ):
            pass
        try:
            cur_x = int(getattr(t, "scroll_x", 0) or 0)
            t.scroll_to(x=cur_x, y=target_scroll_y, animate=False)
        except (
            LookupError,
            KeyError,
            IndexError,
            AttributeError,
            RuntimeError,
            ValueError,
            TypeError,
        ):
            pass

    _apply_position()
    if app._restore_pending.get(app.view_mode, False):
        app.call_after_refresh(_apply_position)
    app._restore_apply_scroll[app.view_mode] = False
