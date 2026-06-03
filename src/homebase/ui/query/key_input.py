from __future__ import annotations

import time
from typing import Any

from textual.widgets import DataTable, Input

_INPUT_FOCUS_IDS = frozenset({
    "filter_query",
    "filter_mgmt_input",
    "value_input",
    "new_name",
    "restore_input",
    "choice_filter",
})

_TABLE_NAV_KEYS = frozenset({
    "up", "down", "pageup", "pagedown", "home", "end",
})


def _should_ignore_for_focus(focused: Any) -> bool:
    return isinstance(focused, Input) and focused.id in _INPUT_FOCUS_IDS


def _handle_table_nav_side_effects(app: Any, event: Any) -> None:
    if app._table_is_active_focus() and event.key in _TABLE_NAV_KEYS:
        app._cancel_restore_for_current_view()
    if (
        app.side_main_tab == "selected"
        and app.side_selected_tab == "readme"
        and app._table_is_active_focus()
        and event.key in _TABLE_NAV_KEYS
    ):
        app._readme_nav_allow_until = time.time() + 0.35


def _handle_tab_completion(app: Any, event: Any, widget_projects: str) -> bool:
    if event.key not in {"tab", "shift+tab", "backtab"}:
        return False
    table = app.query_one(widget_projects, DataTable)
    if not table.has_focus:
        return True
    app._apply_query_completion(event.key == "tab")
    event.stop()
    return True


def _handle_wip_open(
    app: Any, event: Any, wip_open_symbol_map: dict[str, int]
) -> bool:
    if event.character and event.character in wip_open_symbol_map:
        app._open_wip_index(wip_open_symbol_map[event.character])
        event.stop()
        return True
    if event.key in wip_open_symbol_map:
        app._open_wip_index(wip_open_symbol_map[event.key])
        event.stop()
        return True
    return False


def _handle_custom_hotkey(
    app: Any, event: Any, custom_hotkey_targets: dict[str, str]
) -> bool:
    target = custom_hotkey_targets.get(event.key.lower())
    if not target and event.character:
        target = custom_hotkey_targets.get(event.character.lower())
    if not target:
        return False
    app._dispatch_hotkey_target(target)
    event.stop()
    return True


_ROUTE_ACTIONS = {
    "left": "action_route_left",
    "right": "action_route_right",
    "home": "action_route_home",
    "end": "action_route_end",
}


def _handle_route_keys(app: Any, event: Any) -> bool:
    action = _ROUTE_ACTIONS.get(event.key)
    if action is None:
        return False
    getattr(app, action)()
    event.stop()
    return True


def _handle_tab_completion_focused(app: Any, event: Any) -> bool:
    if event.key == "tab":
        app._apply_query_completion(True)
        event.stop()
        return True
    if event.key in {"shift+tab", "backtab"}:
        app._apply_query_completion(False)
        event.stop()
        return True
    return False


def _handle_line_edit_jumps(app: Any, event: Any) -> bool:
    if event.key == "ctrl+a":
        app.query_cursor = 0
        app._refresh_side()
        event.stop()
        return True
    if event.key == "ctrl+e":
        app.query_cursor = len(app.query)
        app._refresh_side()
        event.stop()
        return True
    return False


def _handle_select_mode(app: Any, event: Any) -> bool:
    if not app.select_mode:
        return False
    if event.key == "space":
        app.action_toggle_selected()
        event.stop()
        return True
    if event.key == "a":
        app.multi_selected = {row.path for row in app._current_rows()}
        app._refresh_table()
        app._refresh_side()
        event.stop()
        return True
    if event.key == "c":
        app.multi_selected.clear()
        app._refresh_table()
        app._refresh_side()
        event.stop()
        return True
    if event.key == "u":
        app.multi_selected = {
            row.path for row in app._current_rows() if not row.tags
        }
        app._refresh_table()
        app._refresh_side()
        event.stop()
        return True
    if event.key == "backspace" or (
        event.character is not None and event.character.isprintable()
    ):
        event.stop()
        return True
    return False


def _apply_query_change(app: Any) -> None:
    app.filter_expr = app.query
    app._reset_query_completion()
    app._mark_state_dirty()
    app._queue_query_apply()


def _handle_query_edit(app: Any, event: Any) -> bool:
    if event.key == "backspace":
        if app.query_cursor > 0:
            i = app.query_cursor
            app.query = app.query[: i - 1] + app.query[i:]
            app.query_cursor -= 1
        _apply_query_change(app)
        event.stop()
        return True
    if event.key in {"delete", "ctrl+d"}:
        if app.query_cursor < len(app.query):
            i = app.query_cursor
            app.query = app.query[:i] + app.query[i + 1 :]
        _apply_query_change(app)
        event.stop()
        return True
    if event.character is not None and event.character.isprintable():
        i = app.query_cursor
        app.query = app.query[:i] + event.character + app.query[i:]
        app.query_cursor += len(event.character)
        _apply_query_change(app)
        event.stop()
        return True
    return False


def on_key(
    app: Any,
    event: Any,
    *,
    widget_projects: str,
    wip_open_symbol_map: dict[str, int],
    custom_hotkey_targets: dict[str, str],
) -> None:
    if app._modal_active():
        return
    if _should_ignore_for_focus(app.focused):
        return
    if app._handle_settings_table_key(event):
        event.stop()
        return

    _handle_table_nav_side_effects(app, event)

    if _handle_tab_completion(app, event, widget_projects):
        return
    if _handle_wip_open(app, event, wip_open_symbol_map):
        return

    table = app.query_one(widget_projects, DataTable)
    if not table.has_focus:
        return

    if _handle_custom_hotkey(app, event, custom_hotkey_targets):
        return
    if _handle_route_keys(app, event):
        return
    if _handle_tab_completion_focused(app, event):
        return
    if _handle_line_edit_jumps(app, event):
        return
    if _handle_select_mode(app, event):
        return
    _handle_query_edit(app, event)
