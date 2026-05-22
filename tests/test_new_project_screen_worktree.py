from __future__ import annotations

import subprocess
from pathlib import Path

from homebase.cli.parser import build_cli_parser
from homebase.ui.screens.new_project import (
    SECTION_NAME,
    SECTION_SOURCE,
    NewProjectScreen,
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
    (project / ".base.yaml").write_text("tags: []\n", encoding="utf-8")
    return project


class _ScreenStub(NewProjectScreen):
    """Bypass Textual mount: build a screen that uses stub Input
    values instead of querying real widgets. We never compose() it."""

    def __init__(self, base_dir: Path, *, prefill=None, input_value="", name_value=""):
        # Call __init__ but skip Textual setup that touches widgets.
        self.base_dir_ref = base_dir
        self.allow_stay_in_b = True
        self.templates = []
        self.sources_cfg = {}
        self.source_choices = ["auto", "empty", "local", "git", "download", "downloaded", "worktree"]
        self.source_index = 0
        self.toggle_values = {"tmp": False, "timestamp": False, "open": True, "cd": False, "archive": False, "ts_name": False, "alpha_name": False}
        self.template_index = 0
        self.selected_tags: set[str] = set()
        self.focus_section = SECTION_SOURCE
        self.toggle_index = 0
        self.prefill = dict(prefill or {})
        self.prefill_from_project = str(self.prefill.get("from_project", "")).strip()
        prefill_source = str(self.prefill.get("source", "")).strip()
        if prefill_source and prefill_source in self.source_choices:
            self.source_index = self.source_choices.index(prefill_source)
        if self.prefill_from_project:
            self.focus_section = SECTION_NAME
        self._stub_input = input_value
        self._stub_name = name_value

    def _input_value(self) -> str:
        return self._stub_input

    def _name_value(self) -> str:
        return self._stub_name


def test_derived_parent_name_resolves_repo_subpath(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree", "from_project": "foo"},
        input_value=str(tmp_path / "foo" / "repo"),
        name_value="featx",
    )
    assert screen._derived_worktree_parent_name() == "foo"
    dir_name, err = screen._worktree_validation()
    assert err == ""
    assert dir_name == "foo-featx"


def test_validation_flags_missing_branch(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree", "from_project": "foo"},
        input_value=str(tmp_path / "foo" / "repo"),
        name_value="",
    )
    _dir, err = screen._worktree_validation()
    assert "branch name required" in err


def test_validation_flags_missing_path(tmp_path: Path) -> None:
    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree"},
        input_value="",
        name_value="featx",
    )
    _dir, err = screen._worktree_validation()
    assert "parent repo path required" in err


def test_validation_flags_non_repo_path(tmp_path: Path) -> None:
    (tmp_path / "blank").mkdir()
    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree"},
        input_value=str(tmp_path / "blank"),
        name_value="featx",
    )
    _dir, err = screen._worktree_validation()
    assert "no git repo" in err


def test_validation_flags_target_collision(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    (tmp_path / "foo-featx").mkdir()
    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree", "from_project": "foo"},
        input_value=str(tmp_path / "foo" / "repo"),
        name_value="featx",
    )
    _dir, err = screen._worktree_validation()
    assert "target exists" in err


def test_validation_chains_through_worktree_parent(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["a", "--as", "worktree", "--from", "foo"]) == 0
    # Path points at the worktree (foo-a), not the root parent.
    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree"},
        input_value=str(tmp_path / "foo-a" / "repo"),
        name_value="b",
    )
    # Derived parent name walks worktree.of back to the root: "foo".
    assert screen._derived_worktree_parent_name() == "foo"
    dir_name, err = screen._worktree_validation()
    assert err == ""
    assert dir_name == "foo-b"


def test_branch_with_slash_sanitises_to_double_dash(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree", "from_project": "foo"},
        input_value=str(tmp_path / "foo" / "repo"),
        name_value="feature/auth",
    )
    dir_name, err = screen._worktree_validation()
    assert err == ""
    assert dir_name == "foo-feature--auth"
