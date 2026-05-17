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


def test_run_setup_app_returns_none_when_textual_missing(
    monkeypatch, tmp_path: Path
) -> None:
    real_import = __import__

    def _block_textual(name, *args, **kwargs):
        if name.startswith("textual"):
            raise ImportError("forced")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _block_textual)
    result = setup_app.run_setup_app(_ctx(tmp_path), [], [])
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
