from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from homebase.core import setup_tools as setup_tools
from homebase.core.setup_model import (
    INTENT_ABSENT,
    INTENT_CANNOT_REMOVE,
    INTENT_CREATE,
    INTENT_KEEP,
    INTENT_REMOVE,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_WARN,
    FixResult,
    SetupCheck,
    SetupContext,
    SetupFix,
)

# --- pure helpers ---------------------------------------------------


def test_compact_path_for_display_uses_tilde() -> None:
    home = Path.home()
    out = setup_tools.compact_path_for_display(str(home / "x"))
    assert out.startswith("~")


def test_shell_init_target_paths() -> None:
    home = Path.home()
    assert setup_tools._shell_init_target_for_shell("fish") == (
        home / ".config/fish/conf.d/b.fish"
    )
    assert setup_tools._shell_init_target_for_shell("bash") == (
        home / ".local/share/homebase/shell-init.bash"
    )
    assert setup_tools._shell_init_target_for_shell("zsh") == (
        home / ".local/share/homebase/shell-init.zsh"
    )
    assert setup_tools._shell_init_target_for_shell("powershell") is None


def test_shell_init_installed_detects_present_and_missing(tmp_path: Path) -> None:
    fish_target = tmp_path / "conf.d" / "b.fish"
    fish_target.parent.mkdir(parents=True)
    body = "# script\nfunction b\n  ...\nend\n"
    fish_target.write_text(body)
    assert setup_tools._shell_init_installed("fish", body, fish_target, None)
    fish_target.write_text("stale")
    assert not setup_tools._shell_init_installed("fish", body, fish_target, None)

    bash_target = tmp_path / "share" / "homebase" / "shell-init.bash"
    bash_target.parent.mkdir(parents=True)
    bash_target.write_text(body)
    rc = tmp_path / ".bashrc"
    line = setup_tools._shell_init_source_line("bash", bash_target)
    rc.write_text("# user stuff\n" + line + "\nmore stuff\n")
    assert setup_tools._shell_init_installed("bash", body, bash_target, rc)
    rc.write_text("# user stuff only\n")
    assert not setup_tools._shell_init_installed("bash", body, bash_target, rc)


def test_has_any_tmux_save_binding_detects_bind_line() -> None:
    text = 'bind-key t run-shell -b "uv run --script b.py b tmux save"\n'
    assert setup_tools.has_any_tmux_save_binding(text) is True


def test_tmux_save_binding_lines_returns_only_binding_lines() -> None:
    text = "\n".join(
        [
            "# comment",
            'bind-key t run-shell -b "uv run --script b.py b tmux save"',
            'bind-key x run-shell -b "echo hi"',
            'bind t run-shell -b "uv run --script b.py b tmux save"',
        ]
    )
    out = setup_tools.tmux_save_binding_lines(text)
    assert len(out) == 2
    assert all("b tmux save" in line for line in out)


def test_recommended_tmux_save_binding_contains_expected_parts() -> None:
    line = setup_tools.recommended_tmux_save_binding(Path("/tmp/b"), "/usr/bin/uv", "/usr/bin/tmux")
    assert "TMUX_BIN=" in line
    assert "tmux save" in line


def test_state_text_labels() -> None:
    assert setup_tools._state_text("PASS") == "already configured"
    assert setup_tools._state_text("WARN") == "needs change"
    assert setup_tools._state_text("FAIL") == "missing"


# --- remove helpers --------------------------------------------------


def test_remove_homebase_gitignore_rule_drops_matching_line(tmp_path: Path) -> None:
    p = tmp_path / ".gitignore"
    p.write_text("cache.sqlite3\nfoo.log\n")
    setup_tools._remove_homebase_gitignore_rule(p)
    assert p.read_text() == "foo.log\n"


def test_remove_homebase_gitignore_rule_deletes_file_when_empty(tmp_path: Path) -> None:
    p = tmp_path / ".gitignore"
    p.write_text("cache.sqlite3\n")
    setup_tools._remove_homebase_gitignore_rule(p)
    assert not p.exists()


def test_remove_tmux_binding_keeps_other_lines(tmp_path: Path) -> None:
    p = tmp_path / ".tmux.conf"
    p.write_text(
        "set -g mouse on\n"
        "bind-key t run-shell -b 'b tmux save ...'\n"
        "bind-key x run-shell -b 'echo x'\n"
    )
    setup_tools._remove_tmux_binding(p)
    text = p.read_text()
    assert "set -g mouse on" in text
    assert "bind-key x" in text
    assert "b tmux save" not in text


