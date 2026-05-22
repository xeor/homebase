from __future__ import annotations

import subprocess
from pathlib import Path

from homebase.commands import workspace as commands_workspace
from homebase.metadata.api import load_base_repo_dir


def _git_init(dir_path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=dir_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=dir_path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=dir_path, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=dir_path, check=True)
    (dir_path / "f.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=dir_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=dir_path, check=True)


def _yes(*_args, **_kwargs) -> bool:
    return True


def _read_input(*_args, **_kwargs):
    return None


def _run_fix(project: Path, *, yes: bool = True) -> str:
    return commands_workspace._fix_active_project(
        project,
        include={"marker", "repo-dir"},
        yes=yes,
        base_marker_file=".base.yaml",
        prompt_yes_no=_yes,
        ensure_base_marker=lambda p: (p / ".base.yaml").touch(exist_ok=True),
    )


def test_repo_dir_fixer_detects_flat_layout(tmp_path: Path, capsys) -> None:
    project = tmp_path / "flat"
    project.mkdir()
    _git_init(project)
    (project / ".base.yaml").write_text("tags: []\n", encoding="utf-8")

    outcome = _run_fix(project)
    assert outcome == "changed"
    assert load_base_repo_dir(project) == "."


def test_repo_dir_fixer_detects_repo_subdir_layout(tmp_path: Path) -> None:
    project = tmp_path / "wrapped"
    repo = project / "repo"
    repo.mkdir(parents=True)
    _git_init(repo)
    (project / ".base.yaml").write_text("tags: []\n", encoding="utf-8")

    outcome = _run_fix(project)
    assert outcome == "changed"
    assert load_base_repo_dir(project) == "repo"


def test_repo_dir_fixer_prefers_dot_when_both_exist(tmp_path: Path) -> None:
    project = tmp_path / "ambiguous"
    project.mkdir()
    _git_init(project)
    repo = project / "repo"
    repo.mkdir()
    _git_init(repo)
    (project / ".base.yaml").write_text("tags: []\n", encoding="utf-8")

    outcome = _run_fix(project)
    assert outcome == "changed"
    assert load_base_repo_dir(project) == "."


def test_repo_dir_fixer_idempotent_when_already_configured(tmp_path: Path) -> None:
    project = tmp_path / "set"
    repo = project / "repo"
    repo.mkdir(parents=True)
    _git_init(repo)
    (project / ".base.yaml").write_text("tags: []\nrepo_dir: repo\n", encoding="utf-8")

    outcome = _run_fix(project)
    assert outcome == "ok"
    assert load_base_repo_dir(project) == "repo"


def test_repo_dir_fixer_skips_when_no_git_anywhere(tmp_path: Path) -> None:
    project = tmp_path / "bare"
    project.mkdir()
    (project / ".base.yaml").write_text("tags: []\n", encoding="utf-8")

    outcome = _run_fix(project)
    assert outcome == "ok"
    assert load_base_repo_dir(project) == ""


def test_repo_dir_fixer_declined_when_yes_false(tmp_path: Path) -> None:
    project = tmp_path / "ask"
    repo = project / "repo"
    repo.mkdir(parents=True)
    _git_init(repo)
    (project / ".base.yaml").write_text("tags: []\n", encoding="utf-8")

    def _no(*_a, **_kw) -> bool:
        return False

    outcome = commands_workspace._fix_active_project(
        project,
        include={"marker", "repo-dir"},
        yes=False,
        base_marker_file=".base.yaml",
        prompt_yes_no=_no,
        ensure_base_marker=lambda p: (p / ".base.yaml").touch(exist_ok=True),
    )
    assert outcome == "skipped"
    assert load_base_repo_dir(project) == ""
