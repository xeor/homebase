from __future__ import annotations

import time
from pathlib import Path
from typing import Any


def apply_category(row: Any, suffix: str | None, *, suffixes: list[str]) -> Path | None:
    if bool(getattr(row, "archived", False)):
        return None
    current = Path(str(getattr(row, "path")))
    name = current.name

    base = name
    for sfx in suffixes:
        ext = f".{sfx}"
        if base.endswith(ext):
            base = base[: -len(ext)]
            break

    if suffix is None:
        if base == name:
            return current
        new_name = base
    else:
        if name.endswith(f".{suffix}"):
            return current
        new_name = f"{base}.{suffix}"

    target = current.parent / new_name
    if target.exists():
        return None
    current.rename(target)
    return target


def _event_table_id(event: Any) -> str:
    return str(getattr(getattr(event, "data_table", None), "id", "") or "")


def _row_key_path(event: Any) -> Path | None:
    try:
        return Path(str(event.row_key.value))
    except (TypeError, ValueError):
        return None


def _sync_settings_table_index(app: Any, event: Any) -> bool:
    """Move the settings-column cursor to the highlighted/selected row.

    Returns True when the event targeted the settings table and was
    consumed, so the caller stops (the project-table logic must not run)."""
    if _event_table_id(event) != "side_settings_table":
        return False
    try:
        idx = int(str(event.row_key.value))
    except (AttributeError, TypeError, ValueError):
        return True
    current_columns = app._table_columns_for_view(app.view_mode)
    app.table_settings_index = max(0, min(idx, len(current_columns) - 1))
    return True


def _commit_selected_row(app: Any, path: Path) -> None:
    app.selected_path = path
    app._view_selected_path[app.view_mode] = path
    app._restore_target_path[app.view_mode] = path
    app._restore_pending[app.view_mode] = False
    app._restore_apply_scroll[app.view_mode] = False
    app._mark_state_dirty()
    app._refresh_side()


def _apply_restore_highlight(app: Any, highlighted_path: Path) -> bool:
    """Consume a highlight while a restore is pending. Returns True if the
    row-highlight handler should stop (restore mode owns the cursor)."""
    if not (
        app._restore_pending.get(app.view_mode, False)
        or app._restore_apply_scroll.get(app.view_mode, False)
    ):
        return False
    target = app._restore_target_path.get(app.view_mode)
    if target is not None and app._same_path(highlighted_path, target):
        _commit_selected_row(app, highlighted_path)
    return True


def _readme_nav_suppresses_highlight(app: Any) -> bool:
    return (
        app.side_main_tab == "selected"
        and app.side_selected_tab == "readme"
        and time.time() > float(app._readme_nav_allow_until)
    )


def on_data_table_row_highlighted(app: Any, event: Any) -> None:
    if _sync_settings_table_index(app, event):
        return
    table_id = _event_table_id(event)
    if table_id and table_id != "projects":
        return
    if app._suspend_project_row_highlight or _readme_nav_suppresses_highlight(app):
        return

    highlighted_path = _row_key_path(event)
    if highlighted_path is None:
        return
    if not any(app._same_path(row.path, highlighted_path) for row in app._current_rows()):
        return
    if _apply_restore_highlight(app, highlighted_path):
        return

    app._bump_row_usage(highlighted_path, 0.4)
    _commit_selected_row(app, highlighted_path)


def on_data_table_row_selected(app: Any, event: Any) -> None:
    if _sync_settings_table_index(app, event):
        return
    if _event_table_id(event) != "projects":
        return
    path = _row_key_path(event)
    if path is None:
        return
    app.selected_path = path
    app._bump_row_usage(path, 1.2)
    app.action_open_selected()


def action_toggle_select_mode(app: Any) -> None:
    app.select_mode = not app.select_mode
    if not app.select_mode:
        app.multi_selected.clear()
    app._refresh_table()
    app._refresh_side()


def action_toggle_selected(app: Any) -> None:
    row = app._selected_row()
    if not row:
        return
    if row.path in app.multi_selected:
        app.multi_selected.remove(row.path)
    else:
        app.multi_selected.add(row.path)
    app._refresh_table()
    app._refresh_side()