def test_remove_shell_init_source_line_drops_line(tmp_path: Path) -> None:
    rc = tmp_path / ".zshrc"
    line = '[ -f "$HOME/foo" ] && . "$HOME/foo"  # homebase shell integration'
    rc.write_text("# top\n" + line + "\n# bottom\n")
    setup_tools._remove_shell_init_source_line(rc, line)
    text = rc.read_text()
    assert line not in text
    assert "# top" in text
    assert "# bottom" in text


# --- print fix execution summary -------------------------------------


def _result(rid: str, intent: str, *, success: bool = True, error: str | None = None) -> FixResult:
    return FixResult(id=rid, title=rid.upper(), intent=intent, success=success, error=error)


def test_print_fix_execution_summary_shows_plan_then_results(capsys) -> None:
    setup_tools._print_fix_execution_summary(
        [
            _result("a", INTENT_CREATE),
            _result("b", INTENT_REMOVE, success=False, error="boom"),
            _result("c", INTENT_KEEP),
        ],
        dry_run=False,
    )
    out = capsys.readouterr().out
    assert "plan: create=1 remove=1 keep=1" in out
    assert "results: succeeded=1 failed=1" in out
    assert "created:" in out
    assert "removed:" in out
    assert "failures:" in out
    assert "boom" in out


def test_print_fix_execution_summary_dry_run_skips_results(capsys) -> None:
    setup_tools._print_fix_execution_summary(
        [_result("a", INTENT_CREATE), _result("b", INTENT_ABSENT)],
        dry_run=True,
    )
    out = capsys.readouterr().out
    assert "plan: create=1 remove=0 keep=0" in out
    assert "results:" not in out


# --- selection & apply -----------------------------------------------


def _make_fix(
    fid: str,
    *,
    required: bool = False,
    recommended: bool = False,
    currently_present: bool = False,
    currently_correct: bool = False,
    apply_create=lambda: None,
    apply_remove=None,
    requires: tuple[str, ...] = (),
) -> SetupFix:
    return SetupFix(
        id=fid,
        title=fid.upper(),
        description="desc",
        currently_present=currently_present,
        currently_correct=currently_correct,
        required=required,
        recommended=recommended,
        apply_create=apply_create,
        apply_remove=apply_remove,
        requires=requires,
    )


def test_select_fix_ids_prompt_fallback_selects_expected() -> None:
    fixes = [
        _make_fix("a", required=True, currently_correct=False),
        _make_fix("b", required=False, recommended=False),  # default unselected
    ]

    def _prompt(question: str, default: bool) -> bool:
        _ = default
        return "A" in question

    selected = setup_tools._select_fix_ids(
        fixes, select_fix_ids_fn=None, prompt_yes_no=_prompt,
    )
    assert selected == {"a"}


def test_apply_intents_runs_create_for_absent_recommended_selected(capsys) -> None:
    calls = {"a": 0}

    def _make_a() -> None:
        calls["a"] += 1

    fixes = [_make_fix("a", recommended=True, apply_create=_make_a)]
    results = setup_tools._apply_intents(fixes, {"a"}, dry_run=False)
    _ = capsys.readouterr()
    assert results[0].intent == INTENT_CREATE
    assert results[0].success is True
    assert calls["a"] == 1


def test_apply_intents_runs_remove_for_present_unselected(capsys) -> None:
    calls = {"a": 0}

    def _rm() -> None:
        calls["a"] += 1

    fixes = [_make_fix(
        "a",
        currently_present=True, currently_correct=True,
        apply_create=lambda: None, apply_remove=_rm,
    )]
    results = setup_tools._apply_intents(fixes, set(), dry_run=False)
    _ = capsys.readouterr()
    assert results[0].intent == INTENT_REMOVE
    assert results[0].success is True
    assert calls["a"] == 1


