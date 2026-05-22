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
        self._auto_input_value = ""
        self._last_was_worktree = self._current_source() == "worktree"

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


def test_validation_accepts_project_dir_without_repo_subdir(tmp_path: Path) -> None:
    # Legacy layout: project directory has .git directly, no repo/
    # subdirectory. The dialog should still resolve it.
    proj = tmp_path / "flat"
    proj.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=proj, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=proj, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=proj, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=proj, check=True)
    (proj / "x.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "x.txt"], cwd=proj, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=proj, check=True)
    (proj / ".base.yaml").write_text("tags: []\n", encoding="utf-8")

    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree", "from_project": "flat"},
        input_value=str(proj),
        name_value="featx",
    )
    dir_name, err = screen._worktree_validation()
    assert err == ""
    assert dir_name == "flat-featx"


def test_validation_reports_actual_path_in_error(tmp_path: Path) -> None:
    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree"},
        input_value="/nope/does/not/exist",
        name_value="featx",
    )
    _dir, err = screen._worktree_validation()
    assert "/nope/does/not/exist" in err


def test_compute_auto_parent_path_uses_repo_subdir(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    # NewProjectScreen.__init__ runs base-mount setup; instead we
    # bypass via the stub and call the helper directly.
    screen = _ScreenStub(tmp_path, prefill={"source": "worktree", "from_project": "foo"})
    auto = screen._compute_auto_parent_path("foo")
    assert auto == str(tmp_path / "foo" / "repo")


class _FakeInput:
    def __init__(self, value: str = "") -> None:
        self.value = value
        self.placeholder = ""
        self.disabled = False
        self.classes: set[str] = set()


class _FakeBox:
    def __init__(self) -> None:
        self.classes: set[str] = set()

    def add_class(self, name: str) -> None:
        self.classes.add(name)

    def remove_class(self, name: str) -> None:
        self.classes.discard(name)


class _ChromeStub(_ScreenStub):
    """Same as _ScreenStub but stubs out the Textual widget lookups
    so _sync_worktree_mode_chrome can run."""

    def __init__(self, base_dir: Path, *, prefill=None, input_value="", name_value="") -> None:
        super().__init__(base_dir, prefill=prefill, input_value=input_value, name_value=name_value)
        self._fake_input = _FakeInput(input_value)
        self._fake_box = _FakeBox()

    def query_one(self, selector: str, _typ):
        if selector == "#new_input":
            return self._fake_input
        if selector == "#new_top":
            return self._fake_box
        raise LookupError(selector)


def test_switching_source_from_worktree_clears_auto_prefill(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    auto_path = str(tmp_path / "foo" / "repo")
    screen = _ChromeStub(
        tmp_path,
        prefill={"source": "worktree", "from_project": "foo"},
        input_value=auto_path,
    )
    screen._auto_input_value = auto_path
    screen._fake_input.value = auto_path
    screen._sync_worktree_mode_chrome()
    # In worktree mode: chrome class added, placeholder set, disabled
    # (because prefill_from_project locks the field).
    assert "worktree-mode" in screen._fake_box.classes
    assert "parent repo path" in screen._fake_input.placeholder
    assert screen._fake_input.disabled is True

    # Switch source away from worktree → auto-prefilled value clears,
    # chrome resets, field becomes editable again.
    screen.source_index = screen.source_choices.index("empty")
    # The screen still reports worktree mode because prefill_from_project
    # is set — toggling source manually shouldn't override an explicit
    # action prefill. Remove the prefill to simulate ctrl+n flow.
    screen.prefill_from_project = ""
    screen._sync_worktree_mode_chrome()
    assert "worktree-mode" not in screen._fake_box.classes
    assert screen._fake_input.placeholder == "URL / path / bare name"
    assert screen._fake_input.disabled is False
    assert screen._fake_input.value == ""


def test_switching_back_to_worktree_restores_auto_path(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    auto_path = str(tmp_path / "foo" / "repo")
    screen = _ChromeStub(
        tmp_path,
        prefill={"source": "empty"},
        input_value="",
    )
    screen._auto_input_value = auto_path
    # Simulate user picking worktree from the source picker.
    screen.source_index = screen.source_choices.index("worktree")
    screen._sync_worktree_mode_chrome()
    assert screen._fake_input.value == auto_path
    assert "worktree-mode" in screen._fake_box.classes
