from __future__ import annotations

import subprocess
from pathlib import Path

from homebase.cli.parser import build_cli_parser
from homebase.commands.archive import delete_internal
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


def test_delete_worktree_releases_via_git(tmp_path: Path) -> None:
    parent = _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    wt = tmp_path / "foo-featx"

    delete_internal(tmp_path, wt, sync_tags=False)

    assert not wt.exists()
    admin = parent / "repo" / ".git" / "worktrees"
    assert not admin.exists() or not any(admin.iterdir())


def test_delete_parent_with_worktrees_orphans_them(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    wt = tmp_path / "foo-featx"

    delete_internal(tmp_path, tmp_path / "foo", sync_tags=False)

    assert not (tmp_path / "foo").exists()
    assert wt.exists()
    git_pointer = wt / "repo" / ".git"
    assert git_pointer.is_file()


def test_delete_preview_shows_worktree_badge(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from homebase.ui.actions.bulk_confirm import _delete_preview_lines

    parent_row = SimpleNamespace(
        name="foo",
        archived=False,
        packed=False,
        wip=False,
        worktree_of="",
        size_bytes=0,
        tags=[],
        description="",
        restore_target=None,
    )
    wt_row = SimpleNamespace(
        name="foo-featx",
        archived=False,
        packed=False,
        wip=False,
        worktree_of="foo",
        size_bytes=0,
        tags=[],
        description="",
        restore_target=None,
    )

    class _App:
        active_rows = [parent_row, wt_row]

        def _esc(self, value: str) -> str:
            return value

        def _find_row(self, path: Path):
            if path.name == "foo":
                return ([parent_row], 0)
            if path.name == "foo-featx":
                return ([wt_row], 0)
            return None

    app = _App()
    lines_parent = _delete_preview_lines(
        app, tmp_path / "foo", tmp_path, None, is_under=lambda a, b: True
    )
    assert any("worktrees that will be orphaned" in line for line in lines_parent)
    assert any("foo-featx" in line for line in lines_parent)

    lines_wt = _delete_preview_lines(
        app, tmp_path / "foo-featx", tmp_path, None, is_under=lambda a, b: True
    )
    assert any("worktree of foo" in line for line in lines_wt)
