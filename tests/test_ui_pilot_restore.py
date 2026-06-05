"""Pilot tests for `RestorePathScreen`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.widgets import Input, Static

from homebase.ui.screens.restore import RestorePathScreen


class _Harness(App[None]):
    def __init__(self, factory: Any) -> None:
        super().__init__()
        self._factory = factory
        self.result: Any = "__unset__"

    def compose(self) -> ComposeResult:
        yield Static("harness")

    async def on_mount(self) -> None:
        def _on_dismiss(value: Any) -> None:
            self.result = value

        self.push_screen(self._factory(), _on_dismiss)


async def test_restore_screen_default_target_status_ok(tmp_path: Path) -> None:
    target = tmp_path / "restored"
    app = _Harness(
        lambda: RestorePathScreen(default_target=target, base_dir_ref=tmp_path)
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        status = app.screen.query_one("#restore_status", Static)
        assert "ok" in str(status.render())


async def test_restore_screen_enter_dismisses_valid_target(tmp_path: Path) -> None:
    target = tmp_path / "restored"
    app = _Harness(
        lambda: RestorePathScreen(default_target=target, base_dir_ref=tmp_path)
    )
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.result, Path)
        assert app.result.name == "restored"


async def test_restore_screen_escape_returns_none(tmp_path: Path) -> None:
    target = tmp_path / "restored"
    app = _Harness(
        lambda: RestorePathScreen(default_target=target, base_dir_ref=tmp_path)
    )
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert app.result is None


async def test_restore_screen_existing_target_blocks_dismiss(
    tmp_path: Path,
) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    app = _Harness(
        lambda: RestorePathScreen(default_target=target, base_dir_ref=tmp_path)
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        status = app.screen.query_one("#restore_status", Static)
        assert "exists" in str(status.render())
        # Try to accept; the screen rejects the input — result stays unset.
        await pilot.press("enter")
        await pilot.pause()
        assert app.result == "__unset__"


async def test_restore_screen_empty_input_marks_error(tmp_path: Path) -> None:
    target = tmp_path / "restored"
    app = _Harness(
        lambda: RestorePathScreen(default_target=target, base_dir_ref=tmp_path)
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        inp = app.screen.query_one("#restore_input", Input)
        inp.value = ""
        await pilot.pause()
        status = app.screen.query_one("#restore_status", Static)
        assert "empty" in str(status.render())


async def test_restore_screen_parent_will_be_created_marker(
    tmp_path: Path,
) -> None:
    target = tmp_path / "nested" / "deep" / "restored"
    app = _Harness(
        lambda: RestorePathScreen(default_target=target, base_dir_ref=tmp_path)
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        status = app.screen.query_one("#restore_status", Static)
        assert "parent will be created" in str(status.render())
