from __future__ import annotations

import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

from homebase.cache.api import (
    cache_load_worktree_health_rows,
    cache_prune_worktree_health_rows,
    cache_upsert_worktree_health_row,
)
from homebase.cli.parser import build_cli_parser
from homebase.ui.sync.worktree_health import (
    _is_idle,
    maybe_refresh_worktree_health,
)
from homebase.workspace.health import (
    audit_unit,
    audit_unit_signature,
    list_audit_units,
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
    (project / ".base.yaml").write_text("tags: []\nrepo_dir: repo\n", encoding="utf-8")
    return project


def test_list_audit_units_includes_parents_and_worktrees(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["a", "--as", "worktree", "--from", "foo"]) == 0
    units = list_audit_units(tmp_path)
    names = {u.name for u in units}
    assert {"foo", "foo-a"} <= names


def test_audit_unit_signature_changes_when_pointer_moves(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["a", "--as", "worktree", "--from", "foo"]) == 0
    wt = tmp_path / "foo-a"
    sig_before = audit_unit_signature(tmp_path, wt)

    # Touch the parent admin entry mtime by writing into its dir.
    parent_admin = tmp_path / "foo" / "repo" / ".git" / "worktrees"
    entry = next(parent_admin.iterdir())
    time.sleep(0.01)
    (entry / "gitdir").write_text(
        (entry / "gitdir").read_text(encoding="utf-8"), encoding="utf-8"
    )

    sig_after = audit_unit_signature(tmp_path, wt)
    assert sig_after != sig_before


def test_cache_row_round_trip_and_prune(tmp_path: Path) -> None:
    cache_upsert_worktree_health_row(
        tmp_path, "/abs/foo-a", "sig1", 100, [{"kind": "stale_gitdir"}]
    )
    cache_upsert_worktree_health_row(
        tmp_path, "/abs/foo-b", "sig2", 100, []
    )
    rows = cache_load_worktree_health_rows(tmp_path)
    assert set(rows.keys()) == {"/abs/foo-a", "/abs/foo-b"}
    assert rows["/abs/foo-a"][0] == "sig1"

    cache_prune_worktree_health_rows(tmp_path, {"/abs/foo-a"})
    rows = cache_load_worktree_health_rows(tmp_path)
    assert set(rows.keys()) == {"/abs/foo-a"}


def test_audit_unit_returns_no_issues_for_healthy_row(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["a", "--as", "worktree", "--from", "foo"]) == 0
    wt = tmp_path / "foo-a"
    assert audit_unit(tmp_path, wt) == []


def test_is_idle_returns_false_during_busy_or_typing() -> None:
    app = SimpleNamespace(
        query_apply_pending=False,
        _busy_depth=0,
        _critical_job_active=lambda: False,
    )
    assert _is_idle(app) is True

    app.query_apply_pending = True
    assert _is_idle(app) is False
    app.query_apply_pending = False

    app._busy_depth = 2
    assert _is_idle(app) is False
    app._busy_depth = 0

    app._critical_job_active = lambda: True
    assert _is_idle(app) is False


def test_maybe_refresh_short_circuits_when_not_idle(tmp_path: Path) -> None:
    app = SimpleNamespace(
        base_dir=tmp_path,
        fast_exit_requested=False,
        worktree_health_refresh_running=False,
        worktree_health_refresh_last_ts=0.0,
        worktree_health_scan_cursor=[],
        query_apply_pending=True,
        _busy_depth=0,
        _critical_job_active=lambda: False,
        call_from_thread=lambda *_args, **_kw: None,
    )
    maybe_refresh_worktree_health(app, interval_s=1.0)
    # When not idle, neither the refresh state nor the last_ts should
    # change — the scheduler exits early.
    assert app.worktree_health_refresh_running is False
    assert app.worktree_health_refresh_last_ts == 0.0
