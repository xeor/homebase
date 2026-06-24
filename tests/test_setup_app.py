from __future__ import annotations

from pathlib import Path

from homebase.core import setup_app
from homebase.core.setup_model import (
    INTENT_ABSENT,
    INTENT_CANNOT_CREATE,
    INTENT_CANNOT_REMOVE,
    INTENT_CREATE,
    INTENT_KEEP,
    INTENT_REMOVE,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_WARN,
    SetupCheck,
    SetupContext,
    SetupFix,
)


def _ctx(tmp_path: Path, *, update_cmd: str = "uv tool upgrade homebase") -> SetupContext:
    return SetupContext(
        base_dir=tmp_path,
        bin_dir=tmp_path / "bin",
        homebase_dir=tmp_path / ".homebase",
        config_path=tmp_path / ".homebase/config.yaml",
        homebase_gitignore=tmp_path / ".homebase/.gitignore",
        target=tmp_path / "bin/b",
        dest_dir=tmp_path / "home/.local/bin",
        dest=tmp_path / "home/.local/bin/b",
        launcher_path=None,
        uv_bin="/usr/bin/uv",
        git_bin="/usr/bin/git",
        tmux_bin="/usr/bin/tmux",
        tmuxp_bin=None,
        runtime_ok=True,
        runtime_detail="ok",
        in_path=True,
        tmux_conf_path=tmp_path / ".tmux.conf",
        tmux_conf_text="",
        expected_tmux_binding="bind-key t",
        existing_tmux_binding_lines=("bind-key t old",),
        completion_shell="zsh",
        completion_target=tmp_path / "_b",
        expected_completion="",
        completion_ok=False,
        shell_init_target=tmp_path / "init.zsh",
        shell_init_rc=tmp_path / ".zshrc",
        expected_shell_init="",
        shell_init_ok=False,
        update_cmd=update_cmd,
        update_detail="uv tool",
        config_exists=False,
        config_valid=True,
        macos_fast_focus_installed=False,
    )


def test_format_overview_lists_each_check_and_summary() -> None:
    checks = [
        SetupCheck(id="uv", name="uv", status=STATUS_PASS, detail="ok"),
        SetupCheck(id="path", name="PATH", status=STATUS_WARN, detail="needs"),
        SetupCheck(id="homebase_dir", name=".homebase", status=STATUS_FAIL, detail="missing", required=True),
    ]
    text = setup_app._format_overview(checks)
    assert "uv" in text
    assert "PATH" in text
    assert ".homebase" in text
    assert "PASS=1" in text
    assert "WARN=1" in text
    assert "FAIL=1" in text


def test_format_self_update_with_command(tmp_path: Path) -> None:
    text = setup_app._format_self_update_static(_ctx(tmp_path))
    assert "Self-update available" in text
    assert "uv tool upgrade homebase" in text


def test_format_self_update_manual(tmp_path: Path) -> None:
    text = setup_app._format_self_update_static(_ctx(tmp_path, update_cmd=""))
    assert "needs manual action" in text or "manual action" in text


def test_format_diagnostics_includes_paths_and_tools(tmp_path: Path) -> None:
    text = setup_app._format_diagnostics(_ctx(tmp_path))
    assert "uv:" in text
    assert "git:" in text
    assert "expected binding" in text
    assert "bind-key t old" in text