def test_apply_intents_keeps_correct_items_as_noop(capsys) -> None:
    calls = {"a": 0}

    def _create() -> None:
        calls["a"] += 1

    fixes = [_make_fix(
        "a", currently_present=True, currently_correct=True,
        apply_create=_create, apply_remove=lambda: None,
    )]
    results = setup_tools._apply_intents(fixes, {"a"}, dry_run=False)
    _ = capsys.readouterr()
    assert results[0].intent == INTENT_KEEP
    assert calls["a"] == 0


def test_apply_intents_warns_when_no_apply_remove(capsys) -> None:
    fixes = [_make_fix(
        "a", currently_present=True, currently_correct=True,
        apply_create=lambda: None, apply_remove=None,
    )]
    results = setup_tools._apply_intents(fixes, set(), dry_run=False)
    err = capsys.readouterr().err
    assert results[0].intent == INTENT_CANNOT_REMOVE
    assert results[0].success is False
    assert "cannot uninstall" in err or "cannot uninstall" in results[0].error


def test_apply_intents_collects_create_failures(capsys) -> None:
    def _boom() -> None:
        raise OSError("disk full")

    fixes = [_make_fix("a", recommended=True, apply_create=_boom)]
    results = setup_tools._apply_intents(fixes, {"a"}, dry_run=False)
    _ = capsys.readouterr()
    assert results[0].intent == INTENT_CREATE
    assert results[0].success is False
    assert "disk full" in (results[0].error or "")


# --- summary ---------------------------------------------------------


def test_compute_summary_marks_hard_fail_on_required_check_fail() -> None:
    checks = [
        SetupCheck(id="x", name="x", status=STATUS_FAIL, detail="d", required=True),
    ]
    summary = setup_tools._compute_summary(checks, [], dry_run=False)
    assert summary.hard_fail is True


def test_compute_summary_marks_hard_fail_on_fix_failure() -> None:
    summary = setup_tools._compute_summary(
        [],
        [_result("a", INTENT_CREATE, success=False, error="boom")],
        dry_run=False,
    )
    assert summary.hard_fail is True
    assert summary.failed_count == 1


def test_compute_summary_does_not_hard_fail_when_only_warns_present() -> None:
    checks = [
        SetupCheck(id="x", name="x", status=STATUS_WARN, detail="d", required=False),
        SetupCheck(id="y", name="y", status=STATUS_PASS, detail="d", required=True),
    ]
    summary = setup_tools._compute_summary(checks, [], dry_run=False)
    assert summary.hard_fail is False
    assert summary.warn_count == 1
    assert summary.pass_count == 1


def test_compute_summary_counts_create_remove_keep() -> None:
    summary = setup_tools._compute_summary(
        [],
        [
            _result("a", INTENT_CREATE),
            _result("b", INTENT_REMOVE),
            _result("c", INTENT_KEEP),
            _result("d", INTENT_CREATE),
        ],
        dry_run=False,
    )
    assert summary.create_count == 2
    assert summary.remove_count == 1
    assert summary.keep_count == 1


# --- self-update detection ------------------------------------------


def test_self_update_check_includes_diagnostics_when_unclear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(setup_tools.sys, "executable", "/tmp/custom/python")
    ctx = _basic_context()
    ctx = replace(ctx, update_cmd="", update_detail="install mode unclear")
    check = setup_tools._self_update_check(ctx)
    assert check.status == STATUS_WARN
    joined = "\n".join(check.extra_lines)
    assert "self-update diagnostics" in joined
    assert "launcher:" in joined
    assert "python:" in joined


def test_detect_self_update_for_local_repo(tmp_path: Path) -> None:
    (tmp_path / "src" / "homebase").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='homebase'\n")
    detail, cmd = setup_tools._detect_self_update(tmp_path, None)
    assert "local editable" in detail
    assert "uv tool install --editable" in cmd


def test_detect_self_update_for_uv_tool_path(tmp_path: Path) -> None:
    detail, cmd = setup_tools._detect_self_update(
        tmp_path,
        Path("/Users/me/.local/share/uv/tools/homebase/bin/b"),
    )
    assert "uv tool" in detail
    assert cmd == "uv tool upgrade homebase"


def test_detect_self_update_for_uv_tool_python_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(setup_tools.sys, "executable", "/Users/me/.local/share/uv/tools/homebase/bin/python")
    detail, cmd = setup_tools._detect_self_update(tmp_path, None)
    assert "uv tool runtime" in detail
    assert cmd == "uv tool upgrade homebase"


