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
    (project / ".base.yaml").write_text("tags: []\nrepo_dir: repo\n", encoding="utf-8")
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
        self._fake_name = _FakeInput(name_value)
        self._fake_box = _FakeBox()

    def query_one(self, selector: str, _typ):
        if selector == "#new_input":
            return self._fake_input
        if selector == "#new_name":
            return self._fake_name
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


# ============================================================
# Edge cases: dir name + status lines + validation should match
# what WorktreeSource actually creates. The user reported that the
# dialog's status panel was showing 'name: featx' / 'path: <base>/
# featx' when the real worktree lands at <base>/foo-featx/. These
# tests pin every transformation that produces the displayed text.
# ============================================================


def test_status_lines_match_real_dir_name(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree", "from_project": "foo"},
        input_value=str(tmp_path / "foo" / "repo"),
        name_value="featx",
    )
    lines, dir_name, target = screen._worktree_status_lines()
    assert dir_name == "foo-featx"
    assert target == tmp_path / "foo-featx"
    text = "\n".join(lines)
    assert "parent[/]: [cyan]foo[/]" in text
    assert "branch[/]: [cyan]featx[/]" in text
    assert "dir name[/]: foo-featx" in text
    assert str(tmp_path / "foo-featx") in text
    assert str(tmp_path / "foo-featx" / "repo") in text


def test_status_lines_error_path_shows_reason(tmp_path: Path) -> None:
    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree"},
        input_value="",
        name_value="featx",
    )
    lines, dir_name, target = screen._worktree_status_lines()
    assert target is None
    assert dir_name == ""
    assert "worktree invalid" in lines[0]
    assert "parent repo path required" in lines[0]


def test_target_existing_dir_marks_exists_yes(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    (tmp_path / "foo-featx").mkdir()
    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree", "from_project": "foo"},
        input_value=str(tmp_path / "foo" / "repo"),
        name_value="featx",
    )
    # Validation flags the collision via the err string, so the
    # status panel routes through the invalid branch (no exists
    # row). dir_name still computed for the err message.
    _dir, err = screen._worktree_validation()
    assert err == "target exists: foo-featx"


def test_branch_with_multiple_slashes_sanitises_each(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree", "from_project": "foo"},
        input_value=str(tmp_path / "foo" / "repo"),
        name_value="feat/api/v2",
    )
    dir_name, err = screen._worktree_validation()
    assert err == ""
    assert dir_name == "foo-feat--api--v2"


def test_path_with_trailing_slash_resolves(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree"},
        input_value=str(tmp_path / "foo" / "repo") + "/",
        name_value="featx",
    )
    dir_name, err = screen._worktree_validation()
    assert err == ""
    assert dir_name == "foo-featx"


def test_path_relative_resolves_under_base(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    # User types just 'foo' or 'foo/repo' (relative); validator
    # joins under base_dir_ref.
    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree"},
        input_value="foo/repo",
        name_value="featx",
    )
    dir_name, err = screen._worktree_validation()
    assert err == ""
    assert dir_name == "foo-featx"


def test_path_at_project_root_with_repo_subdir(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree"},
        input_value=str(tmp_path / "foo"),
        name_value="featx",
    )
    dir_name, err = screen._worktree_validation()
    assert err == ""
    assert dir_name == "foo-featx"


def test_path_outside_base_is_rejected(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    proj = elsewhere / "foo"
    repo = proj / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    base = tmp_path / "base"
    base.mkdir()
    screen = _ScreenStub(
        base,
        prefill={"source": "worktree"},
        input_value=str(repo),
        name_value="featx",
    )
    _dir, err = screen._worktree_validation()
    assert "parent must live under base" in err


def test_empty_branch_field_is_required(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree"},
        input_value=str(tmp_path / "foo" / "repo"),
        name_value="   ",
    )
    _dir, err = screen._worktree_validation()
    assert "branch name required" in err


def test_plan_steps_include_git_worktree_add(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree", "from_project": "foo"},
        input_value=str(tmp_path / "foo" / "repo"),
        name_value="featx",
    )
    target = tmp_path / "foo-featx"
    steps = screen._plan_steps_lines("worktree", target)
    text = "\n".join(steps)
    assert "git -C <foo/repo> worktree add -b featx" in text
    assert "/foo-featx/repo" in text
    assert "worktree block + repo_dir" in text


def test_dir_name_prefix_uses_root_parent_not_intermediate(tmp_path: Path) -> None:
    # Build a worktree row 'foo-a' under foo. Now point the dialog
    # at foo-a's repo and pick a new branch — the dir_name must use
    # the ROOT parent name 'foo', not the intermediate 'foo-a'.
    _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["a", "--as", "worktree", "--from", "foo"]) == 0

    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree"},
        input_value=str(tmp_path / "foo-a" / "repo"),
        name_value="b",
    )
    dir_name, err = screen._worktree_validation()
    assert err == ""
    assert dir_name == "foo-b"


def test_dir_name_does_not_double_prefix_when_branch_starts_with_parent(tmp_path: Path) -> None:
    # User picks a branch literally named 'foo-something' under
    # parent 'foo'. The dir name still gets the canonical prefix —
    # no special-casing to detect the redundancy.
    _init_project_repo(tmp_path, "foo")
    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree", "from_project": "foo"},
        input_value=str(tmp_path / "foo" / "repo"),
        name_value="foo-things",
    )
    dir_name, err = screen._worktree_validation()
    assert err == ""
    assert dir_name == "foo-foo-things"


