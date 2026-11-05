from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from homebase.cache.api import cache_load_worktree_health
from homebase.workspace import health_scan
from homebase.workspace.health import WorktreeIssue


def _project(base: Path, name: str) -> Path:
    """A project with a git repo: a potential worktree parent, so an audit unit."""
    path = base / name
    repo = path / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    (path / ".base.yaml").write_text("tags: []\nrepo_dir: repo\n", encoding="utf-8")
    return path


def test_issue_to_dict() -> None:
    issue = WorktreeIssue(
        kind="orphan", path=Path("/a"), detail="d", fix_summary="f", parent_path=None
    )
    assert health_scan.issue_to_dict(issue) == {
        "kind": "orphan", "path": "/a", "detail": "d", "fix_summary": "f", "parent_path": "",
    }


def test_scan_empty_base_stores_clean_result(tmp_path: Path) -> None:
    issues, remaining, visited, ts = health_scan.scan_worktree_health(tmp_path, [], budget_s=None)
    assert (issues, remaining, visited) == ([], [], 0)
    assert cache_load_worktree_health(tmp_path) == (ts, [])


def test_scan_reaudits_only_changed_units(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _project(tmp_path, "alpha")
    _project(tmp_path, "beta")
    audits: list[Path] = []
    real_audit = health_scan.audit_unit

    def counting_audit(base: Path, unit: Path):
        audits.append(unit)
        return real_audit(base, unit)

    monkeypatch.setattr(health_scan, "audit_unit", counting_audit)
    _issues, remaining, visited, _ts = health_scan.scan_worktree_health(tmp_path, [], budget_s=None)
    assert remaining == []
    assert visited == len(audits) >= 2
    audits.clear()
    health_scan.scan_worktree_health(tmp_path, [], budget_s=None)
    assert audits == []


def test_scan_stops_at_budget_and_resumes(tmp_path: Path) -> None:
    _project(tmp_path, "alpha")
    _project(tmp_path, "beta")
    _issues, remaining, visited, _ts = health_scan.scan_worktree_health(tmp_path, [], budget_s=0.0)
    assert visited == 1
    assert remaining
    _issues, rest, visited2, _ts = health_scan.scan_worktree_health(tmp_path, remaining, budget_s=None)
    assert rest == []
    assert visited2 == len(remaining)
