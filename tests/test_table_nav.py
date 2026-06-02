from __future__ import annotations

from types import SimpleNamespace

from homebase.ui.table import nav


class FakeTable:
    def __init__(self, has_focus: bool = True) -> None:
        self.scroll_x = 0
        self.scroll_y = 0
        self.has_focus = has_focus
        self.scrolls: list[dict[str, object]] = []
        self.relative: list[tuple[int, int]] = []

    def scroll_to(self, **kw: object) -> None:
        self.scrolls.append(kw)

    def scroll_relative(self, **kw: object) -> None:
        self.relative.append((int(kw["x"]), int(kw["y"])))


class FakeInput:
    def __init__(self, ident: str = "filter_query") -> None:
        self.id = ident
        self.left_calls = 0
        self.right_calls = 0
        self.home_calls = 0
        self.end_calls = 0

    def action_cursor_left(self, _select: bool) -> None:
        self.left_calls += 1

    def action_cursor_right(self, _select: bool) -> None:
        self.right_calls += 1

    def action_home(self, _select: bool) -> None:
        self.home_calls += 1

    def action_end(self, _select: bool) -> None:
        self.end_calls += 1


def _make_app(table: FakeTable | None = None, **overrides: object) -> SimpleNamespace:
    table = table if table is not None else FakeTable()
    app = SimpleNamespace(
        query="",
        query_cursor=0,
        focused=None,
        side_main_tab="selected",
        side_settings_tab="table",
        side_refreshes=0,
        scroll_calls=[],
        reorder_calls=[],
    )

    def query_one(_sel: str, _cls: type):
        if app.__dict__.get("_raise"):
            raise LookupError("missing")
        return table

    app.query_one = query_one
    app._refresh_side = lambda: app.__dict__.__setitem__(
        "side_refreshes", app.side_refreshes + 1
    )
    app._scroll_table_x = lambda delta: app.scroll_calls.append(delta)
    app._table_is_active_focus = lambda: True
    app._table_settings_reorder = lambda d: app.reorder_calls.append(d)
    for k, v in overrides.items():
        setattr(app, k, v)
    return app, table


def test_scroll_table_x_uses_scroll_to_when_available() -> None:
    app, table = _make_app()
    nav.scroll_table_x(app, 5, widget_projects="#tbl")
    assert table.scrolls
    assert table.scrolls[0]["x"] == 5
    assert table.scrolls[0]["animate"] is False


def test_scroll_table_x_falls_back_to_scroll_relative() -> None:
    class BrokenTable(FakeTable):
        def scroll_to(self, **_kw):
            raise RuntimeError("nope")

    table = BrokenTable()
    app, _ = _make_app(table=table)
    nav.scroll_table_x(app, -3, widget_projects="#tbl")
    assert table.relative == [(-3, 0)]


def test_table_is_active_focus_returns_false_when_input_focused(monkeypatch) -> None:
    app, table = _make_app()
    monkeypatch.setattr(nav, "Input", FakeInput)
    app.focused = FakeInput("filter_query")
    assert nav.table_is_active_focus(app, widget_projects="#tbl") is False


def test_table_is_active_focus_returns_false_when_query_lookup_fails() -> None:
    app, _ = _make_app()
    app.__dict__["_raise"] = True
    assert nav.table_is_active_focus(app, widget_projects="#tbl") is False


def test_table_is_active_focus_returns_focus_flag() -> None:
    table = FakeTable(has_focus=True)
    app, _ = _make_app(table=table)
    assert nav.table_is_active_focus(app, widget_projects="#tbl") is True


def test_action_query_left_decrements_cursor_when_focused() -> None:
    app, _ = _make_app()
    app.query = "abc"
    app.query_cursor = 2
    nav.action_query_left(app)
    assert app.query_cursor == 1


def test_action_query_left_noop_when_not_active() -> None:
    app, _ = _make_app()
    app._table_is_active_focus = lambda: False
    app.query_cursor = 5
    nav.action_query_left(app)
    assert app.query_cursor == 5


def test_action_query_right_caps_at_query_length() -> None:
    app, _ = _make_app()
    app.query = "ab"
    app.query_cursor = 2
    nav.action_query_right(app)
    assert app.query_cursor == 2


def test_action_query_home_and_end() -> None:
    app, _ = _make_app()
    app.query = "hello"
    app.query_cursor = 3
    nav.action_query_home(app)
    assert app.query_cursor == 0
    nav.action_query_end(app)
    assert app.query_cursor == 5


def test_action_table_scroll_helpers() -> None:
    app, _ = _make_app()
    nav.action_table_scroll_left(app)
    nav.action_table_scroll_right(app)
    assert app.scroll_calls == [-12, 12]


def test_action_route_left_in_table_settings_calls_reorder() -> None:
    app, _ = _make_app()
    app.side_main_tab = "settings"
    app.side_settings_tab = "table"
    nav.action_route_left(app)
    assert app.reorder_calls == [-1]


def test_action_route_left_input_focused_uses_input_handler(monkeypatch) -> None:
    inp = FakeInput()
    monkeypatch.setattr(nav, "Input", FakeInput)
    app, _ = _make_app()
    app.side_main_tab = "selected"
    app.focused = inp
    nav.action_route_left(app)
    assert inp.left_calls == 1


def test_action_route_left_falls_back_to_query_cursor() -> None:
    app, _ = _make_app()
    app.side_main_tab = "selected"
    app.query = "abc"
    app.query_cursor = 2
    nav.action_route_left(app)
    assert app.query_cursor == 1


def test_action_route_right_in_table_settings_calls_reorder() -> None:
    app, _ = _make_app()
    app.side_main_tab = "settings"
    app.side_settings_tab = "table"
    nav.action_route_right(app)
    assert app.reorder_calls == [1]


def test_action_route_right_input_focused(monkeypatch) -> None:
    inp = FakeInput()
    monkeypatch.setattr(nav, "Input", FakeInput)
    app, _ = _make_app()
    app.focused = inp
    nav.action_route_right(app)
    assert inp.right_calls == 1


def test_action_route_home_and_end_use_input_handlers(monkeypatch) -> None:
    inp = FakeInput()
    monkeypatch.setattr(nav, "Input", FakeInput)
    app, _ = _make_app()
    app.focused = inp
    nav.action_route_home(app)
    nav.action_route_end(app)
    assert inp.home_calls == 1
    assert inp.end_calls == 1


def test_action_route_home_falls_back_to_query_cursor_zero() -> None:
    app, _ = _make_app()
    app.query_cursor = 5
    nav.action_route_home(app)
    assert app.query_cursor == 0


def test_action_route_end_falls_back_to_query_cursor_end() -> None:
    app, _ = _make_app()
    app.query = "abc"
    app.query_cursor = 0
    nav.action_route_end(app)
    assert app.query_cursor == 3


def test_action_route_helpers_noop_when_not_table_active() -> None:
    app, _ = _make_app()
    app.side_main_tab = "selected"
    app._table_is_active_focus = lambda: False
    app.query = "abc"
    app.query_cursor = 1
    nav.action_route_left(app)
    nav.action_route_right(app)
    nav.action_route_home(app)
    nav.action_route_end(app)
    assert app.query_cursor == 1
