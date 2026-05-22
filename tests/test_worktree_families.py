from __future__ import annotations

import subprocess
from pathlib import Path

from homebase.cli.parser import build_cli_parser
from homebase.commands.archive import archive_move_internal, delete_internal
from homebase.metadata.api import load_base_worktree
from homebase.workspace.health import audit_workspace
from homebase.workspace.new import cmd_new
from homebase.workspace.worktree_families import (
    archive_family_together,
    deworktree_family,
)


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


def test_deworktree_family_clears_all_worktree_blocks(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["a", "--as", "worktree", "--from", "foo"]) == 0
    assert _run_new(tmp_path, tmp_path, ["b", "--as", "worktree", "--from", "foo"]) == 0
    children = [tmp_path / "foo-a", tmp_path / "foo-b"]

    done = deworktree_family(tmp_path, children)

    assert done == children
    for child in children:
        assert load_base_worktree(child) is None
        assert (child / "repo" / ".git").is_dir()


def test_delete_after_deworktree_succeeds(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["x", "--as", "worktree", "--from", "foo"]) == 0
    deworktree_family(tmp_path, [tmp_path / "foo-x"])

    delete_internal(tmp_path, tmp_path / "foo", sync_tags=False)

    assert not (tmp_path / "foo").exists()
    assert (tmp_path / "foo-x" / "repo" / ".git").is_dir()


def test_archive_family_together_moves_and_reanchors(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    parent = tmp_path / "foo"
    wts = [tmp_path / "foo-featx"]

    archived_parent, archived_wts = archive_family_together(
        tmp_path,
        parent,
        wts,
        archive_move=lambda base, src: archive_move_internal(
            base, src, sync_tags=False, allow_worktree_children=True
        ),
    )

    assert not parent.exists()
    assert not (tmp_path / "foo-featx").exists()
    assert (archived_parent / "repo" / ".git").is_dir()
    archived_wt = archived_wts[0]
    assert (archived_wt / "repo" / ".git").is_file()
    block = load_base_worktree(archived_wt)
    assert block is not None
    assert block["parent_path"] == str(archived_parent / "repo")
    branch = subprocess.run(
        ["git", "-C", str(archived_wt / "repo"), "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert branch == "featx"


def test_archive_workflow_blocks_until_worktrees_handled(tmp_path: Path) -> None:
    import pytest

    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0

    with pytest.raises(ValueError):
        archive_move_internal(tmp_path, tmp_path / "foo", sync_tags=False)

    archived = archive_move_internal(
        tmp_path,
        tmp_path / "foo",
        sync_tags=False,
        allow_worktree_children=True,
    )
    assert archived.is_dir()


def test_after_together_archive_audit_finds_no_issues(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    archive_family_together(
        tmp_path,
        tmp_path / "foo",
        [tmp_path / "foo-featx"],
        archive_move=lambda base, src: archive_move_internal(
            base, src, sync_tags=False, allow_worktree_children=True
        ),
    )
    issues = audit_workspace(tmp_path)
    # The archived family lives under _archive/, which the auditor
    # skips. Nothing under base/ has a worktree: block anymore.
    assert issues == []
