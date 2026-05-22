from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import yaml

from homebase.cli.parser import build_cli_parser
from homebase.commands.fix_worktrees import cmd_fix_worktrees
from homebase.workspace.health import (
    ISSUE_MISSING_PARENT,
    ISSUE_ORPHAN_ADMIN,
    ISSUE_RELOCATED_PARENT,
    ISSUE_STALE_GITDIR,
    audit_workspace,
    repair_issue,
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


def test_audit_clean_workspace_has_no_issues(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0

    assert audit_workspace(tmp_path) == []


def test_audit_detects_missing_parent(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    shutil.rmtree(tmp_path / "foo")

    issues = audit_workspace(tmp_path)
    kinds = {i.kind for i in issues}
    assert ISSUE_MISSING_PARENT in kinds


def test_audit_detects_relocated_parent_via_parent_path(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    # Move the parent project out of base. parent_path (absolute, set at
    # creation) still resolves; base/<of>/repo no longer does. That's the
    # "relocated parent" scenario the audit should flag.
    elsewhere = tmp_path / "stash"
    elsewhere.mkdir()
    shutil.move(str(tmp_path / "foo"), str(elsewhere / "foo"))
    block = yaml.safe_load((tmp_path / "foo-featx" / ".base.yaml").read_text())
    block["worktree"]["parent_path"] = str(elsewhere / "foo" / "repo")
    (tmp_path / "foo-featx" / ".base.yaml").write_text(
        yaml.safe_dump(block), encoding="utf-8"
    )

    issues = audit_workspace(tmp_path)
    kinds = {i.kind for i in issues}
    assert ISSUE_RELOCATED_PARENT in kinds


def test_audit_detects_stale_gitdir_after_manual_move(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    wt = tmp_path / "foo-featx"
    new_wt = tmp_path / "foo-renamed"
    # Plain os.rename (no pointer rewrite) deliberately leaves stale state.
    wt.rename(new_wt)

    issues = audit_workspace(tmp_path)
    kinds = {i.kind for i in issues}
    assert ISSUE_STALE_GITDIR in kinds


def test_audit_detects_orphan_admin_entry(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    shutil.rmtree(tmp_path / "foo-featx")

    issues = audit_workspace(tmp_path)
    kinds = {i.kind for i in issues}
    assert ISSUE_ORPHAN_ADMIN in kinds


def test_repair_stale_gitdir_via_git_worktree_repair(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    wt = tmp_path / "foo-featx"
    new_wt = tmp_path / "foo-renamed"
    wt.rename(new_wt)

    issues = audit_workspace(tmp_path)
    stale = [i for i in issues if i.kind == ISSUE_STALE_GITDIR]
    assert stale
    ok, _detail = repair_issue(stale[0])
    assert ok

    follow_up = [i for i in audit_workspace(tmp_path) if i.kind == ISSUE_STALE_GITDIR]
    assert follow_up == []


def test_cmd_fix_worktrees_dry_run_returns_one_with_issues(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    shutil.rmtree(tmp_path / "foo-featx")

    rc = cmd_fix_worktrees(tmp_path, apply=False)
    assert rc == 1


def test_cmd_fix_worktrees_apply_returns_zero_on_success(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    shutil.rmtree(tmp_path / "foo-featx")

    rc = cmd_fix_worktrees(tmp_path, apply=True)
    assert rc == 0
    assert audit_workspace(tmp_path) == []


def test_cmd_fix_worktrees_clean_returns_zero(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    assert cmd_fix_worktrees(tmp_path, apply=False) == 0


def test_audit_flags_worktree_dir_missing_base_yaml(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    # Remove the worktree's .base.yaml so the admin entry still points
    # at a real directory, but homebase no longer treats it as a managed
    # worktree row.
    wt_meta = tmp_path / "foo-featx" / ".base.yaml"
    wt_meta.unlink()

    issues = audit_workspace(tmp_path)
    kinds = {i.kind for i in issues}
    assert ISSUE_ORPHAN_ADMIN in kinds
