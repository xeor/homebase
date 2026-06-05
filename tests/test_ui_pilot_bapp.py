"""Pilot-based smoke tests for the main BApp.

These boot the real Textual app against a tmp_path "base" and verify
that initial mount, table population from a seeded project, and the
quit binding all work end-to-end through the Pilot harness.
"""

from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

from homebase.core.constants import BASE_MARKER_FILE
from homebase.ui.app import BApp
from homebase.ui.context import UIContext


def _empty_ctx(base: Path) -> UIContext:
    return UIContext(
        base_dir=base,
        archive_tz=ZoneInfo("UTC"),
        archive_tz_name="UTC",
        reconcile_config={
            "active": {"enabled": False, "interval_s": 60.0},
            "archive": {"enabled": False, "interval_s": 60.0},
        },
    )


def _seed_project(base: Path, name: str) -> Path:
    project = base / name
    project.mkdir(parents=True)
    (project / BASE_MARKER_FILE).write_text("")
    return project


async def test_bapp_boots_with_empty_base(tmp_path: Path) -> None:
    app = BApp(tmp_path, ctx=_empty_ctx(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        # No projects → row count is zero, but the app is alive.
        assert app.active_rows == []
        assert app.archived_rows == []


async def test_bapp_lists_seeded_project_in_active_rows(tmp_path: Path) -> None:
    _seed_project(tmp_path, "demo")
    app = BApp(tmp_path, ctx=_empty_ctx(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        names = sorted(r.name for r in app.active_rows)
        assert "demo" in names


async def test_bapp_ctrl_q_exits_cleanly(tmp_path: Path) -> None:
    app = BApp(tmp_path, ctx=_empty_ctx(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+q")
        await pilot.pause()
    # run_test exits via context manager; returning here means the app
    # honored quit and shut down.
    assert app.fast_exit_requested is True


async def test_bapp_initial_filter_text_propagates_to_query_state(
    tmp_path: Path,
) -> None:
    from homebase.ui.table.rows_view import current_rows

    _seed_project(tmp_path, "alpha")
    _seed_project(tmp_path, "beta")
    app = BApp(tmp_path, ctx=_empty_ctx(tmp_path), initial_filter="alpha")
    async with app.run_test() as pilot:
        await pilot.pause()
        # The constructor stores the seed filter in `self.query`
        # (which shadows the App.query CSS selector method).
        assert "alpha" in str(app.query)
        names = {r.name for r in current_rows(app, mode_active="active")}
        assert names == {"alpha"}


async def test_bapp_two_projects_visible_in_current_rows(tmp_path: Path) -> None:
    from homebase.ui.table.rows_view import current_rows

    _seed_project(tmp_path, "one")
    _seed_project(tmp_path, "two")
    app = BApp(tmp_path, ctx=_empty_ctx(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        names = sorted(r.name for r in current_rows(app, mode_active="active"))
        assert names == ["one", "two"]


async def test_bapp_ctrl_d_toggles_view_mode(tmp_path: Path) -> None:
    _seed_project(tmp_path, "demo")
    app = BApp(tmp_path, ctx=_empty_ctx(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        initial = app.view_mode
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert app.view_mode != initial
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert app.view_mode == initial


async def test_bapp_initial_filter_unmatched_yields_empty_view(
    tmp_path: Path,
) -> None:
    from homebase.ui.table.rows_view import current_rows

    _seed_project(tmp_path, "alpha")
    _seed_project(tmp_path, "beta")
    app = BApp(tmp_path, ctx=_empty_ctx(tmp_path), initial_filter="zzz-never-matches")
    async with app.run_test() as pilot:
        await pilot.pause()
        rows = list(current_rows(app, mode_active="active"))
        assert rows == []
