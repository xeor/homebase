from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from homebase.ui.table import view_actions


def _make_app(**overrides: object) -> SimpleNamespace:
    app = SimpleNamespace(
        view_mode="active",
        sort_mode="last",
        query="",
        filter_expr="",
        query_cursor=0,
        selected_path=None,
        multi_selected=set(),
        active_rows=[],
        archived_rows=[],
        _view_cursor_row={"active": 0, "archive": 0},
        _view_scroll_y={"active": 0, "archive": 0},
        _view_row_offset={"active": 0, "archive": 0},
        _view_selected_path={"active": None, "archive": None},
        _restore_target_path={"active": None, "archive": None},
        _restore_pending={"active": False, "archive": False},
        _restore_apply_scroll={"active": False, "archive": False},
        _state_cursor_row=0,
        _state_scroll_y=0,
        push_screen_calls=[],
        log_calls=[],
        dirty_marks=0,
        table_refreshes=0,
        side_refreshes=0,
        timer_calls=[],
    )
    app.push_screen = lambda screen, cb=None: app.push_screen_calls.append((screen, cb))
    app._mark_state_dirty = lambda: app.__dict__.__setitem__(
        "dirty_marks", app.dirty_marks + 1
    )
    app._refresh_table = lambda: app.__dict__.__setitem__(
        "table_refreshes", app.table_refreshes + 1
    )
    app._refresh_side = lambda: app.__dict__.__setitem__(
        "side_refreshes", app.side_refreshes + 1
    )
    app._reset_query_completion = lambda: app.__dict__.__setitem__(
        "completion_reset", True
    )
    app._capture_table_position = lambda: True
    app._apply_view_state = lambda view: app.__dict__.__setitem__(
        "_applied_view", view
    )
    app._configure_table_columns = lambda: app.__dict__.__setitem__(
        "_cols_configured", True
    )
    app._restore_table_position = lambda: app.__dict__.__setitem__(
        "_restore_called", True
    )
    app.call_after_refresh = lambda fn: app.timer_calls.append(("after_refresh", fn))
    app.set_timer = lambda delay, fn: app.timer_calls.append((delay, fn))
    app._retry_pending_restore = lambda: None
    app._current_rows = lambda: app.active_rows
    app._on_pick_sort = "on_sort_cb"
    app._on_pick_filters = "on_filters_cb"
    app._on_pick_category = "on_category_cb"

    class FakeTable:
        def __init__(self) -> None:
            self.cursor_coordinate = (0, 0)
            self.scroll_x = 0
            self.scroll_y = 0

        def scroll_to(self, **kw):
            self.last_scroll = kw

    fake = FakeTable()
    app._fake = fake
    app.query_one = lambda _sel, _cls: fake
    app._log = lambda msg, level: app.log_calls.append((level, msg))

    for k, v in overrides.items():
        setattr(app, k, v)
    return app


def test_action_pick_sort_pushes_single_choice_screen() -> None:
    app = _make_app()

    def sort_modes_for_view(_v: str) -> list[tuple[str, str]]:
        return [("last", "Last")]

    def screen_factory(title: str, opts: list[tuple[str, str]]) -> dict[str, object]:
        return {"title": title, "options": opts}

    view_actions.action_pick_sort(
        app,
        sort_modes_for_view=sort_modes_for_view,
        single_choice_screen=screen_factory,
    )
    assert app.push_screen_calls
    screen, cb = app.push_screen_calls[0]
    assert screen["title"] == "Sort picker"
    assert cb == "on_sort_cb"


def test_on_pick_sort_updates_mode_when_value_allowed() -> None:
    app = _make_app()
    view_actions.on_pick_sort(
        app,
        "name",
        sort_modes_for_view=lambda _v: [("last", "Last"), ("name", "Name")],
    )
    assert app.sort_mode == "name"
    assert app.dirty_marks == 1
    assert app.table_refreshes == 1


def test_on_pick_sort_noops_for_disallowed_value() -> None:
    app = _make_app()
    view_actions.on_pick_sort(
        app,
        "ghost",
        sort_modes_for_view=lambda _v: [("last", "Last")],
    )
    assert app.sort_mode == "last"
    assert app.dirty_marks == 0


def test_action_pick_filters_uses_active_rows_in_active_view() -> None:
    captured: list[tuple[str, str, list]] = []

    def screen(query: str, expr: str, rows: list) -> dict[str, object]:
        captured.append((query, expr, rows))
        return {"q": query}

    rows = ["row"]
    app = _make_app(view_mode="active", active_rows=rows, query="foo")
    view_actions.action_pick_filters(
        app,
        mode_active="active",
        filter_manage_screen=screen,
    )
    assert captured == [("foo", "foo", rows)]


def test_on_pick_filters_updates_expression_and_marks_dirty() -> None:
    app = _make_app()
    view_actions.on_pick_filters(
        app,
        "  #foo  ",
        normalize_filter_expression=lambda s: s.strip(),
    )
    assert app.query == "#foo"
    assert app.filter_expr == "#foo"
    assert app.query_cursor == len(app.query)


def test_on_pick_filters_ignores_none() -> None:
    app = _make_app(query="orig")
    view_actions.on_pick_filters(
        app,
        None,
        normalize_filter_expression=lambda s: s,
    )
    assert app.query == "orig"


def test_action_pick_category_lists_suffix_options() -> None:
    captured: list[list[tuple[str, str]]] = []

    def screen(_title: str, opts: list[tuple[str, str]]) -> dict[str, object]:
        captured.append(opts)
        return {"opts": opts}

    app = _make_app()
    view_actions.action_pick_category(
        app,
        suffixes=["tmp", "fork"],
        single_choice_screen=screen,
    )
    assert any(opt[0] == "set_suffix:tmp" for opt in captured[0])
    assert ("clear_suffix", "remove configured suffix on selected") in captured[0]


def test_on_pick_category_clears_when_no_value() -> None:
    app = _make_app(multi_selected={Path("/p")})
    view_actions.on_pick_category(app, None, project_row=lambda *_a, **_k: None)
    assert app.multi_selected == {Path("/p")}


def test_on_pick_category_handles_unknown_value() -> None:
    app = _make_app(multi_selected={Path("/p")})
    view_actions.on_pick_category(app, "weird", project_row=lambda *_a, **_k: None)
    assert app.multi_selected == {Path("/p")}


def test_action_toggle_view_swaps_modes_and_resets_helpers() -> None:
    app = _make_app(view_mode="active")
    view_actions.action_toggle_view(
        app,
        normalize_sort_mode_for_view=lambda view, mode: f"{view}:{mode}",
    )
    assert app.view_mode == "archive"
    assert app.sort_mode == "archive:last"
    assert app.__dict__["_applied_view"] == "archive"
    assert app.timer_calls  # set_timer + call_after_refresh both fire


def test_action_reset_view_clears_query_and_state() -> None:
    rows = [SimpleNamespace(path=Path("/p"))]
    app = _make_app(query="foo", active_rows=rows)
    view_actions.action_reset_view(app, widget_projects="#tbl")
    assert app.query == ""
    assert app.filter_expr == ""
    assert app.query_cursor == 0
    assert app.selected_path == Path("/p")
    assert app._state_cursor_row == 0
    assert app._state_scroll_y == 0
    assert app.dirty_marks >= 1


def test_action_reset_view_handles_empty_rows() -> None:
    app = _make_app(query="foo", active_rows=[])
    view_actions.action_reset_view(app, widget_projects="#tbl")
    assert app.selected_path is None