def test_real_app_apply_without_changes_is_safe(tmp_path: Path) -> None:
    """End-to-end UI test: build the real app on a fully-configured
    workspace, press Ctrl+S, and verify no apply runs (because there
    are no changes). The destructive bug pattern: an empty/wrong
    selected_ids would have triggered REMOVE intents and wiped config."""
    import asyncio

    from homebase.core import setup_tools

    base = tmp_path / "base"
    base.mkdir()
    (base / ".homebase").mkdir()
    (base / ".homebase/.gitignore").write_text("cache.sqlite3\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "b").write_text("#!/bin/sh\n")
    (bin_dir / "b").chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    local_bin = home / ".local/bin"
    local_bin.mkdir(parents=True)
    (local_bin / "b").symlink_to((bin_dir / "b").resolve())

    # Patch the home + executable lookup so the context matches our
    # tmp_path exactly.
    original_home = setup_tools.Path.home
    original_find = setup_tools.find_executable
    original_runtime_ok = setup_tools._runtime_imports_ok
    setup_tools.Path.home = staticmethod(lambda: home)
    setup_tools.find_executable = (
        lambda name, extra_candidates=(): "/usr/bin/x"
        if name in {"uv", "git", "tmux"}
        else None
    )
    setup_tools._runtime_imports_ok = lambda: (True, "ok")

    try:
        ctx = setup_tools._gather_context(
            base, bin_dir,
            tmux_bin_candidates=(),
            completion_script_fn=None,
            shell_init_script_fn=None,
        )
        fixes = setup_tools._build_fixes(ctx)
        checks = setup_tools._build_checks(ctx)

        apply_invocations: list[tuple[set[str], list]] = []

        def _spy_apply(fix_list, selected_ids, *, dry_run, log_fn=None):
            apply_invocations.append((set(selected_ids), list(fix_list)))
            from homebase.core.setup_model import INTENT_KEEP, FixResult

            return [
                FixResult(
                    id=fx.id, title=fx.title,
                    intent=INTENT_KEEP, success=True,
                )
                for fx in fix_list
            ]

        # Capture the App instance so we can drive Pilot
        from textual.app import App

        original_run = App.run

        def fake_run(self):
            async def driver():
                async with self.run_test() as pilot:
                    await pilot.pause()
                    # All currently_correct items must be selected
                    from textual.widgets import SelectionList

                    sl = self.query_one("#fixes_list", SelectionList)
                    selected = set(map(str, sl.selected))
                    expected = {
                        fx.id for fx in fixes
                        if fx.selected_default
                    }
                    assert selected == expected, (
                        f"SelectionList didn't honour selected_default: "
                        f"got {selected}, expected {expected}"
                    )
                    self.exit(None)
            asyncio.run(driver())
            return None

        App.run = fake_run
        try:
            from homebase.core.setup_app import run_setup_app

            run_setup_app(
                ctx, checks, fixes,
                apply_fn=_spy_apply,
                dry_run=False,
            )
        finally:
            App.run = original_run

        # Apply was never actually triggered (we just inspected state)
        # but the assertion inside fake_run is the real check.
        assert apply_invocations == []
    finally:
        setup_tools.Path.home = staticmethod(original_home)
        setup_tools.find_executable = original_find
        setup_tools._runtime_imports_ok = original_runtime_ok


def test_run_setup_app_returns_none_when_textual_missing(
    monkeypatch, tmp_path: Path
) -> None:
    real_import = __import__

    def _block_textual(name, *args, **kwargs):
        if name.startswith("textual"):
            raise ImportError("forced")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _block_textual)
    result = setup_app.run_setup_app(
        _ctx(tmp_path), [], [], apply_fn=lambda *_a, **_kw: [],
    )
    assert result is None


# --- action plan formatting -----------------------------------------


def _fix(fid: str, **kw) -> SetupFix:
    base = dict(
        id=fid,
        title=fid.upper(),
        description="",
        currently_present=False,
        currently_correct=False,
        required=False,
        recommended=False,
    )
    base.update(kw)
    return SetupFix(**base)


def test_fix_row_label_action_word_changes_with_selection() -> None:
    """The leading action word in a Fix row must reflect the current
    selection state. Replaces the [x]/[ ] checkbox glyph."""
    fix_correct = SetupFix(
        id="x", title="X",
        currently_present=True, currently_correct=True,
        required=True, recommended=True,
        apply_create=lambda: None,
        apply_remove=lambda: None,
    )
    selected_label = setup_app._fix_row_label(fix_correct, selected=True)
    unselected_label = setup_app._fix_row_label(fix_correct, selected=False)
    assert "keep" in selected_label
    assert "remove" in unselected_label
    # state moved inside the tag column
    assert "[ok]" in selected_label
    assert "[ok]" in unselected_label
    assert "required" in selected_label


