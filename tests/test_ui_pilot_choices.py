"""Pilot tests for `SingleChoiceScreen` and `FuzzyChoiceScreen`."""

from __future__ import annotations

from typing import Any

from textual.app import App, ComposeResult
from textual.widgets import Static

from homebase.ui.screens.choices import FuzzyChoiceScreen, SingleChoiceScreen


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


# ---------- SingleChoiceScreen ----------


async def test_single_choice_enter_returns_first_option_key() -> None:
    options = [("a", "Apple"), ("b", "Banana")]
    app = _Harness(lambda: SingleChoiceScreen("Pick:", options))
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await pilot.pause()
        assert app.result == "a"


async def test_single_choice_down_then_enter_returns_second() -> None:
    options = [("a", "Apple"), ("b", "Banana")]
    app = _Harness(lambda: SingleChoiceScreen("Pick:", options))
    async with app.run_test() as pilot:
        await pilot.press("down", "enter")
        await pilot.pause()
        assert app.result == "b"


async def test_single_choice_up_wraps_to_last() -> None:
    options = [("a", "Apple"), ("b", "Banana"), ("c", "Cherry")]
    app = _Harness(lambda: SingleChoiceScreen("Pick:", options))
    async with app.run_test() as pilot:
        await pilot.press("up", "enter")
        await pilot.pause()
        assert app.result == "c"


async def test_single_choice_escape_returns_none() -> None:
    options = [("a", "Apple")]
    app = _Harness(lambda: SingleChoiceScreen("Pick:", options))
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert app.result is None


async def test_single_choice_empty_options_enter_returns_none() -> None:
    app = _Harness(lambda: SingleChoiceScreen("Pick:", []))
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await pilot.pause()
        assert app.result is None


async def test_single_choice_skips_headers_when_landing(
) -> None:
    options = [
        ("__hdr__fruits", "— Fruits —"),
        ("a", "Apple"),
        ("__hdr__veg", "— Veggies —"),
        ("c", "Carrot"),
    ]
    app = _Harness(lambda: SingleChoiceScreen("Pick:", options))
    async with app.run_test() as pilot:
        # Initial index lands on first non-header option (a).
        await pilot.press("enter")
        await pilot.pause()
        assert app.result == "a"


async def test_single_choice_down_skips_subsequent_header() -> None:
    options = [
        ("a", "Apple"),
        ("__hdr__veg", "— Veggies —"),
        ("c", "Carrot"),
    ]
    app = _Harness(lambda: SingleChoiceScreen("Pick:", options))
    async with app.run_test() as pilot:
        await pilot.press("down", "enter")
        await pilot.pause()
        assert app.result == "c"


async def test_single_choice_space_accepts_like_enter() -> None:
    options = [("a", "Apple"), ("b", "Banana")]
    app = _Harness(lambda: SingleChoiceScreen("Pick:", options))
    async with app.run_test() as pilot:
        await pilot.press("down", "space")
        await pilot.pause()
        assert app.result == "b"


# ---------- FuzzyChoiceScreen ----------


async def test_fuzzy_enter_returns_first_visible_when_unfiltered() -> None:
    options = [("a.py", "a.py"), ("b.md", "b.md")]
    app = _Harness(lambda: FuzzyChoiceScreen("Pick file:", options))
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await pilot.pause()
        assert app.result == "a.py"


async def test_fuzzy_typing_filters_options() -> None:
    options = [("alpha.py", "alpha.py"), ("beta.py", "beta.py")]
    app = _Harness(lambda: FuzzyChoiceScreen("Pick:", options))
    async with app.run_test() as pilot:
        # Type "beta" then accept — must land on beta.py
        await pilot.press("b", "e", "t", "a", "enter")
        await pilot.pause()
        assert app.result == "beta.py"


async def test_fuzzy_no_matches_accepts_to_none() -> None:
    options = [("alpha", "alpha")]
    app = _Harness(lambda: FuzzyChoiceScreen("Pick:", options))
    async with app.run_test() as pilot:
        await pilot.press("z", "z", "z", "z", "z", "z", "enter")
        await pilot.pause()
        assert app.result is None


async def test_fuzzy_ctrl_c_clears_filter() -> None:
    options = [("alpha", "alpha"), ("beta", "beta")]
    app = _Harness(lambda: FuzzyChoiceScreen("Pick:", options))
    async with app.run_test() as pilot:
        await pilot.press("a", "l")
        await pilot.pause()
        # Filter applied — visible should only have alpha.
        screen = app.screen
        assert isinstance(screen, FuzzyChoiceScreen)
        assert screen.filter_text == "al"
        # Clear filter, then accept — should land on the first option.
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert screen.filter_text == ""
        await pilot.press("enter")
        await pilot.pause()
        assert app.result == "alpha"


async def test_fuzzy_backspace_removes_one_char() -> None:
    options = [("alpha", "alpha"), ("beta", "beta")]
    app = _Harness(lambda: FuzzyChoiceScreen("Pick:", options))
    async with app.run_test() as pilot:
        await pilot.press("a", "l", "p")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, FuzzyChoiceScreen)
        assert screen.filter_text == "alp"
        await pilot.press("backspace")
        await pilot.pause()
        assert screen.filter_text == "al"


async def test_fuzzy_escape_returns_none() -> None:
    options = [("alpha", "alpha")]
    app = _Harness(lambda: FuzzyChoiceScreen("Pick:", options))
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert app.result is None


async def test_fuzzy_down_then_enter_selects_second_visible() -> None:
    options = [("alpha", "alpha"), ("beta", "beta"), ("gamma", "gamma")]
    app = _Harness(lambda: FuzzyChoiceScreen("Pick:", options))
    async with app.run_test() as pilot:
        await pilot.press("down", "enter")
        await pilot.pause()
        assert app.result == "beta"
