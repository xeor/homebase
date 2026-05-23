"""End-to-end tests for ``b new <input>`` invoked from inside a base
project's git repo.

The three input shapes the user types must produce three different
on-disk outcomes — autodetect routes them, but the apply path is what
the user actually sees:

  ``b new featx``    -> git worktree of <base>/foo/repo on branch featx
  ``b new featx/``   -> local move of <base>/foo/repo/featx into a new
                        sibling project <base>/featx/
  ``b new ./featx``  -> same as above (any path-shaped input)

Regression for the case where the trailing slash silently fell into
the worktree shortcut.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from homebase.cli.parser import build_cli_parser
from homebase.metadata.api import load_base_repo_dir, load_base_worktree
from homebase.workspace.new import cmd_new


def _run_new(base: Path, cwd: Path, args: list[str]) -> int:
    ns = build_cli_parser().parse_args(["new", *args, "--no-open", "--yes"])
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


def test_bare_input_inside_repo_creates_worktree(tmp_path: Path) -> None:
    parent = _init_project_repo(tmp_path, "foo")
    rc = _run_new(tmp_path, parent / "repo", ["featx"])
    assert rc == 0
    wt = tmp_path / "foo-featx"
    assert (wt / "repo" / ".git").exists()
    block = load_base_worktree(wt)
    assert block is not None
    assert block["of"] == "foo"
    assert block["branch"] == "featx"


def test_trailing_slash_inside_repo_moves_local_folder(tmp_path: Path) -> None:
    parent = _init_project_repo(tmp_path, "foo")
    folder = parent / "repo" / "featx"
    folder.mkdir()
    (folder / "marker.txt").write_text("hi\n", encoding="utf-8")
    rc = _run_new(tmp_path, parent / "repo", ["featx/"])
    assert rc == 0
    # New sibling project at <base>/featx/, original folder gone, marker
    # carried over, and the worktree shortcut did NOT fire.
    target = tmp_path / "featx"
    assert target.is_dir()
    assert not folder.exists()
    assert (target / "marker.txt").read_text(encoding="utf-8") == "hi\n"
    assert load_base_worktree(target) is None
    # No .git in the moved folder, so repo_dir stays unset.
    assert load_base_repo_dir(target) == ""


def test_relative_path_inside_repo_moves_local_folder(tmp_path: Path) -> None:
    parent = _init_project_repo(tmp_path, "foo")
    folder = parent / "repo" / "sub"
    folder.mkdir()
    rc = _run_new(tmp_path, parent / "repo", ["./sub"])
    assert rc == 0
    target = tmp_path / "sub"
    assert target.is_dir()
    assert not folder.exists()
    assert load_base_worktree(target) is None
