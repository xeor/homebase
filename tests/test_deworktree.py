from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from homebase.cli.parser import build_cli_parser
from homebase.commands.deworktree import cmd_deworktree
from homebase.metadata.api import load_base_worktree
from homebase.workspace.deworktree import deworktree
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


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def test_deworktree_makes_standalone_repo(tmp_path: Path) -> None:
    parent = _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    wt = tmp_path / "foo-featx"
    (wt / "repo" / "wt.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(wt / "repo"), "add", "wt.txt"], check=True)
    subprocess.run(["git", "-C", str(wt / "repo"), "commit", "-q", "-m", "wt"], check=True)
    wt_head = _git(wt / "repo", "rev-parse", "HEAD")

    deworktree(tmp_path, wt)

    git_dir = wt / "repo" / ".git"
    assert git_dir.is_dir()
    assert (git_dir / "HEAD").is_file()
    assert _git(wt / "repo", "branch", "--show-current") == "featx"
    assert _git(wt / "repo", "rev-parse", "HEAD") == wt_head
    log = _git(wt / "repo", "log", "--format=%s")
    assert "wt" in log
    assert "init" in log
    assert load_base_worktree(wt) is None
    parent_admin = parent / "repo" / ".git" / "worktrees"
    assert not parent_admin.exists() or not any(parent_admin.iterdir())
    assert not (git_dir / "worktrees").exists()


def test_deworktree_status_clean_after_run(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    wt = tmp_path / "foo-featx"

    deworktree(tmp_path, wt)

    status = _git(wt / "repo", "status", "--porcelain")
    assert status == ""


def test_deworktree_rejects_non_worktree(tmp_path: Path) -> None:
    plain = _init_project_repo(tmp_path, "foo")
    with pytest.raises(ValueError, match="not a worktree"):
        deworktree(tmp_path, plain)


def test_cmd_deworktree_returns_zero_on_success(tmp_path: Path, capsys) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    wt = tmp_path / "foo-featx"

    rc = cmd_deworktree(tmp_path, str(wt))
    captured = capsys.readouterr()
    assert rc == 0
    assert "deworktreed" in captured.out
    assert load_base_worktree(wt) is None


def test_cmd_deworktree_returns_one_when_not_a_worktree(tmp_path: Path) -> None:
    plain = _init_project_repo(tmp_path, "foo")
    rc = cmd_deworktree(tmp_path, str(plain))
    assert rc == 1
