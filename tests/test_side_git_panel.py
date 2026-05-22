from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from homebase.cli.parser import build_cli_parser
from homebase.core.models import ProjectRow
from homebase.ui.side.content import build_side_git_text
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


def _row(
    path: Path,
    *,
    name: str | None = None,
    repo_dir: str = "",
    worktree_of: str = "",
) -> ProjectRow:
    return ProjectRow(
        path=path,
        name=name or path.name,
        branch="main",
        dirty="",
        last="-",
        src="fs",
        created="-",
        tags=[],
        properties=[],
        description="",
        created_ts=0,
        last_ts=0,
        git_ts=0,
        opened_ts=0,
        is_fork=False,
        is_tmp=False,
        archived=False,
        restore_target=None,
        archived_ts=0,
        wip=False,
        suffix=None,
        worktree_of=worktree_of,
        repo_dir=repo_dir,
    )


def _fake_app() -> SimpleNamespace:
    return SimpleNamespace(_esc=lambda x: str(x))


def test_git_panel_shows_repo_path_for_canonical_layout(tmp_path: Path) -> None:
    parent = _init_project_repo(tmp_path, "foo")
    row = _row(parent, repo_dir="repo")
    text = build_side_git_text(_fake_app(), row)
    assert "repo path" in text
    assert str(parent / "repo") in text
    assert ".git at project root" not in text


def test_git_panel_shows_flat_hint_when_repo_dir_dot(tmp_path: Path) -> None:
    project = tmp_path / "flat"
    project.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=project, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=project, check=True)
    (project / "f.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=project, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=project, check=True)
    (project / ".base.yaml").write_text("tags: []\nrepo_dir: .\n", encoding="utf-8")

    row = _row(project, repo_dir=".")
    text = build_side_git_text(_fake_app(), row)
    assert "repo path" in text
    assert ".git at project root" in text


def test_git_panel_shows_worktree_lineage(tmp_path: Path) -> None:
    parent = _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    wt = tmp_path / "foo-featx"
    row = _row(wt, repo_dir="repo", worktree_of="foo")

    text = build_side_git_text(_fake_app(), row)
    assert "worktree of" in text
    assert "foo" in text
    assert "parent repo" in text
    assert str(parent / "repo") in text


def test_git_panel_no_repo_dir_returns_helpful_message(tmp_path: Path) -> None:
    project = tmp_path / "noconf"
    project.mkdir()
    (project / ".base.yaml").write_text("tags: []\n", encoding="utf-8")
    row = _row(project, repo_dir="")
    text = build_side_git_text(_fake_app(), row)
    assert "repo_dir" in text
    assert "b fix --repo-dir" in text


def test_git_panel_for_packed_archive(tmp_path: Path) -> None:
    row = _row(tmp_path / "packed.tgz", repo_dir="repo")
    row.packed = True
    text = build_side_git_text(_fake_app(), row)
    assert "packed archive" in text
