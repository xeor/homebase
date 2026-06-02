from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from homebase.ui.table import view_state


def _make_app(**overrides: object) -> SimpleNamespace:
    app = SimpleNamespace(
        view_mode="active",
        sort_mode="last",
        query="",
        selected_path=None,
        side_main_tab="selected",
        side_selected_tab="overview",
        side_info_tab="events",
        side_settings_tab="table",
        hotbar_selected_index=0,
        _restore_pending={"active": False, "archive": False},
        _restore_apply_scroll={"active": False, "archive": False},
        _restore_target_path={"active": None, "archive": None},
        _view_selected_path={"active": None, "archive": None},
        _view_cursor_row={"active": 0, "archive": 0},
        _view_scroll_y={"active": 0, "archive": 0},
        _view_row_offset={"active": 0, "archive": 0},
        _state_cursor_row=0,
        _state_scroll_y=0,
        _restore_retry_left=0,
        fast_exit_requested=False,
        timer_calls=[],
        dirty_marks=0,
    )
    app._mark_state_dirty = lambda: app.__dict__.__setitem__(
        "dirty_marks", app.dirty_marks + 1
    )
    app._current_rows = lambda: []
    app._same_path = lambda a, b: str(a) == str(b)
    app.set_timer = lambda delay, fn: app.timer_calls.append((delay, fn))
    app._restore_table_position = lambda: app.__dict__.__setitem__(
        "_restore_called", True
    )
    app._capture_table_position = lambda: False

    class FakeQuery:
        def __init__(self) -> None:
            self.cursor_row = 0
            self.scroll_y = 0
            self.scroll_x = 0
            self.cursor_coordinate = (0, 0)

        def scroll_to(self, **kwargs: object) -> None:
            self.last_scroll = kwargs

    fake = FakeQuery()
    app._fake_query = fake

    def _query_one(_selector: str, _cls: object):
        if app.__dict__.get("_query_raises"):
            raise LookupError("missing")
        return fake

    app.query_one = _query_one
    app.call_after_refresh = lambda fn: app.timer_calls.append(("refresh", fn))

    for k, v in overrides.items():
        setattr(app, k, v)
    return app


def test_capture_table_position_returns_false_when_restore_pending() -> None:
    app = _make_app(_restore_pending={"active": True, "archive": False})
    assert view_state.capture_table_position(app, widget_projects="#tbl") is False


def test_capture_table_position_returns_false_when_apply_scroll_active() -> None:
    app = _make_app(_restore_apply_scroll={"active": True, "archive": False})
    assert view_state.capture_table_position(app, widget_projects="#tbl") is False


def test_capture_table_position_records_changes() -> None:
    app = _make_app(selected_path=Path("/p"))
    app._fake_query.cursor_row = 5
    app._fake_query.scroll_y = 2
    assert view_state.capture_table_position(app, widget_projects="#tbl") is True
    assert app._state_cursor_row == 5
    assert app._state_scroll_y == 2
    assert app._view_selected_path["active"] == Path("/p")


def test_capture_table_position_returns_unchanged_when_no_query() -> None:
    app = _make_app()
    app.__dict__["_query_raises"] = True
    assert view_state.capture_table_position(app, widget_projects="#tbl") is False


def test_retry_pending_restore_clears_when_attempts_exhausted() -> None:
    app = _make_app(
        _restore_retry_left=0,
        _restore_pending={"active": True, "archive": True},
    )
    view_state.retry_pending_restore(app)
    assert app._restore_pending == {"active": False, "archive": False}
    assert app.dirty_marks == 1


def test_retry_pending_restore_noops_when_fast_exit() -> None:
    app = _make_app(fast_exit_requested=True, _restore_retry_left=5,
                    _restore_pending={"active": True, "archive": False})
    view_state.retry_pending_restore(app)
    # No timer scheduled, no dirty mark
    assert app.timer_calls == []
    assert app.dirty_marks == 0