def test_detect_self_update_for_site_packages_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(setup_tools.sys, "executable", "/venv/lib/python3.11/site-packages/bin/python")
    detail, cmd = setup_tools._detect_self_update(tmp_path, None)
    assert "python environment install" in detail
    assert cmd == "python -m pip install -U homebase"


# --- tmux helpers ---------------------------------------------------


def test_write_tmux_binding_appends_when_missing(tmp_path: Path) -> None:
    conf = tmp_path / ".tmux.conf"
    conf.write_text("set -g mouse on\n")
    expected = "bind-key t run-shell -b 'uv run --script /tmp/b tmux save'"
    setup_tools.write_tmux_binding(conf, expected)
    text = conf.read_text()
    assert "set -g mouse on" in text
    assert expected in text


def test_write_tmux_binding_replaces_existing_save_bind(tmp_path: Path) -> None:
    conf = tmp_path / ".tmux.conf"
    conf.write_text(
        "set -g mouse on\n"
        "bind-key t run-shell -b 'old b tmux save command'\n"
        "bind-key x run-shell -b 'echo x'\n"
    )
    expected = "bind-key t run-shell -b 'new b tmux save command'"
    setup_tools.write_tmux_binding(conf, expected)
    lines = conf.read_text().splitlines()
    assert expected in lines
    assert not any("old b tmux save command" in line for line in lines)
    assert any("bind-key x" in line for line in lines)


# --- build_fixes shape -----------------------------------------------


def test_build_fixes_emits_every_item_with_state_metadata(tmp_path: Path) -> None:
    ctx = _ctx_for_fixes(tmp_path)
    fixes = setup_tools._build_fixes(ctx)
    ids = {fx.id for fx in fixes}
    # the canonical set is always present, regardless of current state
    assert {
        "base_folder", "homebase_dir", "local_bin", "launcher_symlink",
        "gitignore_cache", "tmux_binding",
        "shell_completion", "shell_init",
    } <= ids
    # self_update has been moved off the fix list (it lives in its tab)
    assert "self_update" not in ids
    # every fix tells us about itself
    for fx in fixes:
        assert fx.title
        assert fx.description
        assert fx.current_state_text


def test_base_folder_fix_has_no_apply_remove(tmp_path: Path) -> None:
    ctx = _ctx_for_fixes(tmp_path)
    fixes = {fx.id: fx for fx in setup_tools._build_fixes(ctx)}
    base = fixes["base_folder"]
    assert base.required
    assert base.apply_create is not None
    assert base.apply_remove is None  # never auto-uninstall the workspace


def test_local_bin_fix_has_no_apply_remove(tmp_path: Path) -> None:
    ctx = _ctx_for_fixes(tmp_path)
    fixes = {fx.id: fx for fx in setup_tools._build_fixes(ctx)}
    assert fixes["local_bin"].apply_remove is None


def test_launcher_symlink_fix_supports_remove(tmp_path: Path) -> None:
    ctx = _ctx_for_fixes(tmp_path)
    fixes = {fx.id: fx for fx in setup_tools._build_fixes(ctx)}
    assert fixes["launcher_symlink"].apply_remove is not None


def test_build_fixes_apply_targets_are_isolated(tmp_path: Path) -> None:
    """Regression: each fix's apply_create must touch only its own
    target. An earlier refactor accidentally shared closure variables
    across fixes, causing the launcher symlink to point at shell-init.zsh."""
    ctx = _ctx_for_fixes(tmp_path)
    fixes = setup_tools._build_fixes(ctx)
    by_id = {fx.id: fx for fx in fixes}

    # apply the leaf-level create transitions in build order
    for fid in (
        "base_folder", "homebase_dir", "local_bin",
        "launcher_symlink", "gitignore_cache", "tmux_binding",
        "shell_completion", "shell_init",
    ):
        by_id[fid].apply_create()

    real_target = ctx.target
    assert ctx.dest.is_symlink()
    assert ctx.dest.resolve() == real_target.resolve()
    assert ctx.completion_target.read_text() == ctx.expected_completion
    assert ctx.shell_init_target.read_text() == ctx.expected_shell_init
    assert ctx.expected_tmux_binding in ctx.tmux_conf_path.read_text()


