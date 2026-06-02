from __future__ import annotations

from pathlib import Path

import pytest

from homebase.tmux import core as tmux_core


def test_tmux_parse_rows_filters_bad_lines() -> None:
    raw = "a\tb\nc\td\te\n x\t y\n"
    assert tmux_core.tmux_parse_rows(raw, 2) == [["a", "b"], ["x", "y"]]


def test_first_token_basename_handles_shell_and_plain_split() -> None:
    assert tmux_core.first_token_basename("/usr/bin/python -m pytest") == "python"
    assert tmux_core.first_token_basename('"unterminated') == '"unterminated'


def test_resolve_tmux_save_output_defaults_to_project_file(tmp_path: Path) -> None:
    out = tmux_core.resolve_tmux_save_output("", tmp_path)
    assert out == tmp_path / ".tmuxp.yaml"


def test_format_error_prefers_message() -> None:
    err = RuntimeError("boom")
    assert tmux_core.format_error(err) == "RuntimeError: boom"


def test_resolve_project_root_from_panes_single_root(tmp_path: Path) -> None:
    base_root = tmp_path / "base"
    project = base_root / "proj"
    nested = project / "src"
    nested.mkdir(parents=True)

    def _is_under(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False

    def _find_marker_root_upward(path: Path) -> Path | None:
        cur = path.resolve()
        if _is_under(cur, project):
            return project
        return None

    resolved, debug = tmux_core.resolve_project_root_from_panes(
        [str(nested)],
        base_root,
        is_under=_is_under,
        find_marker_root_upward=_find_marker_root_upward,
    )

    assert resolved == project
    assert debug["resolved_project_root"] == str(project)


def test_resolve_project_root_from_panes_raises_on_multiple_roots(tmp_path: Path) -> None:
    base_root = tmp_path / "base"
    a = base_root / "a" / "x"
    b = base_root / "b" / "y"
    a.mkdir(parents=True)
    b.mkdir(parents=True)

    def _is_under(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False

    def _find_marker_root_upward(path: Path) -> Path | None:
        text = str(path.resolve())
        if "/a/" in text:
            return base_root / "a"
        if "/b/" in text:
            return base_root / "b"
        return None

    with pytest.raises(RuntimeError, match="multiple project roots"):
        tmux_core.resolve_project_root_from_panes(
            [str(a), str(b)],
            base_root,
            is_under=_is_under,
            find_marker_root_upward=_find_marker_root_upward,
        )


def test_tmux_socket_path_from_env_empty(monkeypatch) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    assert tmux_core.tmux_socket_path_from_env() == ""


def test_tmux_socket_path_from_env_strips_comma_suffix(monkeypatch) -> None:
    monkeypatch.setenv("TMUX", "/tmp/sock,123,4")
    assert tmux_core.tmux_socket_path_from_env() == "/tmp/sock"


def test_resolve_tmux_bin_uses_env_when_executable(tmp_path: Path, monkeypatch) -> None:
    fake = tmp_path / "fake-tmux"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("TMUX_BIN", str(fake))
    assert tmux_core.resolve_tmux_bin(()) == str(fake)


def test_resolve_tmux_bin_falls_back_to_which(monkeypatch) -> None:
    monkeypatch.delenv("TMUX_BIN", raising=False)
    monkeypatch.setattr(tmux_core.shutil, "which", lambda _name: "/opt/bin/tmux")
    assert tmux_core.resolve_tmux_bin(()) == "/opt/bin/tmux"


def test_resolve_tmux_bin_falls_back_to_candidates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TMUX_BIN", raising=False)
    monkeypatch.setattr(tmux_core.shutil, "which", lambda _name: None)
    bin_path = tmp_path / "candidate-tmux"
    bin_path.write_text("#!/bin/sh\n")
    bin_path.chmod(0o755)
    assert tmux_core.resolve_tmux_bin(("/no/such/tmux", str(bin_path))) == str(bin_path)


def test_resolve_tmux_bin_returns_default_string_when_nothing_works(monkeypatch) -> None:
    monkeypatch.delenv("TMUX_BIN", raising=False)
    monkeypatch.setattr(tmux_core.shutil, "which", lambda _name: None)
    assert tmux_core.resolve_tmux_bin(("/no/such/tmux",)) == "tmux"


def test_tmux_command_prefix_includes_socket(monkeypatch) -> None:
    monkeypatch.setenv("TMUX", "/tmp/sock,1,2")
    out = tmux_core.tmux_command_prefix(resolve_tmux_bin=lambda: "/bin/tmux")
    assert out == ["/bin/tmux", "-S", "/tmp/sock"]


def test_tmux_command_prefix_omits_socket_when_no_env(monkeypatch) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    out = tmux_core.tmux_command_prefix(resolve_tmux_bin=lambda: "/bin/tmux")
    assert out == ["/bin/tmux"]


def test_tmux_display_runs_command_and_returns_value() -> None:
    seen: list[tuple[str, ...]] = []

    def fake_tmux(*args: str) -> str:
        seen.append(args)
        return "session-1"

    out = tmux_core.tmux_display("#{session_id}", tmux=fake_tmux, target="$1")
    assert out == "session-1"
    assert seen[0][0:3] == ("display-message", "-p", "-t")


def test_tmux_display_returns_empty_on_exception() -> None:
    def fake_tmux(*_args: str) -> str:
        raise OSError("boom")

    assert tmux_core.tmux_display("#{session_id}", tmux=fake_tmux) == ""


def test_tmux_list_sessions_windows_panes_parsing() -> None:
    def fake_sessions(*_args: str) -> str:
        return "$0\tmain\t100\t1\n$1\twork\t200\t0\n"

    sessions = tmux_core.tmux_list_sessions(tmux=fake_sessions)
    assert sessions == [
        {"session_id": "$0", "session_name": "main", "session_activity": "100", "session_attached": "1"},
        {"session_id": "$1", "session_name": "work", "session_activity": "200", "session_attached": "0"},
    ]

    def fake_windows(*_args: str) -> str:
        return "@0\teditor\tlayout\t1\n"

    windows = tmux_core.tmux_list_windows("$0", tmux=fake_windows)
    assert windows[0]["window_id"] == "@0"

    def fake_panes(*_args: str) -> str:
        return "%0\t1234\t/dev/ttys000\tvim\t/proj\t1\n"

    panes = tmux_core.tmux_list_panes("@0", tmux=fake_panes)
    assert panes[0]["pane_current_command"] == "vim"


def test_tmux_find_window_by_pane_id_returns_match() -> None:
    def fake_tmux(*_args: str) -> str:
        return "%1\t$0\t@2\n%9\t$1\t@3\n"

    assert tmux_core.tmux_find_window_by_pane_id("%9", tmux=fake_tmux) == ("$1", "@3")
    assert tmux_core.tmux_find_window_by_pane_id("missing", tmux=fake_tmux) is None


def test_tmux_session_activity_handles_invalid_value() -> None:
    assert tmux_core.tmux_session_activity({"session_activity": "abc"}) == 0
    assert tmux_core.tmux_session_activity({"session_activity": "123"}) == 123
    assert tmux_core.tmux_session_activity({}) == 0


def test_tmux_active_window_prefers_display_message() -> None:
    windows = [
        {"window_id": "@1", "window_active": "0"},
        {"window_id": "@2", "window_active": "1"},
    ]
    out = tmux_core.tmux_active_window_in_session(
        "$0",
        tmux_list_windows=lambda _sid: windows,
        tmux_display=lambda _expr, _target: "@1",
    )
    assert out["window_id"] == "@1"


def test_tmux_active_window_falls_back_to_window_active_flag() -> None:
    windows = [
        {"window_id": "@1", "window_active": "0"},
        {"window_id": "@2", "window_active": "1"},
    ]
    out = tmux_core.tmux_active_window_in_session(
        "$0",
        tmux_list_windows=lambda _sid: windows,
        tmux_display=lambda _expr, _target: "",
    )
    assert out["window_id"] == "@2"


def test_tmux_active_window_first_when_no_signal() -> None:
    windows = [
        {"window_id": "@1", "window_active": "0"},
        {"window_id": "@2", "window_active": "0"},
    ]
    out = tmux_core.tmux_active_window_in_session(
        "$0",
        tmux_list_windows=lambda _sid: windows,
        tmux_display=lambda _expr, _target: "",
    )
    assert out["window_id"] == "@1"


def test_tmux_active_window_raises_when_no_windows() -> None:
    with pytest.raises(RuntimeError, match="no windows"):
        tmux_core.tmux_active_window_in_session(
            "$0",
            tmux_list_windows=lambda _sid: [],
            tmux_display=lambda _expr, _target: "",
        )


def test_tmux_resolve_session_window_pane_match(monkeypatch) -> None:
    sessions = [
        {"session_id": "$0", "session_name": "main", "session_activity": "200"},
        {"session_id": "$1", "session_name": "work", "session_activity": "100"},
    ]
    monkeypatch.delenv("TMUX_PANE", raising=False)

    session, window = tmux_core.tmux_resolve_session_window(
        pane_id_hint="%9",
        session_id_hint="",
        tmux_list_sessions=lambda: sessions,
        tmux_find_window_by_pane_id=lambda _pid: ("$1", "@2"),
        tmux_list_windows=lambda _sid: [{"window_id": "@2", "window_name": "w"}],
        tmux_active_window_in_session=lambda _sid: {"window_id": "@2"},
        tmux_display=lambda _expr, _target: "",
    )
    assert session["session_id"] == "$1"
    assert window["window_id"] == "@2"


def test_tmux_resolve_session_window_session_hint(monkeypatch) -> None:
    sessions = [
        {"session_id": "$0", "session_name": "main", "session_activity": "0"},
        {"session_id": "$1", "session_name": "work", "session_activity": "0"},
    ]
    monkeypatch.delenv("TMUX_PANE", raising=False)

    session, _window = tmux_core.tmux_resolve_session_window(
        pane_id_hint="",
        session_id_hint="$1",
        tmux_list_sessions=lambda: sessions,
        tmux_find_window_by_pane_id=lambda _pid: None,
        tmux_list_windows=lambda _sid: [{"window_id": "@1"}],
        tmux_active_window_in_session=lambda _sid: {"window_id": "@1"},
        tmux_display=lambda _expr, _target: "",
    )
    assert session["session_id"] == "$1"


def test_tmux_resolve_session_window_raises_when_unable(monkeypatch) -> None:
    monkeypatch.delenv("TMUX_PANE", raising=False)
    with pytest.raises(RuntimeError, match="no tmux sessions"):
        tmux_core.tmux_resolve_session_window(
            pane_id_hint="",
            session_id_hint="",
            tmux_list_sessions=lambda: [],
            tmux_find_window_by_pane_id=lambda _pid: None,
            tmux_list_windows=lambda _sid: [],
            tmux_active_window_in_session=lambda _sid: {},
            tmux_display=lambda _expr, _target: "",
        )


def test_first_token_basename_returns_empty_for_blank() -> None:
    assert tmux_core.first_token_basename("") == ""
    assert tmux_core.first_token_basename("   ") == ""


def test_is_descendant_pid_walks_parent_chain() -> None:
    parents = {5: 4, 4: 3, 3: 2, 2: 1}
    assert tmux_core.is_descendant_pid(5, 3, parents) is True
    assert tmux_core.is_descendant_pid(5, 9, parents) is False
    assert tmux_core.is_descendant_pid(0, 1, parents) is False
    # cycle protection: should not loop forever
    bad = {1: 2, 2: 1}
    assert tmux_core.is_descendant_pid(1, 3, bad) is False


def test_resolve_tmux_save_output_uses_dir(tmp_path: Path) -> None:
    out = tmux_core.resolve_tmux_save_output(str(tmp_path), tmp_path)
    assert out == tmp_path.resolve() / ".tmuxp.yaml"


def test_resolve_tmux_save_output_uses_file(tmp_path: Path) -> None:
    target = tmp_path / "custom.yaml"
    out = tmux_core.resolve_tmux_save_output(str(target), tmp_path)
    assert out == target.resolve()


def test_format_error_falls_back_to_details() -> None:
    class FakeCalledProcess(Exception):
        def __init__(self) -> None:
            super().__init__()
            self.stderr = "boom"
            self.stdout = ""
            self.cmd = ["tmux"]
            self.returncode = 7

    out = tmux_core.format_error(FakeCalledProcess())
    assert "FakeCalledProcess" in out
    assert "stderr" in out


def test_format_error_falls_back_to_args() -> None:
    class FakeError(Exception):
        pass

    e = FakeError("a", "b")
    out = tmux_core.format_error(e)
    assert "FakeError" in out


def test_pane_best_run_command_debug_shell_short_circuit() -> None:
    out = tmux_core.pane_best_run_command_debug(
        {"pane_id": "%1", "pane_pid": "1234", "pane_tty": "", "pane_current_command": "fish"},
        shell_commands={"fish", "bash", "zsh"},
    )
    assert out["reason"] == "current command is shell"
    assert out["current_name"] == "fish"


def test_resolve_project_root_from_panes_no_inputs(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no pane start directories"):
        tmux_core.resolve_project_root_from_panes(
            [],
            tmp_path,
            is_under=lambda _a, _b: False,
            find_marker_root_upward=lambda _p: None,
        )


def test_resolve_project_root_from_panes_outside_base_only(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="under base root"):
        tmux_core.resolve_project_root_from_panes(
            [str(tmp_path / "elsewhere")],
            tmp_path / "base",
            is_under=lambda _p, _r: False,
            find_marker_root_upward=lambda _p: None,
        )


def test_resolve_project_root_from_panes_no_marker_found(tmp_path: Path) -> None:
    base_root = tmp_path / "base"
    inside = base_root / "x"
    inside.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="no project root found"):
        tmux_core.resolve_project_root_from_panes(
            [str(inside)],
            base_root,
            is_under=lambda _p, _r: True,
            find_marker_root_upward=lambda _p: None,
        )