def test_retry_pending_restore_skips_when_no_pending() -> None:
    app = _make_app(_restore_retry_left=3,
                    _restore_pending={"active": False, "archive": False})
    view_state.retry_pending_restore(app)
    assert app.timer_calls == []


def test_retry_pending_restore_decrements_and_schedules() -> None:
    app = _make_app(_restore_retry_left=2,
                    _restore_pending={"active": True, "archive": False})
    app._retry_pending_restore = lambda: None
    view_state.retry_pending_restore(app)
    assert app._restore_retry_left == 1
    assert app.timer_calls and app.timer_calls[0][0] == pytest.approx(0.08)


def test_cancel_restore_for_current_view_resets_flags() -> None:
    app = _make_app(
        _restore_pending={"active": True, "archive": False},
        _restore_apply_scroll={"active": True, "archive": False},
        _restore_retry_left=5,
    )
    view_state.cancel_restore_for_current_view(app)
    assert app._restore_pending["active"] is False
    assert app._restore_apply_scroll["active"] is False
    assert app._restore_retry_left == 0


def test_apply_view_state_loads_per_view_state() -> None:
    app = _make_app(
        _view_selected_path={"active": Path("/a"), "archive": Path("/b")},
        _view_cursor_row={"active": 3, "archive": 7},
        _view_scroll_y={"active": 1, "archive": 2},
    )
    view_state.apply_view_state(app, "archive")
    assert app.selected_path == Path("/b")
    assert app._state_cursor_row == 7
    assert app._state_scroll_y == 2
    assert app._restore_pending["archive"] is True
    assert app._restore_apply_scroll["archive"] is True
    assert app._restore_retry_left == 32


def test_state_snapshot_includes_view_fields() -> None:
    app = _make_app(
        selected_path=Path("/proj"),
        _view_selected_path={"active": Path("/proj"), "archive": None},
        _view_cursor_row={"active": 4, "archive": 0},
        _view_scroll_y={"active": 2, "archive": 0},
        _view_row_offset={"active": 1, "archive": 0},
    )
    snap = view_state.state_snapshot(
        app,
        state_key_side_main="side_main",
        state_key_side_selected="side_selected",
        state_key_side_info="side_info",
        state_key_side_settings="side_settings",
        state_key_hotbar_selected_index="hotbar_idx",
    )
    assert snap["view"] == "active"
    assert snap["sort"] == "last"
    assert snap["selected_path"] == "/proj"
    assert snap["cursor_row_active"] == 4
    assert snap["scroll_y_active"] == 2
    assert snap["row_offset_active"] == 1
    assert snap["selected_path_archive"] == ""


def test_restore_table_position_does_nothing_without_query() -> None:
    app = _make_app()
    app.__dict__["_query_raises"] = True
    view_state.restore_table_position(app, widget_projects="#tbl")
    # No call_after_refresh scheduled
    assert app.timer_calls == []


def test_restore_table_position_does_nothing_with_no_rows() -> None:
    app = _make_app()
    view_state.restore_table_position(app, widget_projects="#tbl")
    assert app.timer_calls == []


def test_restore_table_position_selects_matching_row() -> None:
    row = SimpleNamespace(path=Path("/p"))
    app = _make_app(selected_path=Path("/p"))
    app._current_rows = lambda: [row]
    view_state.restore_table_position(app, widget_projects="#tbl")
    # Should not enqueue an after_refresh because restore_pending is False
    assert app._restore_apply_scroll["active"] is False
    assert app._fake_query.cursor_coordinate == (0, 0)


def test_restore_table_position_uses_state_cursor_row_when_unmatched() -> None:
    row = SimpleNamespace(path=Path("/other"))
    app = _make_app(selected_path=Path("/missing"))
    app._current_rows = lambda: [row, row]
    app._state_cursor_row = 1
    view_state.restore_table_position(app, widget_projects="#tbl")
    assert app.selected_path == Path("/other")
