from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from homebase.cache.api import (
    cache_load_worktree_health,
    cache_save_worktree_health,
)
from homebase.cli.parser import build_cli_parser
from homebase.ui.sync.worktree_health import (
    dismiss_worktree_health,
    load_initial_health,
    on_worktree_health_refresh_done,
)
from homebase.workspace.new import cmd_new


def _run_new(base: Path, cwd: Path, args: list[str]) -> int:
    ns = build_cli_parser().parse_args(["new", *args, "--no-open"])
    return cmd_new(ns, base, cwd)


def _init_project_repo(base: Path, name: str) -> Path:
    project = base / name
    repo = project / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)
    (repo / "f.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    (project / ".base.yaml").write_text("tags: []\n", encoding="utf-8")
    return project


class _Banner:
    def __init__(self) -> None:
        self.text = ""
        self.classes: set[str] = set()

    def update(self, text: str) -> None:
        self.text = text

    def add_class(self, name: str) -> None:
        self.classes.add(name)

    def remove_class(self, name: str) -> None:
        self.classes.discard(name)


def _make_app(tmp_path: Path) -> SimpleNamespace:
    banner = _Banner()
    app = SimpleNamespace(
        base_dir=tmp_path,
        fast_exit_requested=False,
        worktree_health_issues=[],
        worktree_health_last_scan_ts=0,
        worktree_health_refresh_running=False,
        worktree_health_refresh_last_ts=0.0,
        worktree_health_dismissed=False,
        logs=[],
        _log=lambda msg, level="info": None,
        _banner=banner,
    )

    def _query_one(selector: str, _typ):
        if selector == "#worktree_health_banner":
            return banner
        raise LookupError(selector)

    app.query_one = _query_one
    return app


def _capture_logs(app: SimpleNamespace) -> None:
    def _log(msg: str, level: str = "info") -> None:
        app.logs.append((level, msg))

    app._log = _log


def test_cache_round_trip_persists_issues(tmp_path: Path) -> None:
    assert cache_load_worktree_health(tmp_path) is None
    payload = [
        {
            "kind": "stale_gitdir",
            "path": str(tmp_path / "foo-featx"),
            "detail": "pointer drifted",
            "fix_summary": "git worktree repair",
            "parent_path": str(tmp_path / "foo" / "repo"),
        }
    ]
    cache_save_worktree_health(tmp_path, 1234, payload)

    cached = cache_load_worktree_health(tmp_path)
    assert cached is not None
    scan_at, issues = cached
    assert scan_at == 1234
    assert issues == payload


def test_load_initial_health_announces_cached_issues(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    _capture_logs(app)
    cache_save_worktree_health(
        tmp_path,
        42,
        [
            {
                "kind": "stale_gitdir",
                "path": "/tmp/foo-featx",
                "detail": "x",
                "fix_summary": "y",
                "parent_path": "/tmp/foo/repo",
            }
        ],
    )

    load_initial_health(app)
    assert app.worktree_health_last_scan_ts == 42
    assert len(app.worktree_health_issues) == 1
    assert any("worktree health" in msg for _lvl, msg in app.logs)


def test_load_initial_health_silent_when_dismissed(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    _capture_logs(app)
    cache_save_worktree_health(
        tmp_path,
        42,
        [{"kind": "stale_gitdir", "path": "/x", "detail": "d", "fix_summary": "f", "parent_path": ""}],
    )
    dismiss_worktree_health(app)

    load_initial_health(app)
    assert app.logs == []
    assert app.worktree_health_issues != []


def test_on_refresh_done_logs_only_on_state_change(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    _capture_logs(app)
    app.worktree_health_issues = []

    issues = [{"kind": "stale_gitdir", "path": "/p", "detail": "", "fix_summary": "", "parent_path": ""}]
    on_worktree_health_refresh_done(app, issues, scan_at=1)
    first_logs = list(app.logs)
    assert any("worktree health" in m for _l, m in first_logs)
    assert app.worktree_health_issues == issues

    # Same issue set, dismissed by user → no further log.
    dismiss_worktree_health(app)
    on_worktree_health_refresh_done(app, issues, scan_at=2)
    assert app.logs == first_logs

    # Going clean re-logs at info level.
    on_worktree_health_refresh_done(app, [], scan_at=3)
    assert any(lvl == "info" and "clean" in msg for lvl, msg in app.logs)


def test_audit_then_save_then_reload_matches(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    cache_save_worktree_health(tmp_path, 7, [])
    cached = cache_load_worktree_health(tmp_path)
    assert cached == (7, [])


def test_banner_shows_summary_when_issues_present(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    _capture_logs(app)
    issues = [
        {"kind": "stale_gitdir", "path": "/x", "detail": "", "fix_summary": "", "parent_path": ""},
        {"kind": "orphan_admin", "path": "/y", "detail": "", "fix_summary": "", "parent_path": ""},
    ]
    on_worktree_health_refresh_done(app, issues, scan_at=1)

    assert "visible" in app._banner.classes
    assert "2 issue(s)" in app._banner.text
    assert "stale_gitdir:1" in app._banner.text
    assert "orphan_admin:1" in app._banner.text


def test_banner_hides_when_dismissed_and_reshows_on_count_change(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    _capture_logs(app)
    on_worktree_health_refresh_done(
        app,
        [{"kind": "stale_gitdir", "path": "/x", "detail": "", "fix_summary": "", "parent_path": ""}],
        scan_at=1,
    )
    assert "visible" in app._banner.classes

    dismiss_worktree_health(app)
    assert "visible" not in app._banner.classes

    # Same count → stays dismissed.
    on_worktree_health_refresh_done(
        app,
        [{"kind": "stale_gitdir", "path": "/x", "detail": "", "fix_summary": "", "parent_path": ""}],
        scan_at=2,
    )
    assert "visible" not in app._banner.classes

    # Issue count changes → dismissal lifts and banner returns.
    on_worktree_health_refresh_done(
        app,
        [
            {"kind": "stale_gitdir", "path": "/x", "detail": "", "fix_summary": "", "parent_path": ""},
            {"kind": "orphan_admin", "path": "/y", "detail": "", "fix_summary": "", "parent_path": ""},
        ],
        scan_at=3,
    )
    assert "visible" in app._banner.classes
    assert app.worktree_health_dismissed is False


def test_banner_clears_when_workspace_goes_clean(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    _capture_logs(app)
    on_worktree_health_refresh_done(
        app,
        [{"kind": "stale_gitdir", "path": "/x", "detail": "", "fix_summary": "", "parent_path": ""}],
        scan_at=1,
    )
    on_worktree_health_refresh_done(app, [], scan_at=2)
    assert app._banner.text == ""
    assert "visible" not in app._banner.classes