def test_order_fixes_respects_requires() -> None:
    fixes = [
        _make_fix("launcher", required=True, requires=("local_bin",)),
        _make_fix("local_bin", required=True),
        _make_fix("tmux"),
    ]
    ordered = setup_tools._order_fixes(fixes)
    ids = [fx.id for fx in ordered]
    assert ids.index("local_bin") < ids.index("launcher")


def test_order_fixes_detects_cycle() -> None:
    fixes = [
        _make_fix("a", requires=("b",)),
        _make_fix("b", requires=("a",)),
    ]
    with pytest.raises(ValueError, match="cycle"):
        setup_tools._order_fixes(fixes)


# --- cmd_setup end-to-end --------------------------------------------


def test_cmd_setup_return_code_warns_do_not_fail(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    bin_dir = tmp_path / "bin"
    base_dir.mkdir()
    bin_dir.mkdir()
    (bin_dir / "b").write_text("#!/bin/sh\n")
    (base_dir / ".homebase").mkdir()
    (base_dir / ".homebase" / ".gitignore").write_text("cache.sqlite3\n")

    home = tmp_path / "home"
    home.mkdir()
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    (local_bin / "b").symlink_to((bin_dir / "b").resolve())

    monkeypatch.setattr(setup_tools.Path, "home", lambda: home)
    monkeypatch.setattr(
        setup_tools,
        "find_executable",
        lambda name, extra_candidates=(): "/usr/bin/x" if name in {"uv", "git", "tmux"} else None,
    )
    monkeypatch.setattr(setup_tools, "_runtime_imports_ok", lambda: (True, "ok"))
    monkeypatch.setenv("PATH", f"{local_bin}:/usr/bin")

    rc = setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=(),
        prompt_yes_no=lambda _q, d: d,
    )
    assert rc == 0


def test_cmd_setup_return_code_missing_required_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    bin_dir = tmp_path / "bin"
    base_dir.mkdir()
    bin_dir.mkdir()
    (bin_dir / "b").write_text("#!/bin/sh\n")

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(setup_tools.Path, "home", lambda: home)
    monkeypatch.setattr(setup_tools, "find_executable", lambda _name, extra_candidates=(): None)
    monkeypatch.setattr(setup_tools, "_runtime_imports_ok", lambda: (False, "missing deps"))
    monkeypatch.setenv("PATH", "/usr/bin")

    rc = setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=(),
        prompt_yes_no=lambda _q, _d: False,
    )
    assert rc == 1


def test_cmd_setup_uses_selected_fix_ids_callback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    bin_dir = tmp_path / "bin"
    base_dir.mkdir()
    bin_dir.mkdir()
    (bin_dir / "b").write_text("#!/bin/sh\n")

    home = tmp_path / "home"
    home.mkdir()
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    launcher = local_bin / "b"
    launcher.write_text("not a symlink\n")

    monkeypatch.setattr(setup_tools.Path, "home", lambda: home)
    monkeypatch.setattr(
        setup_tools,
        "find_executable",
        lambda name, extra_candidates=(): "/usr/bin/x" if name in {"uv", "git", "tmux"} else None,
    )
    monkeypatch.setattr(setup_tools, "_runtime_imports_ok", lambda: (True, "ok"))
    monkeypatch.setenv("PATH", f"{local_bin}:/usr/bin")

    def _select_only_launcher_and_base(fixes):
        return {fx.id for fx in fixes if fx.id in {"launcher_symlink", "local_bin"}}

    rc = setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=(),
        prompt_yes_no=lambda _q, _d: False,
        select_fix_ids_fn=_select_only_launcher_and_base,
    )
    # launcher fix runs; but base_folder and .homebase are still required → rc=1
    assert rc == 1
    assert launcher.is_symlink()


