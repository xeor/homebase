from __future__ import annotations

from pathlib import Path

import pytest

from homebase.ui import new_project_app
from homebase.ui.new_project_app import NewProjectApp
from homebase.ui.screens.new_project import NewProjectScreen


@pytest.mark.asyncio
async def test_starts_on_the_popup_and_cancel_quits(tmp_path: Path) -> None:
    app = NewProjectApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, NewProjectScreen)
        assert screen.allow_stay_in_b is False
        screen.dismiss(None)
        await pilot.pause()
    assert app.return_value == ("quit", None, [])
    assert app.messages == [("warn", "new project cancelled")]


@pytest.mark.asyncio
async def test_submit_creates_and_returns_open(tmp_path: Path) -> None:
    app = NewProjectApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.dismiss(
            {
                "input": "fresh",
                "source": "empty",
                "tags": [],
                "template": "",
                "after_create": "open",
            }
        )
        await pilot.pause()
    action, path, _post = app.return_value or ("", None, [])
    assert action == "open"
    assert path is not None and path.name == "fresh" and path.is_dir()
    assert app.last_new_summary


def test_runtime_error_is_kept_for_printing(tmp_path: Path) -> None:
    app = NewProjectApp(tmp_path)
    app._show_runtime_error("new project", ValueError("bad source"))
    assert app.runtime_errors == ["new project: ValueError: bad source"]
    app._busy_start("creating project")
    assert app._busy_depth == 1
    app._busy_stop()
    app._busy_stop()
    assert app._busy_depth == 0


def test_run_prints_errors_after_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(self: NewProjectApp) -> None:
        self.runtime_errors.append("new project config: boom")
        self.last_new_error = "plan failed"

    monkeypatch.setattr(NewProjectApp, "run", fake_run)
    result = new_project_app.run_new_project_ui(tmp_path, tmp_path)
    assert result == ("quit", None, [])
    err = capsys.readouterr().err
    assert "new project config: boom" in err
    assert "b new failed:\nplan failed" in err
