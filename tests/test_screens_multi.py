"""Tests for ``ui/screens/multi.MultiChoiceScreen`` — the actions and
``_refresh_body`` helpers. The Textual mount lifecycle is bypassed
with ``__new__`` and stubbed ``query_one`` / ``dismiss``."""
from __future__ import annotations

from homebase.ui.screens.multi import MultiChoiceScreen


class _StaticStub:
    def __init__(self) -> None:
        self.text = ""

    def update(self, text: str) -> None:
        self.text = text


def _make_screen(
    options: list[tuple[str, str]],
    selected: set[str] | None = None,
    *,
    index: int = 0,
):
    # ``title`` is a Textual reactive — bypass its setter by writing
    # straight into ``__dict__`` so we don't need to mount the screen.
    screen = MultiChoiceScreen.__new__(MultiChoiceScreen)
    screen.__dict__["title"] = "Pick"
    screen.options = options
    screen.index = index
    screen.list_scroll_offset = 0
    screen.selected = set(selected or set())
    screen._dismissed: list[set[str] | None] = []
    screen.dismiss = screen._dismissed.append  # type: ignore[method-assign]
    return screen


# ---- navigation -----------------------------------------------------


def test_move_up_noop_on_empty_options() -> None:
    """No options → no cursor → arrows must not crash or wrap."""
    screen = _make_screen([])
    screen.action_move_up()
    screen.action_move_down()
    assert screen.index == 0


def test_move_down_advances_cursor(monkeypatch) -> None:
    screen = _make_screen([("a", "A"), ("b", "B"), ("c", "C")])
    monkeypatch.setattr(screen, "_refresh_body", lambda: None)
    screen.action_move_down()
    assert screen.index == 1
    screen.action_move_down()
    assert screen.index == 2


def test_move_down_wraps(monkeypatch) -> None:
    screen = _make_screen([("a", "A"), ("b", "B")], index=1)
    monkeypatch.setattr(screen, "_refresh_body", lambda: None)
    screen.action_move_down()
    assert screen.index == 0


def test_move_up_wraps_backwards(monkeypatch) -> None:
    screen = _make_screen([("a", "A"), ("b", "B")], index=0)
    monkeypatch.setattr(screen, "_refresh_body", lambda: None)
    screen.action_move_up()
    assert screen.index == 1


# ---- toggle ---------------------------------------------------------


def test_toggle_adds_unselected_key(monkeypatch) -> None:
    screen = _make_screen([("a", "A"), ("b", "B")])
    monkeypatch.setattr(screen, "_refresh_body", lambda: None)
    screen.action_toggle()
    assert screen.selected == {"a"}


def test_toggle_removes_already_selected_key(monkeypatch) -> None:
    screen = _make_screen([("a", "A"), ("b", "B")], selected={"a"})
    monkeypatch.setattr(screen, "_refresh_body", lambda: None)
    screen.action_toggle()
    assert screen.selected == set()


def test_toggle_noop_on_empty_options() -> None:
    screen = _make_screen([])
    screen.action_toggle()
    assert screen.selected == set()


# ---- accept / cancel ------------------------------------------------


def test_accept_dismisses_with_selected_copy(monkeypatch) -> None:
    screen = _make_screen([("a", "A")], selected={"a"})
    screen.action_accept()
    assert screen._dismissed == [{"a"}]
    # The dismissed set is a copy — mutating ``selected`` later must
    # not change what the caller received.
    screen.selected.add("b")
    assert screen._dismissed[0] == {"a"}


def test_cancel_dismisses_with_none() -> None:
    screen = _make_screen([("a", "A")], selected={"a"})
    screen.action_cancel()
    assert screen._dismissed == [None]


# ---- _refresh_body --------------------------------------------------


class _BodyStub(_StaticStub):
    # ``compute_window`` reads ``size`` to figure out the visible row
    # count; expose a tiny stub with the attribute it needs.
    class _Size:
        height = 5
        width = 80
    size = _Size()


def test_refresh_body_renders_each_option_with_marker(monkeypatch) -> None:
    screen = _make_screen(
        [("a", "alpha"), ("b", "beta"), ("c", "gamma")], selected={"b"},
    )
    body = _BodyStub()
    monkeypatch.setattr(screen, "query_one", lambda *_a, **_kw: body)
    screen._refresh_body()
    assert "alpha" in body.text
    assert "beta" in body.text
    # The selected entry has ``[x]`` rather than ``[ ]``.
    beta_line = next(line for line in body.text.splitlines() if "beta" in line)
    assert "[x]" in beta_line


def test_refresh_body_marks_cursor_row(monkeypatch) -> None:
    screen = _make_screen(
        [("a", "alpha"), ("b", "beta")], index=1,
    )
    body = _BodyStub()
    monkeypatch.setattr(screen, "query_one", lambda *_a, **_kw: body)
    screen._refresh_body()
    beta_line = next(line for line in body.text.splitlines() if "beta" in line)
    alpha_line = next(line for line in body.text.splitlines() if "alpha" in line)
    assert beta_line.startswith(">")
    assert alpha_line.startswith(" ")
