from __future__ import annotations

import json
import subprocess
from pathlib import Path

from homebase.core import debug_timers
from homebase.tmux import client_focus


def _fake_run_for_ancestry(calls: list[list[str]]):
    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        if cmd[:2] == ["ps", "-axo"]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=(
                    "300 200 /opt/homebrew/bin/tmux\n"
                    "200 150 /opt/homebrew/Frameworks/Python.app/Contents/MacOS/Python\n"
                    "150 100 -fish\n"
                    "100 1 /Applications/kitty.app/Contents/MacOS/kitty\n"
                ),
                stderr="",
            )
        if cmd[:2] == ["osascript", "-e"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(cmd)

    return fake_run


def test_focus_tmux_client_app_falls_back_to_osascript_when_appkit_unavailable(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[list[str]] = []

    def tmux_fn(*_args: str) -> str:
        return "300"

    monkeypatch.setattr(client_focus.sys, "platform", "darwin")
    monkeypatch.setattr(client_focus.subprocess, "run", _fake_run_for_ancestry(calls))
    monkeypatch.setattr(client_focus, "_activate_via_appkit", lambda _pid: False)

    client_focus.focus_tmux_client_app(tmux_fn, tmp_path)

    assert [cmd[:2] for cmd in calls] == [["ps", "-axo"], ["osascript", "-e"]]
    assert calls[1][-1] == 'tell application "/Applications/kitty.app" to activate'


def test_focus_tmux_client_app_prefers_appkit_when_available(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[list[str]] = []
    activated_pids: list[int] = []

    def tmux_fn(*_args: str) -> str:
        return "300"

    monkeypatch.setattr(client_focus.sys, "platform", "darwin")
    monkeypatch.setattr(client_focus.subprocess, "run", _fake_run_for_ancestry(calls))
    monkeypatch.setattr(
        client_focus,
        "_activate_via_appkit",
        lambda pid: activated_pids.append(pid) or True,
    )

    client_focus.focus_tmux_client_app(tmux_fn, tmp_path)

    # AppKit succeeded: no osascript activate call needed at all.
    assert calls == [["ps", "-axo", "pid=,ppid=,comm="]]
    assert activated_pids == [100]


def test_focus_tmux_client_app_falls_back_to_system_events_when_both_fail(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[list[str]] = []

    def tmux_fn(*_args: str) -> str:
        return "300"

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        if cmd[:2] == ["ps", "-axo"]:
            return _fake_run_for_ancestry([])(cmd, **_kwargs)
        if cmd[:2] == ["osascript", "-e"]:
            # bundle-activate and system-events both report failure
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
        raise AssertionError(cmd)

    monkeypatch.setattr(client_focus.sys, "platform", "darwin")
    monkeypatch.setattr(client_focus.subprocess, "run", fake_run)
    monkeypatch.setattr(client_focus, "_activate_via_appkit", lambda _pid: False)

    client_focus.focus_tmux_client_app(tmux_fn, tmp_path)

    assert [cmd[:2] for cmd in calls] == [
        ["ps", "-axo"],
        ["osascript", "-e"],
        ["osascript", "-e"],
    ]
    assert "System Events" in calls[2][-1]


def test_focus_tmux_client_app_writes_debug_timers_when_enabled(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[list[str]] = []

    def tmux_fn(*_args: str) -> str:
        return "300"

    monkeypatch.setattr(client_focus.sys, "platform", "darwin")
    monkeypatch.setattr(client_focus.subprocess, "run", _fake_run_for_ancestry(calls))
    monkeypatch.setattr(client_focus, "_activate_via_appkit", lambda _pid: False)
    monkeypatch.setattr(debug_timers, "enabled", True)

    client_focus.focus_tmux_client_app(tmux_fn, tmp_path)

    log_path = debug_timers.debug_timers_log_path(tmp_path)
    records = [json.loads(line) for line in log_path.read_text().splitlines()]
    labels = [record["label"] for record in records]
    assert labels == [
        "tmux_focus.client_pid_lookup",
        "tmux_focus.process_ancestry",
        "tmux_focus.activate_via_appkit",
        "tmux_focus.activate_by_bundle",
        "tmux_focus.wait_until_frontmost",
    ]
    appkit_record, activate_record, wait_record = records[2], records[3], records[4]
    assert appkit_record["ok"] is False
    assert activate_record["bundle"] == "/Applications/kitty.app"
    assert activate_record["ok"] is True
    assert wait_record["pid"] == 100
    # fake osascript returns empty stdout, so the frontmost poll reports false
    assert wait_record["ok"] is False
    assert all(isinstance(record["seconds"], float) for record in records)
