from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from homebase.cli.parser import build_cli_parser
from homebase.workspace.new import cmd_new


def _run(base: Path, cwd: Path, args: list[str]) -> int:
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


def _read_meta(project: Path) -> dict:
    return yaml.safe_load((project / ".base.yaml").read_text(encoding="utf-8"))


def test_worktree_explicit_creates_directory_and_block(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")

    rc = _run(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"])
    assert rc == 0

    out = tmp_path / "foo-featx"
    assert (out / "repo" / ".git").is_file()
    branch = subprocess.run(
        ["git", "-C", str(out / "repo"), "branch", "--show-current"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert branch == "featx"

    meta = _read_meta(out)
    block = meta["worktree"]
    assert block["of"] == "foo"
    assert block["branch"] == "featx"
    assert Path(block["parent_path"]) == (tmp_path / "foo" / "repo")
    assert isinstance(block["gitdir_id"], str) and block["gitdir_id"]


def test_worktree_slash_branch_sanitized_dir(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")

    rc = _run(tmp_path, tmp_path, ["feature/auth", "--as", "worktree", "--from", "foo"])
    assert rc == 0

    out = tmp_path / "foo-feature--auth"
    assert out.is_dir()
    meta = _read_meta(out)
    assert meta["worktree"]["branch"] == "feature/auth"


def test_worktree_autodefault_from_cwd_inside_project(tmp_path: Path) -> None:
    parent = _init_project_repo(tmp_path, "foo")
    sub = parent / "repo" / "sub"
    sub.mkdir()

    rc = _run(tmp_path, sub, ["x"])
    assert rc == 0
    out = tmp_path / "foo-x"
    assert out.is_dir()
    assert _read_meta(out)["worktree"]["of"] == "foo"


def test_worktree_chained_parent_resolves_to_root(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    rc1 = _run(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"])
    assert rc1 == 0
    wt = tmp_path / "foo-featx"

    rc2 = _run(tmp_path, wt / "repo", ["bugfix-y"])
    assert rc2 == 0
    out = tmp_path / "foo-bugfix-y"
    assert out.is_dir()
    block = _read_meta(out)["worktree"]
    assert block["of"] == "foo"
    log = subprocess.run(
        ["git", "-C", str(out / "repo"), "log", "-1", "--format=%H"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    featx_head = subprocess.run(
        ["git", "-C", str(wt / "repo"), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert log == featx_head


def test_worktree_collision_errors_without_mutation(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    (tmp_path / "foo-featx").mkdir()

    rc = _run(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"])
    assert rc == 1
    contents = list((tmp_path / "foo-featx").iterdir())
    assert contents == []


def test_worktree_missing_from_errors(tmp_path: Path) -> None:
    rc = _run(tmp_path, tmp_path, ["featx", "--as", "worktree"])
    assert rc == 1
