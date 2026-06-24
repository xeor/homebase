from __future__ import annotations

import subprocess
from pathlib import Path

from homebase.tmux import external as tmux_external


def _run_external_open(base_dir: Path, path: Path) -> int:
    return tmux_external.open_with_mode_outside_tmux(
        base_dir,
        path,
        open_shell_in_dir=lambda _path: 0,
    )


def test_list_panes_args_for_session_scans_every_window() -> None:
    assert tmux_external._list_panes_args_for_session(
        ("list-panes", "-a", "-F", "#{pane_id}"),
        "$1",
    ) == ["list-panes", "-s", "-t", "$1", "-F", "#{pane_id}"]


def test_is_inside_current_tmux_pane_rejects_incomplete_tmux_env(monkeypatch) -> None:
    monkeypatch.setenv("TMUX", "/tmp/tmux-sock,1,2")
    monkeypatch.delenv("TMUX_PANE", raising=False)

    assert tmux_external.is_inside_current_tmux_pane() is False


def test_is_inside_current_tmux_pane_rejects_unreachable_tmux(monkeypatch) -> None:
    monkeypatch.setenv("TMUX", "/tmp/tmux-sock,1,2")
    monkeypatch.setenv("TMUX_PANE", "%7")
    monkeypatch.setattr(tmux_external.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tmux_external.sys.stdin, "fileno", lambda: 0)
    monkeypatch.setattr(tmux_external.os, "ttyname", lambda _fd: "/dev/ttys-terminal")
    monkeypatch.setattr(
        tmux_external,
        "_tmux_for_prefix",
        lambda _prefix: lambda *_args: (
            _ for _ in ()
        ).throw(OSError("stale socket")),
    )

    assert tmux_external.is_inside_current_tmux_pane() is False


def test_open_with_mode_uses_registered_tmux_socket_outside_tmux(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    context = {
        "socket_path": "/tmp/tmux-sock",
        "open_profile": "tmux_tab_load_or_goto",
    }
    monkeypatch.setattr(
        tmux_external,
        "load_active_tmux_context",
        lambda _base: context,
    )
    monkeypatch.setattr(tmux_external, "load_tmux_contexts", lambda _base: [context])
    monkeypatch.setattr(tmux_external, "_resolve_tmux_bin", lambda: "/bin/tmux")
    monkeypatch.setattr(
        tmux_external.tmux_core,
        "tmux_list_sessions",
        lambda tmux: [
            {
                "session_id": "$1",
                "session_name": "main",
                "session_activity": "1",
                "session_attached": "1",
            }
        ],
    )
    focused: list[object] = []
    monkeypatch.setattr(
        tmux_external,
        "focus_tmux_client_app",
        lambda tmux_fn, _base_dir: focused.append(tmux_fn),
    )
    seen: dict[str, object] = {}

    def _open_with_mode(_base, _path, **kwargs):
        seen["prefix"] = kwargs["tmux_command_prefix"]()
        seen["available"] = kwargs["tmux_available"]()
        seen["profile"] = kwargs["load_open_mode_config"](tmp_path)
        return 0

    monkeypatch.setattr(tmux_external.tmux_commands, "open_with_mode", _open_with_mode)

    rc = _run_external_open(tmp_path, tmp_path / "project")

    assert rc == 0
    assert seen == {
        "prefix": ["/bin/tmux", "-S", "/tmp/tmux-sock"],
        "available": True,
        "profile": {"profile": "tmux_tab_load_or_goto"},
    }
    assert len(focused) == 1


def test_open_with_mode_uses_single_tmux_session_without_registry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(tmux_external, "load_active_tmux_context", lambda _base: None)
    monkeypatch.setattr(
        tmux_external,
        "load_open_mode_config",
        lambda _base: {"profile": "tmux_tab"},
    )
    monkeypatch.setattr(tmux_external, "_resolve_tmux_bin", lambda: "/bin/tmux")
    monkeypatch.setattr(
        tmux_external.tmux_core,
        "tmux_list_sessions",
        lambda tmux: [
            {
                "session_id": "$1",
                "session_name": "main",
                "session_activity": "1",
                "session_attached": "1",
            }
        ],
    )
    seen: dict[str, object] = {}

    def _open_with_mode(_base, _path, **kwargs):
        seen["prefix"] = kwargs["tmux_command_prefix"]()
        seen["available"] = kwargs["tmux_available"]()
        seen["new"] = kwargs["tmux_open_new_tab"](tmp_path / "project")
        return 0

    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="@7\n", stderr="")

    monkeypatch.setattr(tmux_external.tmux_commands, "open_with_mode", _open_with_mode)
    monkeypatch.setattr(tmux_external.subprocess, "run", fake_run)

    assert _run_external_open(tmp_path, tmp_path / "project") == 0
    assert seen == {"prefix": ["/bin/tmux"], "available": True, "new": 0}
    assert calls[0][:4] == ["/bin/tmux", "new-window", "-t", "$1"]


