"""Pilot tests for `RenameInputScreen`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.widgets import Input, Static

from homebase.ui.screens.rename import RenameInputScreen, _similar_matches


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


def test_similar_matches_returns_empty_for_very_short_query(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()
    assert _similar_matches(tmp_path, "a") == []


def test_similar_matches_skips_hidden_and_underscore(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "_archive").mkdir()
    out = _similar_matches(tmp_path, "demo")
    assert ("demo", 100) in out
    assert all(name != ".hidden" for name, _ in out)
    assert all(name != "_archive" for name, _ in out)


def test_similar_matches_excludes_current_name(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()
    out = _similar_matches(tmp_path, "demo", exclude="demo")
    assert all(name != "demo" for name, _ in out)


def test_similar_matches_ranks_prefix_and_substring(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alphabet").mkdir()
    (tmp_path / "zzz").mkdir()
    out = _similar_matches(tmp_path, "alph")
    names = [n for n, _ in out]
    # Both alpha+alphabet matched; zzz did not.
    assert "alpha" in names
    assert "alphabet" in names
    assert "zzz" not in names


async def test_rename_screen_enter_returns_typed_value(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()
    app = _Harness(
        lambda: RenameInputScreen(
            "Rename:", current_path=tmp_path / "demo", base_dir=tmp_path
        )
    )
    async with app.run_test() as pilot:
        # Initial value is "demo"; replace with "newname".
        await pilot.pause()
        inp = app.screen.query_one("#rename_input", Input)
        inp.value = "newname"
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.result == "newname"


async def test_rename_screen_escape_returns_none(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()
    app = _Harness(
        lambda: RenameInputScreen(
            "Rename:", current_path=tmp_path / "demo", base_dir=tmp_path
        )
    )
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert app.result is None


async def test_rename_screen_preview_marks_existing_target(
    tmp_path: Path,
) -> None:
    (tmp_path / "demo").mkdir()
    (tmp_path / "existing").mkdir()
    app = _Harness(
        lambda: RenameInputScreen(
            "Rename:", current_path=tmp_path / "demo", base_dir=tmp_path
        )
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        inp = app.screen.query_one("#rename_input", Input)
        inp.value = "existing"
        await pilot.pause()
        preview = app.screen.query_one("#rename_preview", Static)
        assert "target exists" in str(preview.render())


async def test_rename_screen_preview_unchanged_when_same_name(
    tmp_path: Path,
) -> None:
    (tmp_path / "demo").mkdir()
    app = _Harness(
        lambda: RenameInputScreen(
            "Rename:", current_path=tmp_path / "demo", base_dir=tmp_path
        )
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        preview = app.screen.query_one("#rename_preview", Static)
        assert "unchanged" in str(preview.render())


async def test_rename_screen_blank_input_shows_placeholder_hint(
    tmp_path: Path,
) -> None:
    (tmp_path / "demo").mkdir()
    app = _Harness(
        lambda: RenameInputScreen(
            "Rename:", current_path=tmp_path / "demo", base_dir=tmp_path
        )
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        inp = app.screen.query_one("#rename_input", Input)
        inp.value = ""
        await pilot.pause()
        preview = app.screen.query_one("#rename_preview", Static)
        assert "type a new name" in str(preview.render())
