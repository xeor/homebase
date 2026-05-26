from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from homebase.workspace.seed import commit_files, git_init, read_gitdir_id


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )
    return proc.stdout.strip()


def test_git_init_creates_repo_with_initial_branch(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    git_init(repo)
    assert (repo / ".git").is_dir()
    # No commits yet, but HEAD points to refs/heads/main.
    head = (repo / ".git" / "HEAD").read_text().strip()
    assert head == "ref: refs/heads/main"


def test_git_init_writes_user_config(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    git_init(repo, user_email="x@y.z", user_name="X Y")
    assert _git(repo, "config", "user.email") == "x@y.z"
    assert _git(repo, "config", "user.name") == "X Y"


def test_commit_files_uses_author_date(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    git_init(repo)
    (repo / "a.txt").write_text("hi\n")
    when = datetime(2018, 6, 1, 9, 30, tzinfo=timezone.utc)
    commit_files(repo, "first", author_date=when)

    iso = _git(repo, "log", "-1", "--format=%aI")
    assert iso.startswith("2018-06-01")
    commit_ts = int(_git(repo, "log", "-1", "--format=%at"))
    assert commit_ts == int(when.timestamp())


def test_commit_files_without_date_uses_now(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    git_init(repo)
    (repo / "a.txt").write_text("hi\n")
    commit_files(repo, "now")
    iso = _git(repo, "log", "-1", "--format=%aI")
    assert iso.startswith("20")


def test_commit_files_with_explicit_paths(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    git_init(repo)
    (repo / "a.txt").write_text("a\n")
    (repo / "b.txt").write_text("b\n")
    commit_files(repo, "only a", paths=["a.txt"])
    files = _git(repo, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
    assert files == ["a.txt"]


def test_read_gitdir_id_finds_worktree_entry(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    git_init(parent)
    (parent / "seed.txt").write_text("seed\n")
    commit_files(parent, "seed")

    wt_repo = tmp_path / "wt-x"
    subprocess.run(
        ["git", "-C", str(parent), "worktree", "add",
         "-b", "feat/x", str(wt_repo)],
        check=True, capture_output=True,
    )
    found = read_gitdir_id(parent, wt_repo)
    assert (parent / ".git" / "worktrees" / found).is_dir()


def test_read_gitdir_id_raises_when_missing(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    git_init(parent)
    # No worktrees admin dir exists yet.
    other = tmp_path / "elsewhere"
    other.mkdir()
    try:
        read_gitdir_id(parent, other)
    except ValueError:
        return
    raise AssertionError("expected ValueError when no worktrees admin dir")