def test_open_with_mode_treats_stale_tmux_env_as_outside_tmux(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("TMUX", "/tmp/tmux-sock,1,2")
    monkeypatch.setenv("TMUX_PANE", "%7")
    monkeypatch.setattr(tmux_external, "load_active_tmux_context", lambda _base: None)
    monkeypatch.setattr(
        tmux_external,
        "load_open_mode_config",
        lambda _base: {"profile": "tmux_tab"},
    )
    monkeypatch.setattr(tmux_external, "_resolve_tmux_bin", lambda: "/bin/tmux")
    monkeypatch.setattr(
        tmux_external,
        "_tmux_for_prefix",
        lambda _prefix: (
            lambda *args: "/dev/ttys-tmux-pane"
            if args == ("display-message", "-p", "-t", "%7", "#{pane_tty}")
            else ""
        ),
    )
    monkeypatch.setattr(tmux_external.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tmux_external.sys.stdin, "fileno", lambda: 0)
    monkeypatch.setattr(tmux_external.os, "ttyname", lambda _fd: "/dev/ttys-terminal")
    monkeypatch.setattr(
        tmux_external.tmux_core,
        "tmux_list_sessions",
        lambda tmux: [
            {
                "session_id": "$1",
                "session_name": "main",
                "session_activity": "1",
                "session_attached": "1",
            }
        ],
    )
    seen: dict[str, object] = {}

    def _open_with_mode(_base, _path, **kwargs):
        seen["available"] = kwargs["tmux_available"]()
        seen["prefix"] = kwargs["tmux_command_prefix"]()
        return 0

    monkeypatch.setattr(tmux_external.tmux_commands, "open_with_mode", _open_with_mode)

    assert _run_external_open(tmp_path, tmp_path / "project") == 0
    assert seen == {"available": True, "prefix": ["/bin/tmux", "-S", "/tmp/tmux-sock"]}


def test_open_with_mode_rejects_ambiguous_external_tmux_sessions(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(tmux_external, "load_active_tmux_context", lambda _base: None)
    monkeypatch.setattr(
        tmux_external,
        "load_open_mode_config",
        lambda _base: {"profile": "tmux_tab"},
    )
    monkeypatch.setattr(tmux_external, "_resolve_tmux_bin", lambda: "/bin/tmux")
    monkeypatch.setattr(
        tmux_external.tmux_core,
        "tmux_list_sessions",
        lambda tmux: [
            {"session_id": "$1", "session_name": "main"},
            {"session_id": "$2", "session_name": "work"},
        ],
    )

    assert _run_external_open(tmp_path, tmp_path / "project") == 1
    assert "multiple tmux sessions found" in capsys.readouterr().err


def test_context_for_configured_session_selects_matching_socket(
    monkeypatch,
) -> None:
    contexts = [
        {"socket_path": "/tmp/work.sock"},
        {"socket_path": "/tmp/main.sock"},
    ]

    def fake_sessions(*, tmux):
        socket_path = tmux()
        session_name = "main" if socket_path == "/tmp/main.sock" else "work"
        return [{"session_id": "$1", "session_name": session_name}]

    monkeypatch.setattr(tmux_external, "_resolve_tmux_bin", lambda: "/bin/tmux")
    monkeypatch.setattr(
        tmux_external,
        "_tmux_for_prefix",
        lambda prefix_fn: lambda *_args: prefix_fn()[2],
    )
    monkeypatch.setattr(tmux_external.tmux_core, "tmux_list_sessions", fake_sessions)

    assert tmux_external._context_for_configured_session(contexts, "main") == contexts[1]


def test_external_target_rejects_sessions_across_multiple_sockets(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contexts = [
        {"socket_path": "/tmp/main.sock"},
        {"socket_path": "/tmp/work.sock"},
    ]

    def fake_candidate(context, socket_path):
        name = "main" if socket_path == "/tmp/main.sock" else "work"
        return context, ["/bin/tmux", "-S", socket_path], lambda *_args: "", [
            {"session_id": f"${name}", "session_name": name}
        ]

    monkeypatch.setattr(tmux_external, "load_open_mode_config", lambda _base: {})
    monkeypatch.setattr(tmux_external, "load_tmux_contexts", lambda _base: contexts)
    monkeypatch.setattr(tmux_external, "_external_tmux_candidate", fake_candidate)

    assert tmux_external._external_tmux_target(tmp_path) is None
    assert "multiple tmux sessions found" in capsys.readouterr().err


def test_external_target_selects_configured_session_across_sockets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    contexts = [
        {"socket_path": "/tmp/main.sock"},
        {"socket_path": "/tmp/work.sock"},
    ]

    def fake_candidate(context, socket_path):
        name = "main" if socket_path == "/tmp/main.sock" else "work"
        return context, ["/bin/tmux", "-S", socket_path], lambda *_args: "", [
            {"session_id": f"${name}", "session_name": name}
        ]

    monkeypatch.setattr(
        tmux_external,
        "load_open_mode_config",
        lambda _base: {"tmux_session": "work"},
    )
    monkeypatch.setattr(tmux_external, "load_tmux_contexts", lambda _base: contexts)
    monkeypatch.setattr(tmux_external, "_external_tmux_candidate", fake_candidate)

    resolved = tmux_external._external_tmux_target(tmp_path)

    assert resolved is not None
    context, prefix, _tmux_fn, session_target = resolved
    assert context == contexts[1]
    assert prefix == ["/bin/tmux", "-S", "/tmp/work.sock"]
    assert session_target == "work"


def test_load_profile_window_for_tmux_targets_socket_and_session_pane(
    tmp_path: Path,
    monkeypatch,
) -> None:
    profile = tmp_path / ".tmuxp.yaml"
    profile.write_text("session_name: project\nwindows: []\n")
    seen: dict[str, object] = {}
    tmux_calls: list[tuple[str, ...]] = []

    def fake_load(profile, **kwargs):
        seen["profile"] = profile
        seen["tmuxp_args"] = kwargs["tmuxp_args"]
        seen["tmux_pane"] = kwargs["env"].get("TMUX_PANE")
        kwargs["list_window_ids"]()
        return "@2", None

    monkeypatch.setattr(tmux_external.tmux_commands, "load_profile_window", fake_load)

    def tmux_fn(*args: str) -> str:
        tmux_calls.append(args)
        return ""

    result = tmux_external._load_profile_window(
        profile,
        tmux_fn,
        socket_path="/tmp/main.sock",
        session_target="$1",
        session_pane_id="%9",
    )

    assert result == ("@2", None)
    assert seen == {
        "profile": profile,
        "tmuxp_args": ["tmuxp", "load", "-a", "-S", "/tmp/main.sock"],
        "tmux_pane": "%9",
    }
    assert tmux_calls == [
        ("list-windows", "-t", "$1", "-F", "#{window_id}"),
    ]


def test_first_pane_in_session_uses_session_scope() -> None:
    calls: list[tuple[str, ...]] = []

    def tmux_fn(*args: str) -> str:
        calls.append(args)
        return "%9\n%10\n"

    assert tmux_external._first_pane_in_session(tmux_fn, "$1") == "%9"
    assert calls == [
        ("list-panes", "-s", "-t", "$1", "-F", "#{pane_id}"),
    ]


def test_open_with_mode_shell_profile_outside_tmux_does_not_resolve_tmux(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(tmux_external, "load_active_tmux_context", lambda _base: None)
    monkeypatch.setattr(
        tmux_external,
        "load_open_mode_config",
        lambda _base: {"profile": "shell_cd"},
    )
    monkeypatch.setattr(
        tmux_external.tmux_core,
        "tmux_list_sessions",
        lambda tmux: (_ for _ in ()).throw(AssertionError("should not query tmux")),
    )
    opened: list[Path] = []

    assert (
        tmux_external.open_with_mode_outside_tmux(
            tmp_path,
            tmp_path / "project",
            open_shell_in_dir=lambda path: opened.append(path) or 0,
        )
        == 0
    )
    assert opened == [tmp_path / "project"]


def test_open_with_mode_selects_live_pane_in_resolved_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = tmp_path / "project"
    target.mkdir()
    monkeypatch.delenv("TMUX", raising=False)
    context = {
        "socket_path": "/tmp/tmux-sock",
        "open_profile": "tmux_tab_load_or_goto",
    }
    monkeypatch.setattr(tmux_external, "load_active_tmux_context", lambda _base: context)
    monkeypatch.setattr(tmux_external, "load_tmux_contexts", lambda _base: [context])
    monkeypatch.setattr(tmux_external, "_resolve_tmux_bin", lambda: "/bin/tmux")
    monkeypatch.setattr(
        tmux_external.tmux_core,
        "tmux_list_sessions",
        lambda tmux: [
            {
                "session_id": "$1",
                "session_name": "main",
                "session_activity": "1",
                "session_attached": "1",
            }
        ],
    )
    focused: list[object] = []
    monkeypatch.setattr(
        tmux_external,
        "focus_tmux_client_app",
        lambda tmux_fn, _base_dir: focused.append(tmux_fn),
    )

    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    def fake_open_with_mode(_base, _path, **kwargs):
        found = kwargs["tmux_find_pane_for_cwd"](target)
        assert found == ("%7", "main:3")
        pane_id, window_id = found
        subprocess.run([*kwargs["tmux_command_prefix"](), "select-window", "-t", window_id])
        subprocess.run([*kwargs["tmux_command_prefix"](), "select-pane", "-t", pane_id])
        return 0

    monkeypatch.setattr(
        tmux_external,
        "_tmux_find_pane_for_cwd_in_session",
        lambda _target, _tmux_fn, session: ("%7", "main:3")
        if session == "$1"
        else None,
    )

    monkeypatch.setattr(tmux_external.tmux_commands, "open_with_mode", fake_open_with_mode)
    monkeypatch.setattr(tmux_external.subprocess, "run", fake_run)

    assert _run_external_open(tmp_path, target) == 0
    assert calls == [
        ["/bin/tmux", "-S", "/tmp/tmux-sock", "select-window", "-t", "main:3"],
        ["/bin/tmux", "-S", "/tmp/tmux-sock", "select-pane", "-t", "%7"],
    ]
    assert len(focused) == 1


def test_open_with_mode_does_not_focus_when_external_open_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    context = {"socket_path": "/tmp/tmux-sock"}
    monkeypatch.setattr(
        tmux_external,
        "load_active_tmux_context",
        lambda _base: context,
    )
    monkeypatch.setattr(tmux_external, "load_tmux_contexts", lambda _base: [context])
    monkeypatch.setattr(
        tmux_external,
        "load_open_mode_config",
        lambda _base: {"profile": "tmux_tab"},
    )
    monkeypatch.setattr(tmux_external, "_resolve_tmux_bin", lambda: "/bin/tmux")
    monkeypatch.setattr(
        tmux_external.tmux_core,
        "tmux_list_sessions",
        lambda tmux: [
            {
                "session_id": "$1",
                "session_name": "main",
                "session_activity": "1",
                "session_attached": "1",
            }
        ],
    )
    focused: list[object] = []
    monkeypatch.setattr(
        tmux_external,
        "focus_tmux_client_app",
        lambda tmux_fn, _base_dir: focused.append(tmux_fn),
    )
    monkeypatch.setattr(
        tmux_external.tmux_commands,
        "open_with_mode",
        lambda _base, _path, **_kwargs: 9,
    )

    assert _run_external_open(tmp_path, tmp_path / "project") == 9
    assert focused == []

