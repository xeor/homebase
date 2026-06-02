"""Tests for ``ui/query/workspace_guard.py`` — the startup helpers
that detect filesystem drift from the cached row set."""
from __future__ import annotations

from pathlib import Path

from homebase.core.models import ProjectRow
from homebase.ui.query import workspace_guard as wg


def _row(name: str, path: Path) -> ProjectRow:
    return ProjectRow(
        path=path,
        name=name,
        branch="-",
        dirty="",
        last="",
        src="fs",
        created="",
        tags=[],
        properties=[],
        description="",
        created_ts=0,
        last_ts=0,
        git_ts=0,
        opened_ts=0,
        is_fork=False,
        is_tmp=False,
        archived=False,
        packed=False,
        pack_format=None,
        restore_target=None,
        archived_ts=0,
        wip=False,
        suffix=None,
        size_bytes=0,
        size_refresh_count=0,
        worktree_of="",
        repo_dir="",
    )


# ---- cached_top_active_names ----------------------------------------


def test_cached_top_active_names_returns_only_top_level(tmp_path: Path) -> None:
    base = tmp_path
    top = base / "alpha"
    top.mkdir()
    nested = base / "container" / "child"
    nested.mkdir(parents=True)
    rows = [_row("alpha", top), _row("child", nested)]
    out = wg.cached_top_active_names(base_dir=base, active_rows=rows)
    assert out == {"alpha"}


def test_cached_top_active_names_empty_when_no_top_level(tmp_path: Path) -> None:
    nested = tmp_path / "container" / "leaf"
    nested.mkdir(parents=True)
    rows = [_row("leaf", nested)]
    assert wg.cached_top_active_names(base_dir=tmp_path, active_rows=rows) == set()


def test_cached_top_active_names_swallows_oserror(tmp_path: Path) -> None:
    """A row whose path can't be resolved (deleted, broken symlink…)
    is silently skipped — the helper must never propagate I/O errors
    out of a guard."""
    class _BrokenPath:
        @property
        def parent(self):
            raise OSError("ghost")

    fake_row = ProjectRow.__new__(ProjectRow)
    fake_row.__dict__.update({
        "path": _BrokenPath(),
        "name": "ghost",
    })
    rows = [fake_row]  # type: ignore[list-item]
    assert wg.cached_top_active_names(base_dir=tmp_path, active_rows=rows) == set()


def test_cached_top_active_names_empty_with_no_rows(tmp_path: Path) -> None:
    assert wg.cached_top_active_names(base_dir=tmp_path, active_rows=[]) == set()


# ---- quick_active_dir_names -----------------------------------------


def test_quick_active_dir_names_lists_visible_top_level(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    out = wg.quick_active_dir_names(base_dir=tmp_path)
    assert out == {"alpha", "beta"}


def test_quick_active_dir_names_skips_dot_and_underscore_dirs(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "_archive").mkdir()
    (tmp_path / "_tags").mkdir()
    out = wg.quick_active_dir_names(base_dir=tmp_path)
    assert out == {"alpha"}


def test_quick_active_dir_names_skips_files(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "afile.txt").write_text("x")
    out = wg.quick_active_dir_names(base_dir=tmp_path)
    assert out == {"alpha"}


def test_quick_active_dir_names_empty_when_base_missing(tmp_path: Path) -> None:
    assert wg.quick_active_dir_names(base_dir=tmp_path / "missing") == set()


# ---- startup_quick_active_dir_check ---------------------------------


class _GuardApp:
    def __init__(
        self,
        *,
        live: set[str],
        cached: set[str],
        fast_exit: bool = False,
    ) -> None:
        self.fast_exit_requested = fast_exit
        self._live = live
        self._cached = cached
        self.logs: list[tuple[str, str]] = []
        self.cache_refreshes: list[tuple[str, bool]] = []

    def _quick_active_dir_names(self) -> set[str]:
        return self._live

    def _cached_top_active_names(self) -> set[str]:
        return self._cached

    def _log(self, msg: str, level: str) -> None:
        self.logs.append((msg, level))

    def _start_cache_refresh(self, reason: str, force: bool = False) -> None:
        self.cache_refreshes.append((reason, force))


def test_startup_quick_check_skips_when_fast_exit() -> None:
    app = _GuardApp(live={"a"}, cached={"b"}, fast_exit=True)
    wg.startup_quick_active_dir_check(app, level_info="info")
    assert app.cache_refreshes == []
    assert app.logs == []


def test_startup_quick_check_skips_when_live_empty() -> None:
    """An empty base dir at startup is treated as "nothing to do" —
    don't pre-emptively refresh the cache, the user might just be in
    a brand-new workspace."""
    app = _GuardApp(live=set(), cached={"a", "b"})
    wg.startup_quick_active_dir_check(app, level_info="info")
    assert app.cache_refreshes == []


def test_startup_quick_check_skips_when_sets_match() -> None:
    app = _GuardApp(live={"a", "b"}, cached={"a", "b"})
    wg.startup_quick_active_dir_check(app, level_info="info")
    assert app.cache_refreshes == []
    assert app.logs == []


def test_startup_quick_check_triggers_refresh_on_addition() -> None:
    app = _GuardApp(live={"a", "b"}, cached={"a"})
    wg.startup_quick_active_dir_check(app, level_info="info")
    assert app.cache_refreshes == [("startup top-level dir delta", True)]
    assert app.logs and "delta +1 -0" in app.logs[0][0]


def test_startup_quick_check_triggers_refresh_on_removal() -> None:
    app = _GuardApp(live={"a"}, cached={"a", "b"})
    wg.startup_quick_active_dir_check(app, level_info="info")
    assert app.cache_refreshes == [("startup top-level dir delta", True)]
    assert app.logs and "delta +0 -1" in app.logs[0][0]


def test_startup_quick_check_uses_level_info_string() -> None:
    app = _GuardApp(live={"a"}, cached=set())
    wg.startup_quick_active_dir_check(app, level_info="warn")
    assert app.logs and app.logs[0][1] == "warn"
