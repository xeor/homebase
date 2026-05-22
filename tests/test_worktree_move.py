from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from homebase.cli.parser import build_cli_parser
from homebase.commands.archive import archive_move_internal
from homebase.metadata.api import load_base_worktree
from homebase.workspace.new import cmd_new
from homebase.workspace.worktree_paths import find_worktree_children, move_project


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


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def test_move_project_renames_worktree_and_repairs_pointers(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    old = tmp_path / "foo-featx"
    new = tmp_path / "foo-renamed"

    move_project(tmp_path, old, new)

    assert not old.exists()
    assert (new / "repo" / ".git").is_file()
    assert _git(new / "repo", "branch", "--show-current") == "featx"
    block = load_base_worktree(new)
    assert block is not None
    assert block["of"] == "foo"
    parent_admin = tmp_path / "foo" / "repo" / ".git" / "worktrees"
    entry = next(parent_admin.iterdir())
    pointer = (entry / "gitdir").read_text().strip()
    assert pointer.endswith("foo-renamed/repo/.git")


def test_move_project_renames_parent_and_rewrites_children(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    new_parent = tmp_path / "bar"

    move_project(tmp_path, tmp_path / "foo", new_parent)

    child = tmp_path / "foo-featx"
    assert (new_parent / "repo" / ".git").is_dir()
    block = load_base_worktree(child)
    assert block is not None
    assert block["of"] == "bar"
    assert block["parent_path"] == str(new_parent / "repo")
    assert _git(child / "repo", "rev-parse", "HEAD")


def test_archive_worktree_repairs_pointers(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    wt = tmp_path / "foo-featx"

    dst = archive_move_internal(tmp_path, wt, sync_tags=False)

    assert not wt.exists()
    assert (dst / "repo" / ".git").is_file()
    assert _git(dst / "repo", "branch", "--show-current") == "featx"


def test_archive_parent_with_active_worktrees_is_blocked(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0

    with pytest.raises(ValueError, match="active worktrees"):
        archive_move_internal(tmp_path, tmp_path / "foo", sync_tags=False)
    assert (tmp_path / "foo").is_dir()


def test_find_worktree_children_returns_paths_for_parent(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    _init_project_repo(tmp_path, "bar")
    assert _run_new(tmp_path, tmp_path, ["a", "--as", "worktree", "--from", "foo"]) == 0
    assert _run_new(tmp_path, tmp_path, ["b", "--as", "worktree", "--from", "foo"]) == 0

    children = find_worktree_children(tmp_path, "foo")
    names = sorted(c.name for c in children)
    assert names == ["foo-a", "foo-b"]
    assert find_worktree_children(tmp_path, "bar") == []
