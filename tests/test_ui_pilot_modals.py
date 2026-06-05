"""Pilot-based tests for the modal screens.

Each test boots a minimal harness App that pushes the modal under test
and stashes the dismiss value on the harness. See
https://textual.textualize.io/guide/testing/ for the Pilot API.
"""

from __future__ import annotations

from typing import Any

from textual.app import App, ComposeResult
from textual.widgets import Input, Static

from homebase.ui.screens.basic import (
    ConfirmScreen,
    InputScreen,
    ResultScreen,
    RuntimeErrorScreen,
)


class _Harness(App[None]):
    """Minimal harness: mounts a placeholder, then push_screen() the
    modal-under-test on_mount and stash the dismiss value."""

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


async def test_confirm_screen_yes_key_dismisses_true() -> None:
    app = _Harness(lambda: ConfirmScreen("Continue?", "details"))
    async with app.run_test() as pilot:
        await pilot.press("y")
        await pilot.pause()
        assert app.result is True


async def test_confirm_screen_no_key_dismisses_false() -> None:
    app = _Harness(lambda: ConfirmScreen("Continue?", ""))
    async with app.run_test() as pilot:
        await pilot.press("n")
        await pilot.pause()
        assert app.result is False


async def test_confirm_screen_enter_dismisses_true() -> None:
    app = _Harness(lambda: ConfirmScreen("Continue?"))
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await pilot.pause()
        assert app.result is True


async def test_confirm_screen_space_dismisses_true() -> None:
    app = _Harness(lambda: ConfirmScreen("Continue?"))
    async with app.run_test() as pilot:
        await pilot.press("space")
        await pilot.pause()
        assert app.result is True


async def test_confirm_screen_escape_dismisses_false() -> None:
    app = _Harness(lambda: ConfirmScreen("Continue?"))
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert app.result is False


async def test_input_screen_submit_returns_stripped_value() -> None:
    app = _Harness(lambda: InputScreen("Name:", placeholder="x"))
    async with app.run_test() as pilot:
        await pilot.press("h", "e", "l", "l", "o", "space", "space", "enter")
        await pilot.pause()
        assert app.result == "hello"


async def test_input_screen_escape_returns_none() -> None:
    app = _Harness(lambda: InputScreen("Name:", placeholder="x"))
    async with app.run_test() as pilot:
        await pilot.press("a", "b", "escape")
        await pilot.pause()
        assert app.result is None


async def test_input_screen_prefilled_value_is_focused() -> None:
    app = _Harness(lambda: InputScreen("Name:", placeholder="x", value="seed"))
    async with app.run_test() as pilot:
        await pilot.pause()
        # The input widget must exist and contain the prefilled value
        # while being focused (so the user can type immediately).
        inp = app.screen.query_one("#value_input", Input)
        assert inp.value == "seed"
        assert inp.has_focus


async def test_input_screen_side_info_is_rendered() -> None:
    app = _Harness(
        lambda: InputScreen("Name:", placeholder="x", side_info="explain things")
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        side = app.screen.query_one("#input_side_info", Static)
        assert "explain things" in str(side.render())


async def test_result_screen_enter_closes() -> None:
    app = _Harness(lambda: ResultScreen("Done", "ran ok", "long details"))
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await pilot.pause()
        assert app.result is None


async def test_result_screen_q_closes() -> None:
    app = _Harness(lambda: ResultScreen("Done", "", ""))
    async with app.run_test() as pilot:
        await pilot.press("q")
        await pilot.pause()
        assert app.result is None


async def test_result_screen_unknown_level_falls_back_to_info() -> None:
    app = _Harness(
        lambda: ResultScreen("Done", "ok", "", level="garbage")
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        # The screen survives an invalid level; renders title in green
        # (level coerced to "info").
        # No public attribute on level — check the constructor normalised it.
        screen = app.screen
        assert isinstance(screen, ResultScreen)
        assert screen.level == "info"


async def test_runtime_error_screen_escape_closes() -> None:
    app = _Harness(
        lambda: RuntimeErrorScreen("Boom", "saving", "stack trace details")
    )
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert app.result is None


async def test_runtime_error_screen_renders_context_and_details() -> None:
    app = _Harness(
        lambda: RuntimeErrorScreen("Boom", "saving foo", "trace lines")
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        ctx = app.screen.query_one("#runtime_error_context", Static)
        det = app.screen.query_one("#runtime_error_details", Static)
        assert "saving foo" in str(ctx.render())
        assert "trace lines" in str(det.render())
