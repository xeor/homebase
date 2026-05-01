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
