from __future__ import annotations

import time
from typing import Any

from textual.widgets import DataTable, Input


def on_key(
    app: Any,
    event: Any,
    *,
    widget_projects: str,
    wip_open_symbol_map: dict[str, int],
) -> None:
    if app._modal_active():
        return
    focused = app.focused
    if isinstance(focused, Input) and focused.id in {
        "filter_query",
        "filter_mgmt_input",
        "value_input",
        "new_name",
        "restore_input",
        "choice_filter",
    }:
        return

    if app._handle_settings_table_key(event):
        event.stop()
        return

    if app._table_is_active_focus() and event.key in {
        "up",
        "down",
        "pageup",
        "pagedown",
        "home",
        "end",
    }:
        app._cancel_restore_for_current_view()

    if (
        app.side_main_tab == "selected"
        and app.side_selected_tab == "readme"
        and app._table_is_active_focus()
        and event.key in {"up", "down", "pageup", "pagedown", "home", "end"}
    ):
        app._readme_nav_allow_until = time.time() + 0.35

    if event.key in {"tab", "shift+tab", "backtab"}:
        table = app.query_one(widget_projects, DataTable)
        if not table.has_focus:
            table.focus()
        if event.key == "tab":
            app._apply_query_completion(True)
        else:
            app._apply_query_completion(False)
        event.stop()
        return

    if event.character and event.character in wip_open_symbol_map:
        app._open_wip_index(wip_open_symbol_map[event.character])
        event.stop()
        return
    if event.key in wip_open_symbol_map:
        app._open_wip_index(wip_open_symbol_map[event.key])
        event.stop()
        return

    table = app.query_one(widget_projects, DataTable)
    if not table.has_focus:
        return

    if event.key == "left":
        app.action_route_left()
        event.stop()
        return
    if event.key == "right":
        app.action_route_right()
        event.stop()
        return
    if event.key == "home":
        app.action_route_home()
        event.stop()
        return
    if event.key == "end":
        app.action_route_end()
        event.stop()
        return

    if event.key == "tab":
        app._apply_query_completion(True)
        event.stop()
        return
    if event.key in {"shift+tab", "backtab"}:
        app._apply_query_completion(False)
        event.stop()
        return

    if event.key == "ctrl+a":
        app.query_cursor = 0
        app._refresh_side()
        event.stop()
        return
    if event.key == "ctrl+e":
        app.query_cursor = len(app.query)
        app._refresh_side()
        event.stop()
        return

    if app.select_mode:
        if event.key == "space":
            app.action_toggle_selected()
            event.stop()
            return
        if event.key == "a":
            app.multi_selected = {row.path for row in app._current_rows()}
            app._refresh_table()
            app._refresh_side()
            event.stop()
            return
        if event.key == "c":
            app.multi_selected.clear()
            app._refresh_table()
            app._refresh_side()
            event.stop()
            return
        if event.key == "u":
            app.multi_selected = {row.path for row in app._current_rows() if not row.tags}
            app._refresh_table()
            app._refresh_side()
            event.stop()
            return

        if event.key == "backspace" or (
            event.character is not None and event.character.isprintable()
        ):
            event.stop()
            return

    if event.key == "backspace":
        if app.query_cursor > 0:
            i = app.query_cursor
            app.query = app.query[: i - 1] + app.query[i:]
            app.query_cursor -= 1
        app.filter_expr = app.query
        app._reset_query_completion()
        app._mark_state_dirty()
        app._queue_query_apply()
        event.stop()
        return

    if event.key in {"delete", "ctrl+d"}:
        if app.query_cursor < len(app.query):
            i = app.query_cursor
            app.query = app.query[:i] + app.query[i + 1 :]
        app.filter_expr = app.query
        app._reset_query_completion()
        app._mark_state_dirty()
        app._queue_query_apply()
        event.stop()
        return

    if event.character is not None and event.character.isprintable():
        i = app.query_cursor
        app.query = app.query[:i] + event.character + app.query[i:]
        app.query_cursor += len(event.character)
        app.filter_expr = app.query
        app._reset_query_completion()
        app._mark_state_dirty()
        app._queue_query_apply()
        event.stop()
        return