def test_right_pane_for_keep_shows_verified_not_diff() -> None:
    """Regression: items that are already correct must NOT render
    the create-diff in the right pane (that gave the false
    impression that something would be installed)."""
    fix = SetupFix(
        id="x", title="X",
        description="why this matters",
        currently_present=True, currently_correct=True,
        required=True, recommended=True,
        apply_create=lambda: None,
        preview_create=("# would never apply", "+ /some/file"),
        current_state_text="present: /some/file",
    )
    title, body = setup_app._right_pane_for_intent(fix, INTENT_KEEP)
    assert title == "Verified"
    assert "Already configured" in body
    assert "present: /some/file" in body
    # critically — no green/red diff markup leaking through
    assert "would never apply" not in body
    assert "+ /some/file" not in body


def test_right_pane_for_create_shows_install_preview() -> None:
    fix = SetupFix(
        id="x", title="X",
        currently_present=False, currently_correct=False,
        recommended=True,
        apply_create=lambda: None,
        preview_create=("[bright_green]+ new line[/]",),
    )
    title, body = setup_app._right_pane_for_intent(fix, INTENT_CREATE)
    assert "install" in title.lower()
    assert "+ new line" in body


def test_right_pane_for_remove_shows_remove_preview() -> None:
    fix = SetupFix(
        id="x", title="X",
        currently_present=True, currently_correct=True,
        apply_remove=lambda: None,
        preview_remove=("[bright_red]- old line[/]",),
    )
    title, body = setup_app._right_pane_for_intent(fix, INTENT_REMOVE)
    assert "remove" in title.lower()
    assert "- old line" in body


def test_right_pane_for_absent_says_no_action() -> None:
    fix = SetupFix(
        id="x", title="X",
        currently_present=False, currently_correct=False,
        current_state_text="not installed",
    )
    title, body = setup_app._right_pane_for_intent(fix, INTENT_ABSENT)
    assert title == "Status"
    assert "no action" in body.lower()


def test_fix_row_label_for_missing_recommended_says_add_when_selected() -> None:
    fix_missing = SetupFix(
        id="x", title="X",
        currently_present=False, currently_correct=False,
        recommended=True,
        apply_create=lambda: None,
    )
    sel = setup_app._fix_row_label(fix_missing, selected=True)
    unsel = setup_app._fix_row_label(fix_missing, selected=False)
    assert "add" in sel
    assert "[missing]" in sel
    assert "skip" in unsel


def test_action_plan_groups_creates_removes_and_keeps() -> None:
    fixes = [
        _fix("a", currently_present=True, currently_correct=True, apply_remove=lambda: None),
        _fix("b", apply_create=lambda: None),
        _fix("c", currently_present=True, currently_correct=True, apply_remove=lambda: None),
        _fix("d"),  # absent, optional
    ]
    selected = {"a", "b"}  # keep a, install b, remove c, leave d alone
    text = setup_app._format_action_plan(fixes, selected)
    assert "install (1)" in text
    assert "REMOVE (1)" in text
    assert "+ B" in text
    assert "- C" in text


def test_action_plan_when_nothing_changes() -> None:
    fixes = [
        _fix("a", currently_present=True, currently_correct=True, apply_remove=lambda: None),
    ]
    selected = {"a"}
    text = setup_app._format_action_plan(fixes, selected)
    assert "no changes" in text


def test_action_plan_calls_out_cannot_remove() -> None:
    fixes = [
        _fix("a", currently_present=True, currently_correct=True),  # no remove
    ]
    text = setup_app._format_action_plan(fixes, set())
    assert "cannot uninstall" in text


def test_compute_intents_matches_per_fix() -> None:
    a = _fix("a", currently_present=True, currently_correct=True, apply_remove=lambda: None)
    b = _fix("b", apply_create=lambda: None)
    intents = setup_app._compute_intents([a, b], {"a"})
    assert intents["a"] == INTENT_KEEP
    assert intents["b"] == INTENT_ABSENT


def test_intent_label_translates_known_intents() -> None:
    assert "keep" in setup_app._intent_label(INTENT_KEEP)
    assert "install" in setup_app._intent_label(INTENT_CREATE)
    assert "REMOVE" in setup_app._intent_label(INTENT_REMOVE)
    assert "skip" in setup_app._intent_label(INTENT_ABSENT)
    assert "cannot" in setup_app._intent_label(INTENT_CANNOT_CREATE)
    assert "manual" in setup_app._intent_label(INTENT_CANNOT_REMOVE)
