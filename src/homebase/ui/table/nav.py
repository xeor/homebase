from __future__ import annotations

from typing import Any

from textual.widgets import DataTable, Input


def scroll_table_x(app: Any, delta: int, *, widget_projects: str) -> None:
    table = app.query_one(widget_projects, DataTable)
    try:
        cur = int(getattr(table, "scroll_x", 0) or 0)
        nxt = max(0, cur + delta)
        table.scroll_to(x=nxt, y=getattr(table, "scroll_y", None), animate=False)
        return
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
        table.scroll_relative(x=delta, y=0, animate=False)
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


def table_is_active_focus(app: Any, *, widget_projects: str) -> bool:
    focused = app.focused
    if isinstance(focused, Input) and focused.id in {
        "filter_query",
        "filter_mgmt_input",
        "value_input",
        "new_name",
        "restore_input",
        "choice_filter",
    }:
        return False
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
        return False
    return table.has_focus


def action_query_left(app: Any) -> None:
    if not app._table_is_active_focus():
        return
    app.query_cursor = max(0, app.query_cursor - 1)
    app._refresh_side()


def action_query_right(app: Any) -> None:
    if not app._table_is_active_focus():
        return
    app.query_cursor = min(len(app.query), app.query_cursor + 1)
    app._refresh_side()


def action_query_home(app: Any) -> None:
    if not app._table_is_active_focus():
        return
    app.query_cursor = 0
    app._refresh_side()


def action_query_end(app: Any) -> None:
    if not app._table_is_active_focus():
        return
    app.query_cursor = len(app.query)
    app._refresh_side()


def action_table_scroll_left(app: Any) -> None:
    if not app._table_is_active_focus():
        return
    app._scroll_table_x(-12)


def action_table_scroll_right(app: Any) -> None:
    if not app._table_is_active_focus():
        return
    app._scroll_table_x(12)


def action_route_left(app: Any) -> None:
    if app.side_main_tab == "settings" and app.side_settings_tab == "table":
        app._table_settings_reorder(-1)
        return
    focused = app.focused
    if isinstance(focused, Input):
        focused.action_cursor_left(False)
        return
    if not app._table_is_active_focus():
        return
    app.query_cursor = max(0, app.query_cursor - 1)
    app._refresh_side()


def action_route_right(app: Any) -> None:
    if app.side_main_tab == "settings" and app.side_settings_tab == "table":
        app._table_settings_reorder(1)
        return
    focused = app.focused
    if isinstance(focused, Input):
        focused.action_cursor_right(False)
        return
    if not app._table_is_active_focus():
        return
    app.query_cursor = min(len(app.query), app.query_cursor + 1)
    app._refresh_side()


def action_route_home(app: Any) -> None:
    focused = app.focused
    if isinstance(focused, Input):
        focused.action_home(False)
        return
    if not app._table_is_active_focus():
        return
    app.query_cursor = 0
    app._refresh_side()


def action_route_end(app: Any) -> None:
    focused = app.focused
    if isinstance(focused, Input):
        focused.action_end(False)
        return
    if not app._table_is_active_focus():
        return
    app.query_cursor = len(app.query)
    app._refresh_side()
