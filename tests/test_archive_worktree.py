from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from homebase.cli.parser import build_cli_parser
from homebase.commands.archive import (
    archive_move_internal,
    archive_pack_internal,
    archive_unpack_internal,
)
from homebase.commands.fix_worktrees import cmd_fix_worktrees
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


def test_pack_worktree_warns_and_produces_tarball(tmp_path: Path, capsys) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    wt = tmp_path / "foo-featx"
    archived = archive_move_internal(tmp_path, wt, sync_tags=False)
    capsys.readouterr()

    dst = archive_pack_internal(tmp_path, archived)
    captured = capsys.readouterr()
    assert dst.suffix == ".tgz"
    assert "warning" in captured.err.lower()
    assert "fix-worktrees" in captured.err


def test_pack_worktree_rejected_when_block_incomplete(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    wt = tmp_path / "foo-featx"
    archived = archive_move_internal(tmp_path, wt, sync_tags=False)
    block = yaml.safe_load((archived / ".base.yaml").read_text())
    block["worktree"].pop("gitdir_id")
    (archived / ".base.yaml").write_text(yaml.safe_dump(block), encoding="utf-8")

    with pytest.raises(ValueError, match="incomplete worktree block"):
        archive_pack_internal(tmp_path, archived)


def test_unpack_stale_worktree_emits_warning(tmp_path: Path, capsys) -> None:
    import shutil

    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    wt = tmp_path / "foo-featx"
    archived = archive_move_internal(tmp_path, wt, sync_tags=False)
    packed = archive_pack_internal(tmp_path, archived)
    capsys.readouterr()
    # Remove the parent so unpack's pointer resolves at a missing path.
    shutil.rmtree(tmp_path / "foo")

    archive_unpack_internal(tmp_path, packed)
    captured = capsys.readouterr()
    assert "stale gitdir" in captured.err.lower()
    assert "fix-worktrees" in captured.err


def test_pack_unpack_round_trip_repairable_via_fix(tmp_path: Path, capsys) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    wt = tmp_path / "foo-featx"
    archived = archive_move_internal(tmp_path, wt, sync_tags=False)
    packed = archive_pack_internal(tmp_path, archived)
    capsys.readouterr()

    unpacked = archive_unpack_internal(tmp_path, packed)
    capsys.readouterr()

    rc = cmd_fix_worktrees(tmp_path, apply=True)
    assert rc == 0
    branch = subprocess.run(
        ["git", "-C", str(unpacked / "repo"), "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert branch == "featx"
