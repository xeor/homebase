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


def on_data_table_row_highlighted(app: Any, event: Any) -> None:
    table_id = str(getattr(getattr(event, "data_table", None), "id", "") or "")
    if table_id == "side_settings_table":
        try:
            idx = int(str(event.row_key.value))
        except (AttributeError, TypeError, ValueError):
            return
        if app.side_settings_tab == "open":
            max_idx = max(0, len(app._open_mode_rows()) - 1)
            app.open_settings_index = max(0, min(idx, max_idx))
            app._update_open_settings_details()
        elif app.side_settings_tab == "table_config":
            max_idx = max(0, len(app._table_config_rows()) - 1)
            app.table_config_index = max(0, min(idx, max_idx))
        else:
            current_columns = app._table_columns_for_view(app.view_mode)
            app.table_settings_index = max(0, min(idx, len(current_columns) - 1))
        return
    if table_id and table_id != "projects":
        return
    if app._suspend_project_row_highlight:
        return

    if (
        app.side_main_tab == "selected"
        and app.side_selected_tab == "readme"
        and time.time() > float(app._readme_nav_allow_until)
    ):
        return

    highlighted_path: Path | None
    try:
        highlighted_path = Path(str(event.row_key.value))
    except (TypeError, ValueError):
        highlighted_path = None

    if app._restore_pending.get(app.view_mode, False) or app._restore_apply_scroll.get(
        app.view_mode, False
    ):
        target = app._restore_target_path.get(app.view_mode)
        if target is not None and app._same_path(highlighted_path, target):
            app.selected_path = highlighted_path
            app._view_selected_path[app.view_mode] = app.selected_path
            app._restore_target_path[app.view_mode] = app.selected_path
            app._restore_pending[app.view_mode] = False
            app._restore_apply_scroll[app.view_mode] = False
            app._mark_state_dirty()
            app._refresh_side()
        return

    app.selected_path = highlighted_path
    app._bump_row_usage(app.selected_path, 0.4)
    app._view_selected_path[app.view_mode] = app.selected_path
    app._restore_target_path[app.view_mode] = app.selected_path
    app._restore_pending[app.view_mode] = False
    app._restore_apply_scroll[app.view_mode] = False
    app._mark_state_dirty()
    app._refresh_side()


def on_data_table_row_selected(app: Any, event: Any) -> None:
    table_id = str(getattr(getattr(event, "data_table", None), "id", "") or "")
    if table_id == "side_settings_table":
        try:
            idx = int(str(event.row_key.value))
        except (AttributeError, TypeError, ValueError):
            return
        if app.side_settings_tab == "open":
            max_idx = max(0, len(app._open_mode_rows()) - 1)
            app.open_settings_index = max(0, min(idx, max_idx))
            app._open_mode_select_selected()
            app._update_open_settings_details()
        elif app.side_settings_tab == "table_config":
            max_idx = max(0, len(app._table_config_rows()) - 1)
            app.table_config_index = max(0, min(idx, max_idx))
        else:
            current_columns = app._table_columns_for_view(app.view_mode)
            app.table_settings_index = max(0, min(idx, len(current_columns) - 1))
        return
    if table_id != "projects":
        return
    try:
        app.selected_path = Path(str(event.row_key.value))
    except (TypeError, ValueError):
        return
    app._bump_row_usage(app.selected_path, 1.2)
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
