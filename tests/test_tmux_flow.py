from __future__ import annotations

import subprocess
from pathlib import Path

from homebase.tmux import flow as tmux_flow


def test_open_with_mode_uses_registered_tmux_socket_outside_tmux(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(
        tmux_flow,
        "load_active_tmux_context",
        lambda _base: {
            "socket_path": "/tmp/tmux-sock",
            "open_profile": "tmux_tab_load_or_goto",
        },
    )
    monkeypatch.setattr(tmux_flow, "_resolve_tmux_bin", lambda: "/bin/tmux")
    focused: list[object] = []
    monkeypatch.setattr(tmux_flow, "_focus_tmux_client_app", lambda tmux_fn: focused.append(tmux_fn))
    seen: dict[str, object] = {}

    def _open_with_mode(_base, _path, **kwargs):
        seen["prefix"] = kwargs["tmux_command_prefix"]()
        seen["available"] = kwargs["tmux_available"]()
        seen["profile"] = kwargs["load_open_mode_config"](tmp_path)
        return 0

    monkeypatch.setattr(tmux_flow.tmux_commands, "open_with_mode", _open_with_mode)

    rc = tmux_flow.open_with_mode(tmp_path, tmp_path / "project")

    assert rc == 0
    assert seen == {
        "prefix": ["/bin/tmux", "-S", "/tmp/tmux-sock"],
        "available": True,
        "profile": {"profile": "tmux_tab_load_or_goto"},
    }
    assert len(focused) == 1


def test_open_with_mode_selects_pane_from_registered_project_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = tmp_path / "project"
    target.mkdir()
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(
        tmux_flow,
        "load_active_tmux_context",
        lambda _base: {
            "socket_path": "/tmp/tmux-sock",
            "open_profile": "tmux_tab_load_or_goto",
            "project_panes": {
                str(target.resolve()): [
                    {
                        "pane_id": "%7",
                        "target": "main:3.0",
                        "active": True,
                    }
                ]
            },
        },
    )
    monkeypatch.setattr(tmux_flow, "_resolve_tmux_bin", lambda: "/bin/tmux")
    focused: list[object] = []
    monkeypatch.setattr(tmux_flow, "_focus_tmux_client_app", lambda tmux_fn: focused.append(tmux_fn))

    def fail_open_with_mode(*_args, **_kwargs):
        raise AssertionError("generic open fallback should not run")

    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(tmux_flow.tmux_commands, "open_with_mode", fail_open_with_mode)
    monkeypatch.setattr(tmux_flow.subprocess, "run", fake_run)

    assert tmux_flow.open_with_mode(tmp_path, target) == 0
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
    monkeypatch.setattr(
        tmux_flow,
        "load_active_tmux_context",
        lambda _base: {"socket_path": "/tmp/tmux-sock"},
    )
    monkeypatch.setattr(tmux_flow, "_resolve_tmux_bin", lambda: "/bin/tmux")
    focused: list[object] = []
    monkeypatch.setattr(tmux_flow, "_focus_tmux_client_app", lambda tmux_fn: focused.append(tmux_fn))
    monkeypatch.setattr(
        tmux_flow.tmux_commands,
        "open_with_mode",
        lambda _base, _path, **_kwargs: 9,
    )

    assert tmux_flow.open_with_mode(tmp_path, tmp_path / "project") == 9
    assert focused == []


def test_focus_tmux_client_app_walks_parent_processes(monkeypatch) -> None:
    calls: list[list[str]] = []

    def tmux_fn(*_args: str) -> str:
        return "300"

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        if cmd[:3] == ["ps", "-o", "ppid="]:
            pid = cmd[-1]
            parent = {"300": "200\n", "200": "100\n", "100": "1\n"}[pid]
            return subprocess.CompletedProcess(cmd, 0, stdout=parent, stderr="")
        if "unix id is 100" in cmd[-1]:
            return subprocess.CompletedProcess(cmd, 0, stdout="true\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="false\n", stderr="")

    monkeypatch.setattr(tmux_flow.sys, "platform", "darwin")
    monkeypatch.setattr(tmux_flow.subprocess, "run", fake_run)

    tmux_flow._focus_tmux_client_app(tmux_fn)

    scripts = [cmd[-1] for cmd in calls if cmd[:2] == ["osascript", "-e"]]
    assert any("unix id is 300" in script for script in scripts)
    assert any("unix id is 200" in script for script in scripts)
    assert any("unix id is 100" in script for script in scripts)
