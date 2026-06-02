from __future__ import annotations

import types
from pathlib import Path

import pytest

from homebase.tmux import commands as tmux_commands


def test_list_window_ids_parses_non_empty_rows() -> None:
    out = tmux_commands.list_window_ids(tmux=lambda *_args: "@1\n\n @2 \n")
    assert out == {"@1", "@2"}


def test_choose_load_mode_returns_cancel_on_none() -> None:
    mode = tmux_commands.choose_load_mode(
        2,
        action_cancel="cancel",
        prompt_readline=lambda *_args, **_kwargs: None,
        is_interactive=True,
    )
    assert mode == "cancel"


def test_choose_load_mode_non_interactive_invalid_choice_cancels() -> None:
    mode = tmux_commands.choose_load_mode(
        2,
        action_cancel="cancel",
        prompt_readline=lambda *_args, **_kwargs: "x",
        is_interactive=False,
    )
    assert mode == "cancel"


def test_cmd_tmux_load_returns_error_when_profile_missing(tmp_path: Path) -> None:
    rc = tmux_commands.cmd_tmux_load(
        str(tmp_path),
        action_cancel="cancel",
        tmux=lambda *_args: "",
        tmux_run=lambda *_args: None,
        choose_load_mode=lambda _count: "new",
        load_profile_window=lambda _profile: ("@1", None),
    )
    assert rc == 1


def test_open_new_tab_with_load_status_falls_back_without_tmuxp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tmux_commands.shutil, "which", lambda _name: None)
    rc, status = tmux_commands.open_new_tab_with_load_status(
        tmp_path,
        load_profile_window=lambda _profile: ("@1", "loaded workspace: x"),
        tmux_run=lambda *_args: None,
        tmux_open_new_tab=lambda _path: 7,
    )
    assert rc == 7
    assert status is None


def test_tmux_save_debug_snapshot_contains_windows_and_panes() -> None:
    snap = tmux_commands.tmux_save_debug_snapshot(
        [{"session_id": "$1", "session_name": "main", "session_activity": "0", "session_attached": "1"}],
        tmux_list_windows=lambda _sid: [{"window_id": "@1", "window_name": "w", "window_active": "1"}],
        tmux_list_panes=lambda _wid: [{"pane_id": "%1"}],
    )
    assert snap[0]["session_name"] == "main"
    assert snap[0]["windows"][0]["window_id"] == "@1"