def test_cmd_setup_returns_fail_when_selected_fix_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    base_dir = tmp_path / "base"
    bin_dir = tmp_path / "bin"
    base_dir.mkdir()
    bin_dir.mkdir()
    (bin_dir / "b").write_text("#!/bin/sh\n")
    (base_dir / ".homebase").mkdir()
    (base_dir / ".homebase" / ".gitignore").write_text("cache.sqlite3\n")

    home = tmp_path / "home"
    home.mkdir()
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    (local_bin / "b").symlink_to((bin_dir / "b").resolve())

    monkeypatch.setattr(setup_tools.Path, "home", lambda: home)
    monkeypatch.setattr(
        setup_tools,
        "find_executable",
        lambda name, extra_candidates=(): "/usr/bin/x" if name in {"uv", "git", "tmux", "tmuxp"} else None,
    )
    monkeypatch.setattr(setup_tools, "_runtime_imports_ok", lambda: (True, "ok"))
    monkeypatch.setenv("PATH", f"{local_bin}:/usr/bin")

    def _boom(*_args, **_kwargs):
        raise OSError("write failed")

    monkeypatch.setattr(setup_tools, "write_tmux_binding", _boom)

    rc = setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=(),
        prompt_yes_no=lambda _q, _d: False,
        select_fix_ids_fn=lambda fixes: {fix.id for fix in fixes if fix.id == "tmux_binding"},
    )
    assert rc == 1


def test_cmd_setup_offers_to_install_shell_init(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    base_dir = tmp_path / "base"
    bin_dir = tmp_path / "bin"
    base_dir.mkdir()
    bin_dir.mkdir()
    (bin_dir / "b").write_text("#!/bin/sh\n")
    (base_dir / ".homebase").mkdir()
    (base_dir / ".homebase" / ".gitignore").write_text("cache.sqlite3\n")

    home = tmp_path / "home"
    home.mkdir()
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    (local_bin / "b").symlink_to((bin_dir / "b").resolve())

    monkeypatch.setattr(setup_tools.Path, "home", lambda: home)
    monkeypatch.setattr(
        setup_tools,
        "find_executable",
        lambda name, extra_candidates=(): "/usr/bin/x"
        if name in {"uv", "git", "tmux"} else None,
    )
    monkeypatch.setattr(setup_tools, "_runtime_imports_ok", lambda: (True, "ok"))
    monkeypatch.setenv("PATH", f"{local_bin}:/usr/bin")
    monkeypatch.setenv("SHELL", "/usr/local/bin/bash")

    expected_wrapper = "# wrapper body\nb() { :; }\n"
    rc = setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=(),
        prompt_yes_no=lambda _q, _d: True,
        completion_script_fn=lambda _s: "# completion\n",
        shell_init_script_fn=lambda _s: expected_wrapper,
    )
    assert rc == 0
    init_target = home / ".local/share/homebase/shell-init.bash"
    assert init_target.is_file()
    assert init_target.read_text() == expected_wrapper
    bashrc = home / ".bashrc"
    assert bashrc.is_file()
    assert "homebase shell integration" in bashrc.read_text()


def test_cmd_setup_fixes_wrong_symlink_target(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    bin_dir = tmp_path / "bin"
    old_bin_dir = tmp_path / "oldbin"
    base_dir.mkdir()
    bin_dir.mkdir()
    old_bin_dir.mkdir()
    (bin_dir / "b").write_text("#!/bin/sh\n")
    (old_bin_dir / "b").write_text("#!/bin/sh\n")
    (base_dir / ".homebase").mkdir()
    (base_dir / ".homebase" / ".gitignore").write_text("cache.sqlite3\n")

    home = tmp_path / "home"
    home.mkdir()
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    launcher = local_bin / "b"
    launcher.symlink_to((old_bin_dir / "b").resolve())

    monkeypatch.setattr(setup_tools.Path, "home", lambda: home)
    monkeypatch.setattr(
        setup_tools,
        "find_executable",
        lambda name, extra_candidates=(): "/usr/bin/x" if name in {"uv", "git", "tmux"} else None,
    )
    monkeypatch.setattr(setup_tools, "_runtime_imports_ok", lambda: (True, "ok"))
    monkeypatch.setenv("PATH", f"{local_bin}:/usr/bin")

    rc = setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=(),
        prompt_yes_no=lambda _q, _d: True,
    )
    assert rc == 0
    assert launcher.is_symlink()
    assert launcher.resolve() == (bin_dir / "b").resolve()


