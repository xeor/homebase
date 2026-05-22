from __future__ import annotations

import subprocess
from pathlib import Path

from homebase.cache.api import cache_load_rows, cache_store_rows
from homebase.cli.parser import build_cli_parser
from homebase.workspace.new import cmd_new
from homebase.workspace.projects import project_row


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


def test_repo_dir_survives_cache_round_trip(tmp_path: Path) -> None:
    parent = _init_project_repo(tmp_path, "foo")
    row = project_row(parent, archived=False)
    assert row.repo_dir == "repo"

    cache_store_rows(tmp_path, [row], [])
    active, _archived, _ts = cache_load_rows(tmp_path, max_age_s=99999)

    loaded = next(r for r in active if r.path == parent)
    assert loaded.repo_dir == "repo"


def test_worktree_of_survives_cache_round_trip(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    wt = tmp_path / "foo-featx"
    fresh = project_row(wt, archived=False)
    assert fresh.worktree_of == "foo"
    assert fresh.repo_dir == "repo"

    cache_store_rows(tmp_path, [fresh], [])
    active, _archived, _ts = cache_load_rows(tmp_path, max_age_s=99999)

    loaded = next(r for r in active if r.path == wt)
    assert loaded.worktree_of == "foo"
    assert loaded.repo_dir == "repo"


def test_cached_row_keeps_empty_fields_when_unset(tmp_path: Path) -> None:
    # A bare project without git or repo_dir should round-trip with
    # both fields empty.
    project = tmp_path / "bare"
    project.mkdir()
    (project / ".base.yaml").write_text("tags: []\n", encoding="utf-8")
    row = project_row(project, archived=False)
    assert row.worktree_of == ""
    assert row.repo_dir == ""

    cache_store_rows(tmp_path, [row], [])
    active, _archived, _ts = cache_load_rows(tmp_path, max_age_s=99999)

    loaded = next(r for r in active if r.path == project)
    assert loaded.worktree_of == ""
    assert loaded.repo_dir == ""
