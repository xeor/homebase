from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from homebase.tmux import commands as tmux_commands


def _write_profile(dir_path: Path, *, windows: list | None = None) -> Path:
    profile = dir_path / ".tmuxp.yaml"
    if windows is None:
        windows = [{"window_name": "w1"}]
    payload_lines = ["windows:"]
    for w in windows:
        payload_lines.append("  - {}".format(w))
    profile.write_text("\n".join(payload_lines) + "\n")
    return profile


def test_cmd_tmux_load_returns_error_outside_tmux(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_profile(tmp_path)
    monkeypatch.delenv("TMUX", raising=False)
    rc = tmux_commands.cmd_tmux_load(
        str(tmp_path),
        action_cancel="cancel",
        tmux=lambda *_args: "",
        tmux_run=lambda *_args: None,
        choose_load_mode=lambda _count: "new",
        load_profile_window=lambda _profile: ("@1", None),
    )
    assert rc == 1


def test_cmd_tmux_load_rejects_multi_window_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_profile(tmp_path, windows=[{"window_name": "a"}, {"window_name": "b"}])
    monkeypatch.setenv("TMUX", "/tmp/tmux:1,0")
    rc = tmux_commands.cmd_tmux_load(
        str(tmp_path),
        action_cancel="cancel",
        tmux=lambda *_args: "main",
        tmux_run=lambda *_args: None,
        choose_load_mode=lambda _count: "new",
        load_profile_window=lambda _profile: ("@1", None),
    )
    assert rc == 1


def _fake_tmux_factory(values: dict[str, str]) -> callable:
    def tmux(*args: str) -> str:
        # args are passed as positional strings; use the format-message text to key on
        joined = " ".join(args)
        for key, val in values.items():
            if key in joined:
                return val
        return ""

    return tmux


def test_cmd_tmux_load_cancel_mode_returns_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_profile(tmp_path)
    monkeypatch.setenv("TMUX", "/tmp/tmux:1,0")
    tmux = _fake_tmux_factory(
        {"session_name": "main", "window_id": "@7", "window_index": "3", "window_panes": "1"}
    )
    rc = tmux_commands.cmd_tmux_load(
        str(tmp_path),
        action_cancel="cancel",
        tmux=tmux,
        tmux_run=lambda *_args: None,
        choose_load_mode=lambda _count: "cancel",
        load_profile_window=lambda _profile: ("@9", None),
    )
    assert rc == 0
    assert "cancelled" in capsys.readouterr().out


def test_cmd_tmux_load_new_mode_selects_new_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_profile(tmp_path)
    monkeypatch.setenv("TMUX", "/tmp/tmux:1,0")
    tmux = _fake_tmux_factory(
        {"session_name": "main", "window_id": "@7", "window_index": "3", "window_panes": "1"}
    )
    calls: list[tuple[str, ...]] = []

    def tmux_run(*args: str) -> None:
        calls.append(args)

    rc = tmux_commands.cmd_tmux_load(
        str(tmp_path),
        action_cancel="cancel",
        tmux=tmux,
        tmux_run=tmux_run,
        choose_load_mode=lambda _count: "new",
        load_profile_window=lambda _profile: ("@9", "loaded x"),
    )
    assert rc == 0
    assert ("select-window", "-t", "@9") in calls


def test_cmd_tmux_load_overwrite_mode_moves_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_profile(tmp_path)
    monkeypatch.setenv("TMUX", "/tmp/tmux:1,0")
    tmux = _fake_tmux_factory(
        {"session_name": "main", "window_id": "@7", "window_index": "3", "window_panes": "1"}
    )
    calls: list[tuple[str, ...]] = []
    rc = tmux_commands.cmd_tmux_load(
        str(tmp_path),
        action_cancel="cancel",
        tmux=tmux,
        tmux_run=lambda *args: calls.append(args),
        choose_load_mode=lambda _count: "overwrite",
        load_profile_window=lambda _profile: ("@9", None),
    )
    assert rc == 0
    assert ("move-window", "-k", "-s", "@9", "-t", "main:3") in calls
    assert ("select-window", "-t", "main:3") in calls


def test_cmd_tmux_load_merge_mode_joins_panes_and_tiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_profile(tmp_path)
    monkeypatch.setenv("TMUX", "/tmp/tmux:1,0")

    def tmux(*args: str) -> str:
        joined = " ".join(args)
        if "session_name" in joined:
            return "main"
        if "window_id" in joined:
            return "@cur"
        if "window_index" in joined:
            return "2"
        if "window_panes" in joined:
            return "2"
        if "list-panes" in args:
            return "%5\n%6\n"
        return ""

    calls: list[tuple[str, ...]] = []
    rc = tmux_commands.cmd_tmux_load(
        str(tmp_path),
        action_cancel="cancel",
        tmux=tmux,
        tmux_run=lambda *args: calls.append(args),
        choose_load_mode=lambda _count: "merge",
        load_profile_window=lambda _profile: ("@new", None),
    )
    assert rc == 0
    assert ("join-pane", "-s", "%5", "-t", "@cur") in calls
    assert ("join-pane", "-s", "%6", "-t", "@cur") in calls
    assert ("select-layout", "-t", "@cur", "tiled") in calls


def test_cmd_tmux_load_merge_mode_failure_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_profile(tmp_path)
    monkeypatch.setenv("TMUX", "/tmp/tmux:1,0")

    def tmux(*args: str) -> str:
        joined = " ".join(args)
        if "session_name" in joined:
            return "main"
        if "window_id" in joined:
            return "@cur"
        if "window_index" in joined:
            return "2"
        if "window_panes" in joined:
            return "2"
        if "list-panes" in args:
            return "%5\n"
        return ""

    def tmux_run(*_args: str) -> None:
        raise subprocess.SubprocessError("join failed")

    rc = tmux_commands.cmd_tmux_load(
        str(tmp_path),
        action_cancel="cancel",
        tmux=tmux,
        tmux_run=tmux_run,
        choose_load_mode=lambda _count: "merge",
        load_profile_window=lambda _profile: ("@new", None),
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "merge failed" in err


def test_tmux_open_new_tab_returns_1_on_subprocess_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(_cmd, **_kw):
        return subprocess.CompletedProcess(_cmd, returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(tmux_commands.subprocess, "run", fake_run)
    rc = tmux_commands.tmux_open_new_tab(tmp_path, tmux_command_prefix=lambda: ["tmux"])
    assert rc == 1


def test_tmux_open_new_tab_selects_window_when_returned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **_kw):
        calls.append(list(cmd))
        # First call (new-window) returns "@99"; subsequent select-window returns ok
        if "new-window" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="@99\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(tmux_commands.subprocess, "run", fake_run)
    rc = tmux_commands.tmux_open_new_tab(tmp_path, tmux_command_prefix=lambda: ["tmux"])
    assert rc == 0
    assert any("select-window" in c for c in calls)


def test_open_with_mode_uses_goto_loaded_pane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TMUX", "/tmp/tmux:1,0")
    profiles = [
        {
            "id": "loaded",
            "use_tmux": True,
            "run_load": True,
            "goto_loaded": True,
            "fallback_cd": True,
        }
    ]
    calls: list[list[str]] = []
    monkeypatch.setattr(
        tmux_commands.subprocess,
        "run",
        lambda cmd, **_kw: calls.append(list(cmd)) or subprocess.CompletedProcess(cmd, 0),
    )
    rc = tmux_commands.open_with_mode(
        tmp_path,
        tmp_path / "p",
        load_open_mode_config=lambda _b: {"profile": "loaded"},
        open_mode_default_profile="loaded",
        open_mode_profiles=profiles,
        open_shell_in_dir=lambda _p: 99,
        tmux_find_pane_for_cwd=lambda _p: ("%5", "@7"),
        tmux_command_prefix=lambda: ["tmux"],
        tmux_open_new_tab_with_load=lambda _p: 88,
        tmux_open_new_tab=lambda _p: 77,
    )
    assert rc == 0
    flat = [arg for cmd in calls for arg in cmd]
    assert "select-window" in flat
    assert "select-pane" in flat


def test_open_with_mode_run_load_when_goto_loaded_misses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TMUX", "/tmp/tmux:1,0")
    profiles = [
        {
            "id": "loaded",
            "use_tmux": True,
            "run_load": True,
            "goto_loaded": True,
            "fallback_cd": True,
        }
    ]
    rc = tmux_commands.open_with_mode(
        tmp_path,
        tmp_path / "p",
        load_open_mode_config=lambda _b: {"profile": "loaded"},
        open_mode_default_profile="loaded",
        open_mode_profiles=profiles,
        open_shell_in_dir=lambda _p: 99,
        tmux_find_pane_for_cwd=lambda _p: None,
        tmux_command_prefix=lambda: ["tmux"],
        tmux_open_new_tab_with_load=lambda _p: 88,
        tmux_open_new_tab=lambda _p: 77,
    )
    assert rc == 88


def test_print_save_diagnostics_header_prints_versions_and_env(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(tmux_commands, "_tool_version", lambda b: f"{b}@v0.0")
    monkeypatch.setenv("TMUX", "/tmp/x:1,0")
    monkeypatch.setenv("TMUX_PANE", "%42")
    tmux_commands.print_save_diagnostics_header("%pane-h", "$session-h")
    out = capsys.readouterr().out
    assert "tmux@v0.0" in out
    assert "tmuxp@v0.0" in out
    assert "TMUX=/tmp/x:1,0" in out
    assert "TMUX_PANE=%42" in out
    assert "%pane-h" in out
    assert "$session-h" in out


def test_cmd_tmux_save_outside_tmux_with_pause_shows_banner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(tmux_commands, "_wait_for_enter", lambda: None)
    monkeypatch.setattr(tmux_commands, "_tool_version", lambda _b: "stub")
    rc = tmux_commands.cmd_tmux_save(
        tmp_path,
        pause=True,
        tmux_list_sessions=lambda: [],
        tmux_resolve_session_window=lambda _p, _s: ({}, {}),
        tmux_list_panes=lambda _w: [],
        resolve_project_root_from_panes=lambda _d, _b: (tmp_path, {}),
        pane_best_run_command_debug=lambda _p: {},
        tmux_display=lambda _v: "",
        tmux_save_debug_snapshot=lambda _s: [],
        resolve_tmux_save_output=lambda _r, _root: tmp_path / ".tmuxp.yaml",
        tmux_notify=lambda *_a: None,
        format_error=lambda exc: str(exc),
    )
    # pause-mode swallows the error code and returns 0 after presenting the banner
    assert rc == 0
    captured = capsys.readouterr()
    assert "not running inside a tmux session" in captured.out