def test_cmd_setup_renames_plain_launcher_file_before_symlink(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base_dir = tmp_path / "base"
    bin_dir = tmp_path / "bin"
    base_dir.mkdir()
    bin_dir.mkdir()
    (bin_dir / "b").write_text("#!/bin/sh\n")
    (base_dir / ".homebase").mkdir()
    (base_dir / ".homebase" / ".gitignore").write_text("cache.sqlite3\n")

    home = tmp_path / "home"
    home.mkdir()
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    launcher = local_bin / "b"
    launcher.write_text("not a symlink\n")

    monkeypatch.setattr(setup_tools.Path, "home", lambda: home)
    monkeypatch.setattr(
        setup_tools,
        "find_executable",
        lambda name, extra_candidates=(): "/usr/bin/x" if name in {"uv", "git", "tmux"} else None,
    )
    monkeypatch.setattr(setup_tools, "_runtime_imports_ok", lambda: (True, "ok"))
    monkeypatch.setenv("PATH", f"{local_bin}:/usr/bin")

    rc = setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=(),
        prompt_yes_no=lambda _q, _d: True,
    )
    assert rc == 0
    assert launcher.is_symlink()
    backups = list(local_bin.glob("b.bak-*"))
    assert len(backups) == 1


def test_cmd_setup_dry_run_does_not_modify_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    bin_dir = tmp_path / "bin"
    base_dir.mkdir()
    bin_dir.mkdir()
    (bin_dir / "b").write_text("#!/bin/sh\n")

    home = tmp_path / "home"
    home.mkdir()
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)

    monkeypatch.setattr(setup_tools.Path, "home", lambda: home)
    monkeypatch.setattr(
        setup_tools,
        "find_executable",
        lambda name, extra_candidates=(): "/usr/bin/x" if name in {"uv", "git", "tmux"} else None,
    )
    monkeypatch.setattr(setup_tools, "_runtime_imports_ok", lambda: (True, "ok"))
    monkeypatch.setenv("PATH", f"{local_bin}:/usr/bin")

    rc = setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=(),
        prompt_yes_no=lambda _q, _d: True,
        dry_run=True,
    )
    assert rc == 1
    assert not (base_dir / ".homebase").exists()
    assert not (local_bin / "b").exists()


def test_cmd_setup_missing_config_is_warning_not_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base_dir = tmp_path / "base"
    bin_dir = tmp_path / "bin"
    base_dir.mkdir()
    bin_dir.mkdir()
    (bin_dir / "b").write_text("#!/bin/sh\n")
    (base_dir / ".homebase").mkdir()
    (base_dir / ".homebase" / ".gitignore").write_text("cache.sqlite3\n")

    home = tmp_path / "home"
    home.mkdir()
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    (local_bin / "b").symlink_to((bin_dir / "b").resolve())

    monkeypatch.setattr(setup_tools.Path, "home", lambda: home)
    monkeypatch.setattr(
        setup_tools,
        "find_executable",
        lambda name, extra_candidates=(): "/usr/bin/x" if name in {"uv", "git", "tmux"} else None,
    )
    monkeypatch.setattr(setup_tools, "_runtime_imports_ok", lambda: (True, "ok"))
    monkeypatch.setenv("PATH", f"{local_bin}:/usr/bin")

    rc = setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=(),
        prompt_yes_no=lambda _q, d: d,
    )
    assert rc == 0


# --- json output, report persistence --------------------------------


def test_cmd_setup_json_output_is_pure_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    base_dir = tmp_path / "base"
    bin_dir = tmp_path / "bin"
    base_dir.mkdir()
    bin_dir.mkdir()
    (bin_dir / "b").write_text("#!/bin/sh\n")
    (base_dir / ".homebase").mkdir()
    (base_dir / ".homebase" / ".gitignore").write_text("cache.sqlite3\n")

    home = tmp_path / "home"
    home.mkdir()
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    (local_bin / "b").symlink_to((bin_dir / "b").resolve())

    monkeypatch.setattr(setup_tools.Path, "home", lambda: home)
    monkeypatch.setattr(
        setup_tools,
        "find_executable",
        lambda name, extra_candidates=(): "/usr/bin/x" if name in {"uv", "git", "tmux"} else None,
    )
    monkeypatch.setattr(setup_tools, "_runtime_imports_ok", lambda: (True, "ok"))
    monkeypatch.setenv("PATH", f"{local_bin}:/usr/bin")

    rc = setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=(),
        prompt_yes_no=lambda _q, _d: False,
        select_fix_ids_fn=lambda _fixes: set(),
        json_output=True,
    )
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert "checks" in payload
    assert "fixes" in payload
    fix_block = payload["fixes"]["available"]
    assert any(fx["id"] == "base_folder" for fx in fix_block)
    assert any(fx["id"] == "launcher_symlink" for fx in fix_block)
    assert all("currently_present" in fx for fx in fix_block)
    assert all("supports_create" in fx for fx in fix_block)