def test_cmd_tmux_save_returns_error_outside_tmux(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    rc = tmux_commands.cmd_tmux_save(
        tmp_path,
        tmux_list_sessions=lambda: [],
        tmux_resolve_session_window=lambda _pane, _session: ({}, {}),
        tmux_list_panes=lambda _wid: [],
        resolve_project_root_from_panes=lambda _dirs, _base: (tmp_path, {}),
        pane_best_run_command_debug=lambda _pane: {},
        tmux_display=lambda _value: "",
        tmux_save_debug_snapshot=lambda _sessions: [],
        resolve_tmux_save_output=lambda _raw, _root: tmp_path / ".tmuxp.yaml",
        tmux_notify=lambda _message, _pane_id, _delay_ms: None,
        format_error=lambda exc: str(exc),
    )
    assert rc == 1


def test_find_panes_for_cwd_matches_and_sorts(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    target.mkdir(parents=True)
    sub = target / "sub"
    sub.mkdir()
    other = tmp_path / "other"
    other.mkdir()

    raw = "\n".join(
        [
            f"%2\ts:2.0\tw\tvim\t{sub}\t0",
            f"%1\ts:1.0\tw\tbash\t{target}\t1",
            f"%9\ts:9.0\tw\tbash\t{other}\t1",
        ]
    )

    out = tmux_commands.find_panes_for_cwd(
        target,
        tmux=lambda *_args: raw,
        is_under=lambda path, root: str(path).startswith(str(root)),
        pane_ref_factory=lambda **kwargs: types.SimpleNamespace(**kwargs),
    )

    assert [p.pane_id for p in out] == ["%1", "%2"]


def test_open_with_mode_returns_shell_when_not_tmux(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    opened: list[Path] = []

    rc = tmux_commands.open_with_mode(
        tmp_path,
        tmp_path / "proj",
        load_open_mode_config=lambda _base: {"profile": "tmux_tab"},
        open_mode_default_profile="shell_cd",
        open_mode_profiles=[
            {
                "id": "tmux_tab",
                "use_tmux": True,
                "run_load": False,
                "goto_loaded": False,
                "fallback_cd": True,
            }
        ],
        open_shell_in_dir=lambda p: (opened.append(p) or 0),
        tmux_find_pane_for_cwd=lambda _path: None,
        tmux_command_prefix=lambda: ["tmux"],
        tmux_open_new_tab_with_load=lambda _path: 2,
        tmux_open_new_tab=lambda _path: 3,
    )

    assert rc == 0
    assert opened == [tmp_path / "proj"]


def test_choose_load_mode_single_pane_overwrite() -> None:
    assert (
        tmux_commands.choose_load_mode(
            1,
            action_cancel="cancel",
            prompt_readline=lambda *_a, **_k: "1",
            is_interactive=True,
        )
        == "overwrite"
    )


def test_choose_load_mode_explicit_choices_map() -> None:
    pairs = [("1", "overwrite"), ("2", "new"), ("3", "merge"), ("4", "cancel")]
    for raw, expected in pairs:
        out = tmux_commands.choose_load_mode(
            3,
            action_cancel="cancel",
            prompt_readline=lambda *_a, _raw=raw, **_k: _raw,
            is_interactive=True,
        )
        assert out == expected


def test_open_new_tab_with_load_status_uses_tmuxp_when_available(
    tmp_path: Path, monkeypatch
) -> None:
    profile = tmp_path / ".tmuxp.yaml"
    profile.write_text("session_name: x\nwindows: []\n")
    monkeypatch.setattr(tmux_commands.shutil, "which", lambda _name: "/usr/bin/tmuxp")

    selected: list[tuple[str, ...]] = []
    rc, status = tmux_commands.open_new_tab_with_load_status(
        tmp_path,
        load_profile_window=lambda _p: ("@1", "loaded workspace: x"),
        tmux_run=lambda *args: selected.append(args),
        tmux_open_new_tab=lambda _p: 99,
    )
    assert rc == 0
    assert status == "loaded workspace: x"
    assert selected[0] == ("select-window", "-t", "@1")


def test_open_new_tab_with_load_status_falls_back_on_error(
    tmp_path: Path, monkeypatch
) -> None:
    profile = tmp_path / ".tmuxp.yaml"
    profile.write_text("x\n")
    monkeypatch.setattr(tmux_commands.shutil, "which", lambda _name: "/usr/bin/tmuxp")

    def boom(_profile: Path) -> tuple[str, str | None]:
        raise OSError("nope")

    rc, status = tmux_commands.open_new_tab_with_load_status(
        tmp_path,
        load_profile_window=boom,
        tmux_run=lambda *_a: None,
        tmux_open_new_tab=lambda _p: 1,
    )
    assert rc == 1
    assert status is None


def test_open_new_tab_with_load_wraps_status() -> None:
    rc = tmux_commands.open_new_tab_with_load(
        Path("/tmp"),
        open_new_tab_with_load_status=lambda _p: (5, "ignored"),
    )
    assert rc == 5


def test_find_pane_for_cwd_returns_first_match(tmp_path: Path) -> None:
    import types as types_mod

    pane = types_mod.SimpleNamespace(
        pane_id="%9", target="main:1.0", window_name="w", command="vim",
        cwd=tmp_path, active=True,
    )
    out = tmux_commands.find_pane_for_cwd(
        tmp_path,
        tmux_find_panes_for_cwd=lambda _t: [pane],
    )
    assert out == ("%9", "main:1")


def test_find_pane_for_cwd_returns_none_when_empty(tmp_path: Path) -> None:
    out = tmux_commands.find_pane_for_cwd(
        tmp_path,
        tmux_find_panes_for_cwd=lambda _t: [],
    )
    assert out is None


def test_find_panes_for_cwd_handles_tmux_error() -> None:
    import subprocess

    def boom(*_args: str) -> str:
        raise subprocess.SubprocessError("nope")

    out = tmux_commands.find_panes_for_cwd(
        Path("/tmp"),
        tmux=boom,
        is_under=lambda _p, _r: False,
        pane_ref_factory=lambda **kw: kw,
    )
    assert out == []


def test_open_with_mode_uses_shell_when_use_tmux_false(tmp_path: Path) -> None:
    opened: list[Path] = []
    rc = tmux_commands.open_with_mode(
        tmp_path,
        tmp_path / "proj",
        load_open_mode_config=lambda _b: {"profile": "shell_cd"},
        open_mode_default_profile="shell_cd",
        open_mode_profiles=[{"id": "shell_cd", "use_tmux": False}],
        open_shell_in_dir=lambda p: (opened.append(p), 0)[1],
        tmux_find_pane_for_cwd=lambda _p: None,
        tmux_command_prefix=lambda: ["tmux"],
        tmux_open_new_tab_with_load=lambda _p: 99,
        tmux_open_new_tab=lambda _p: 1,
    )
    assert rc == 0
    assert opened == [tmp_path / "proj"]


def test_open_with_mode_falls_back_to_tmux_open_new_tab(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TMUX", "/tmp/sock,1,2")
    rc = tmux_commands.open_with_mode(
        tmp_path,
        tmp_path / "proj",
        load_open_mode_config=lambda _b: {"profile": "tmux_tab"},
        open_mode_default_profile="tmux_tab",
        open_mode_profiles=[
            {
                "id": "tmux_tab",
                "use_tmux": True,
                "run_load": False,
                "goto_loaded": False,
                "fallback_cd": False,
            }
        ],
        open_shell_in_dir=lambda _p: 0,
        tmux_find_pane_for_cwd=lambda _p: None,
        tmux_command_prefix=lambda: ["tmux"],
        tmux_open_new_tab_with_load=lambda _p: 1,
        tmux_open_new_tab=lambda _p: 77,
    )
    assert rc == 77


def test_open_with_mode_uses_run_load(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TMUX", "/tmp/sock,1,2")
    rc = tmux_commands.open_with_mode(
        tmp_path,
        tmp_path / "proj",
        load_open_mode_config=lambda _b: {"profile": "tmux_load"},
        open_mode_default_profile="tmux_load",
        open_mode_profiles=[
            {
                "id": "tmux_load",
                "use_tmux": True,
                "run_load": True,
                "goto_loaded": False,
                "fallback_cd": False,
            }
        ],
        open_shell_in_dir=lambda _p: 0,
        tmux_find_pane_for_cwd=lambda _p: None,
        tmux_command_prefix=lambda: ["tmux"],
        tmux_open_new_tab_with_load=lambda _p: 5,
        tmux_open_new_tab=lambda _p: 6,
    )
    assert rc == 5


def test_open_with_mode_requires_tmux_when_no_fallback(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    rc = tmux_commands.open_with_mode(
        tmp_path,
        tmp_path / "proj",
        load_open_mode_config=lambda _b: {"profile": "tmux_tab"},
        open_mode_default_profile="tmux_tab",
        open_mode_profiles=[
            {
                "id": "tmux_tab",
                "use_tmux": True,
                "run_load": False,
                "goto_loaded": False,
                "fallback_cd": False,
            }
        ],
        open_shell_in_dir=lambda _p: 0,
        tmux_find_pane_for_cwd=lambda _p: None,
        tmux_command_prefix=lambda: ["tmux"],
        tmux_open_new_tab_with_load=lambda _p: 1,
        tmux_open_new_tab=lambda _p: 2,
    )
    assert rc == 1
    assert "requires tmux session" in capsys.readouterr().err


def test_open_with_mode_unknown_profile_falls_back_to_first(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    rc = tmux_commands.open_with_mode(
        tmp_path,
        tmp_path / "proj",
        load_open_mode_config=lambda _b: {"profile": "ghost"},
        open_mode_default_profile="shell_cd",
        open_mode_profiles=[
            {"id": "shell_cd", "use_tmux": False},
            {"id": "other", "use_tmux": True},
        ],
        open_shell_in_dir=lambda _p: 9,
        tmux_find_pane_for_cwd=lambda _p: None,
        tmux_command_prefix=lambda: ["tmux"],
        tmux_open_new_tab_with_load=lambda _p: 1,
        tmux_open_new_tab=lambda _p: 2,
    )
    assert rc == 9


def test_classify_save_error_known_paths(tmp_path: Path) -> None:
    headline, hint = tmux_commands.classify_save_error("not inside a tmux session")
    assert "tmux session" in headline
    assert "$TMUX" in hint or "manually" in hint

    headline, hint = tmux_commands.classify_save_error(
        "no pane start directories under base root", base_root=tmp_path / "base"
    )
    assert "outside your base" in headline

    headline, hint = tmux_commands.classify_save_error("no project root found")
    assert "no .base.yaml" in headline

    headline, hint = tmux_commands.classify_save_error("multiple project roots")
    assert "multiple projects" in headline

    headline, hint = tmux_commands.classify_save_error(
        "resolved active window has no panes"
    )
    assert "no panes" in headline

    headline, hint = tmux_commands.classify_save_error(
        "no pane start directories found"
    )
    assert "wedged" in hint

    headline, _hint = tmux_commands.classify_save_error("command not found")
    assert "missing" in headline


def test_classify_save_error_fallback() -> None:
    headline, hint = tmux_commands.classify_save_error("some random failure")
    assert "b tmux save failed" == headline
    assert hint == "some random failure"


def test_print_error_banner_includes_headline_and_hint(capsys) -> None:
    tmux_commands.print_error_banner("boom", "step 1\nstep 2")
    out = capsys.readouterr().out
    assert "boom" in out
    assert "step 1" in out
    assert "step 2" in out


def test_find_bin_uses_which_first(monkeypatch) -> None:
    monkeypatch.setattr(tmux_commands.shutil, "which", lambda _n: "/usr/bin/x")
    assert tmux_commands._find_bin("x") == "/usr/bin/x"


def test_find_bin_searches_prefixes(monkeypatch, tmp_path: Path) -> None:
    fake = tmp_path / "fakebin"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setattr(tmux_commands.shutil, "which", lambda _n: None)
    monkeypatch.setattr(
        tmux_commands, "_BIN_SEARCH_PREFIXES", (str(fake.parent),)
    )
    assert tmux_commands._find_bin("fakebin") == str(fake)


def test_find_bin_returns_none_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(tmux_commands.shutil, "which", lambda _n: None)
    monkeypatch.setattr(tmux_commands, "_BIN_SEARCH_PREFIXES", ())
    monkeypatch.setenv("HOME", "/no/such/home")
    assert tmux_commands._find_bin("ghost") is None


def test_tool_version_missing(monkeypatch) -> None:
    monkeypatch.setattr(tmux_commands, "_find_bin", lambda _n: None)
    assert tmux_commands._tool_version("ghost") == "MISSING"
