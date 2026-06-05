"""Pilot tests for ``ui/screens/actions.ActionPickerScreen``.

Currently the screen sits around 14.8% line coverage — most of it is
key-driven UI logic that only exercises under a real Textual harness.
"""

from __future__ import annotations

from typing import Any

from textual.app import App, ComposeResult
from textual.widgets import Static

from homebase.ui.screens.actions import ActionPickerScreen


class _Harness(App[None]):
    def __init__(self, screen_factory: Any) -> None:
        super().__init__()
        self._screen_factory = screen_factory
        self.result: Any = "__unset__"

    def compose(self) -> ComposeResult:
        yield Static("harness")

    async def on_mount(self) -> None:
        def _on_dismiss(value: Any) -> None:
            self.result = value

        self.push_screen(self._screen_factory(), _on_dismiss)


_TABS = [
    (
        "builtin",
        "Built-in",
        [
            ("archive", "archive"),
            ("delete", "delete"),
            ("new_worktree", "new worktree"),
        ],
    ),
    (
        "custom",
        "Custom",
        [
            ("build", "build"),
            ("lint", "lint"),
        ],
    ),
]


async def test_picker_enter_returns_first_action_in_default_tab() -> None:
    app = _Harness(lambda: ActionPickerScreen(_TABS))
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await pilot.pause()
        assert app.result == "archive"


async def test_picker_down_then_enter_picks_second() -> None:
    app = _Harness(lambda: ActionPickerScreen(_TABS))
    async with app.run_test() as pilot:
        await pilot.press("down", "enter")
        await pilot.pause()
        assert app.result == "delete"


async def test_picker_up_wraps_to_last_in_tab() -> None:
    app = _Harness(lambda: ActionPickerScreen(_TABS))
    async with app.run_test() as pilot:
        await pilot.press("up", "enter")
        await pilot.pause()
        assert app.result == "new_worktree"


async def test_picker_next_tab_switches_to_custom() -> None:
    """Right-arrow moves to the next tab and the cursor resets to 0."""
    app = _Harness(lambda: ActionPickerScreen(_TABS))
    async with app.run_test() as pilot:
        await pilot.press("right", "enter")
        await pilot.pause()
        assert app.result == "build"


async def test_picker_prev_tab_wraps_to_last() -> None:
    app = _Harness(lambda: ActionPickerScreen(_TABS))
    async with app.run_test() as pilot:
        await pilot.press("left", "enter")
        await pilot.pause()
        # Wrapped from "builtin" to "custom".
        assert app.result == "build"


async def test_picker_default_tab_arg_records_initial_tab() -> None:
    """The ``default_tab`` kwarg primes ``active_tab`` even before
    Tabs raises its first activation event."""
    screen = ActionPickerScreen(_TABS, default_tab="custom")
    assert screen.active_tab == "custom"


async def test_picker_default_tab_falls_back_to_first_when_unknown() -> None:
    screen = ActionPickerScreen(_TABS, default_tab="nope")
    assert screen.active_tab == "builtin"


async def test_picker_no_tabs_leaves_active_blank() -> None:
    screen = ActionPickerScreen([])
    assert screen.active_tab == ""


async def test_picker_typing_filters_actions() -> None:
    """Typing ``arc`` should keep ``archive`` visible and dismiss returns it."""
    app = _Harness(lambda: ActionPickerScreen(_TABS))
    async with app.run_test() as pilot:
        await pilot.press("a", "r", "c", "enter")
        await pilot.pause()
        assert app.result == "archive"


async def test_picker_filter_no_match_dismisses_none() -> None:
    app = _Harness(lambda: ActionPickerScreen(_TABS))
    async with app.run_test() as pilot:
        await pilot.press("z", "z", "z", "z", "z", "z", "enter")
        await pilot.pause()
        assert app.result is None


async def test_picker_backspace_clears_one_char_of_filter() -> None:
    app = _Harness(lambda: ActionPickerScreen(_TABS))
    async with app.run_test() as pilot:
        await pilot.press("a", "r", "c")
        await pilot.pause()
        scr = app.screen
        assert isinstance(scr, ActionPickerScreen)
        assert scr.filter_text == "arc"
        await pilot.press("backspace")
        await pilot.pause()
        assert scr.filter_text == "ar"


async def test_picker_ctrl_c_clears_filter_text() -> None:
    app = _Harness(lambda: ActionPickerScreen(_TABS))
    async with app.run_test() as pilot:
        await pilot.press("a", "r")
        await pilot.pause()
        scr = app.screen
        assert isinstance(scr, ActionPickerScreen)
        assert scr.filter_text == "ar"
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert scr.filter_text == ""


async def test_picker_escape_dismisses_none() -> None:
    app = _Harness(lambda: ActionPickerScreen(_TABS))
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert app.result is None


async def test_picker_empty_tabs_returns_none() -> None:
    app = _Harness(lambda: ActionPickerScreen([("solo", "Solo", [])]))
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await pilot.pause()
        assert app.result is None