def test_cmd_setup_persists_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base_dir = tmp_path / "base"
    bin_dir = tmp_path / "bin"
    base_dir.mkdir()
    bin_dir.mkdir()
    (bin_dir / "b").write_text("#!/bin/sh\n")
    (base_dir / ".homebase").mkdir()
    (base_dir / ".homebase" / ".gitignore").write_text("cache.sqlite3\n")

    home = tmp_path / "home"
    home.mkdir()
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    (local_bin / "b").symlink_to((bin_dir / "b").resolve())

    monkeypatch.setattr(setup_tools.Path, "home", lambda: home)
    monkeypatch.setattr(
        setup_tools,
        "find_executable",
        lambda name, extra_candidates=(): "/usr/bin/x" if name in {"uv", "git", "tmux"} else None,
    )
    monkeypatch.setattr(setup_tools, "_runtime_imports_ok", lambda: (True, "ok"))
    monkeypatch.setenv("PATH", f"{local_bin}:/usr/bin")

    rc = setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=(),
        prompt_yes_no=lambda _q, d: d,
    )
    assert rc == 0
    report = base_dir / ".homebase" / setup_tools.SETUP_REPORT_FILE_NAME
    assert report.is_file()
    payload = json.loads(report.read_text())
    assert payload["summary"]["exit_code"] == 0


# --- helpers used by parametric tests --------------------------------


def _basic_context() -> SetupContext:
    home = Path("/tmp/home")
    base = Path("/tmp/base")
    return SetupContext(
        base_dir=base,
        bin_dir=Path("/tmp/bin"),
        homebase_dir=base / ".homebase",
        config_path=base / ".homebase/config.yaml",
        homebase_gitignore=base / ".homebase/.gitignore",
        target=Path("/tmp/bin/b"),
        dest_dir=home / ".local/bin",
        dest=home / ".local/bin/b",
        launcher_path=None,
        uv_bin=None,
        git_bin=None,
        tmux_bin=None,
        tmuxp_bin=None,
        runtime_ok=True,
        runtime_detail="ok",
        in_path=True,
        tmux_conf_path=home / ".tmux.conf",
        tmux_conf_text="",
        expected_tmux_binding="bind-key t",
        existing_tmux_binding_lines=(),
        completion_shell="",
        completion_target=None,
        expected_completion="",
        completion_ok=False,
        shell_init_target=None,
        shell_init_rc=None,
        expected_shell_init="",
        shell_init_ok=False,
        update_cmd="",
        update_detail="",
        config_exists=False,
        config_valid=True,
    )


def _ctx_for_fixes(tmp_path: Path) -> SetupContext:
    base = tmp_path / "base"
    base.mkdir()
    homebase_dir = base / ".homebase"
    dest_dir = tmp_path / "bin"
    dest = dest_dir / "b"
    target = tmp_path / "target-b"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("#!/bin/sh\n")
    return SetupContext(
        base_dir=base,
        bin_dir=dest_dir,
        homebase_dir=homebase_dir,
        config_path=homebase_dir / "config.yaml",
        homebase_gitignore=homebase_dir / ".gitignore",
        target=target,
        dest_dir=dest_dir,
        dest=dest,
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
        expected_tmux_binding="bind-key t run-shell -b 'b tmux save expected'",
        existing_tmux_binding_lines=(),
        completion_shell="zsh",
        completion_target=tmp_path / "completion/_b",
        expected_completion="# completion script\n",
        completion_ok=False,
        shell_init_target=tmp_path / "init/shell-init.zsh",
        shell_init_rc=tmp_path / ".zshrc",
        expected_shell_init="# init script\n",
        shell_init_ok=False,
        update_cmd="uv tool upgrade homebase",
        update_detail="detected",
        config_exists=False,
        config_valid=True,
    )


def test_write_homebase_gitignore_adds_cache_rule_once(tmp_path: Path) -> None:
    path = tmp_path / ".gitignore"
    setup_tools._write_homebase_gitignore(path)
    setup_tools._write_homebase_gitignore(path)
    lines = path.read_text().splitlines()
    assert lines == ["cache.sqlite3"]