def test_branch_with_dots_and_dashes_unchanged_in_dir(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree", "from_project": "foo"},
        input_value=str(tmp_path / "foo" / "repo"),
        name_value="v1.2-rc",
    )
    dir_name, err = screen._worktree_validation()
    assert err == ""
    assert dir_name == "foo-v1.2-rc"


def test_invalid_path_returns_empty_parent_name(tmp_path: Path) -> None:
    screen = _ScreenStub(
        tmp_path,
        prefill={"source": "worktree"},
        input_value="/no/such/path",
        name_value="featx",
    )
    # Path doesn't exist → derived parent name is empty; validation
    # short-circuits with 'parent path does not exist'.
    assert screen._derived_worktree_parent_name() == ""
    _dir, err = screen._worktree_validation()
    assert "parent path does not exist" in err
    assert "/no/such/path" in err


# ============================================================
# Source-change confirm guard. When the dialog was opened via the
# worktree action (prefill_from_project pinned the path + locked the
# input field), switching to a different source must NOT silently
# wipe state — confirm_destructive intercepts and only resets after
# explicit user acceptance.
# ============================================================


class _GuardStub(_ChromeStub):
    """Stub that intercepts push_screen so we can drive the confirm
    callback synchronously from tests, mirroring the real flow."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.pushed: list[tuple[object, object]] = []

    def push_screen(self, screen, callback) -> None:  # type: ignore[override]
        self.pushed.append((screen, callback))


def test_source_change_from_worktree_with_prefill_prompts_confirm(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    auto_path = str(tmp_path / "foo" / "repo")
    screen = _GuardStub(
        tmp_path,
        prefill={"source": "worktree", "from_project": "foo"},
        input_value=auto_path,
    )
    screen._auto_input_value = auto_path
    screen._fake_input.value = auto_path
    screen._fake_input.disabled = True

    # Bypass _refresh's widget queries.
    screen._refresh = lambda: None
    screen._set_section_focus = lambda: None

    # Attempt to switch to 'empty' — must prompt, not mutate yet.
    empty_idx = screen.source_choices.index("empty")
    screen._set_source_index(empty_idx)
    assert len(screen.pushed) == 1
    assert screen.source_index == screen.source_choices.index("worktree")
    assert screen.prefill_from_project == "foo"
    assert screen._fake_input.disabled is True


def test_confirm_yes_resets_prefill_and_applies_source_change(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    auto_path = str(tmp_path / "foo" / "repo")
    screen = _GuardStub(
        tmp_path,
        prefill={"source": "worktree", "from_project": "foo"},
        input_value=auto_path,
        name_value="featx",
    )
    screen._auto_input_value = auto_path
    screen._fake_input.value = auto_path
    screen._fake_input.disabled = True
    screen._refresh = lambda: None
    screen._set_section_focus = lambda: None

    empty_idx = screen.source_choices.index("empty")
    screen._set_source_index(empty_idx)
    _screen_obj, callback = screen.pushed[-1]
    callback(True)

    assert screen.source_index == empty_idx
    assert screen.prefill_from_project == ""
    assert screen._auto_input_value == ""
    assert screen._fake_input.value == ""
    assert screen._fake_input.disabled is False
    assert screen._last_was_worktree is False


def test_confirm_no_leaves_source_and_prefill_alone(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    auto_path = str(tmp_path / "foo" / "repo")
    screen = _GuardStub(
        tmp_path,
        prefill={"source": "worktree", "from_project": "foo"},
        input_value=auto_path,
    )
    screen._auto_input_value = auto_path
    screen._fake_input.value = auto_path
    screen._fake_input.disabled = True
    screen._refresh = lambda: None
    screen._set_section_focus = lambda: None

    initial_idx = screen.source_index
    empty_idx = screen.source_choices.index("empty")
    screen._set_source_index(empty_idx)
    _screen_obj, callback = screen.pushed[-1]
    callback(False)

    assert screen.source_index == initial_idx
    assert screen.prefill_from_project == "foo"
    assert screen._fake_input.value == auto_path
    assert screen._fake_input.disabled is True


def test_source_change_without_prefill_skips_the_confirm(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    screen = _GuardStub(
        tmp_path,
        prefill={"source": "worktree"},  # no from_project → no lock
        input_value="",
    )
    screen._refresh = lambda: None
    screen._set_section_focus = lambda: None

    empty_idx = screen.source_choices.index("empty")
    screen._set_source_index(empty_idx)
    # No confirm pushed; the change applies immediately.
    assert screen.pushed == []
    assert screen.source_index == empty_idx


def test_source_change_into_worktree_does_not_prompt(tmp_path: Path) -> None:
    # ctrl+n flow with no prefill — picking 'worktree' for the
    # first time should never prompt because there's no state to
    # lose. The guard only triggers when LEAVING worktree+prefill.
    _init_project_repo(tmp_path, "foo")
    screen = _GuardStub(
        tmp_path,
        prefill=None,
        input_value="",
    )
    screen._refresh = lambda: None
    screen._set_section_focus = lambda: None

    wt_idx = screen.source_choices.index("worktree")
    screen._set_source_index(wt_idx)
    assert screen.pushed == []
    assert screen.source_index == wt_idx
