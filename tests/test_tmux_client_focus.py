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
    # Force the osascript fallback so the System Events step is testable
    # without invoking real NSAppleScript on a machine with pyobjc.
    monkeypatch.setattr(client_focus, "_foundation_available", lambda: False)

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


def test_frontmost_by_name_script_targets_process_and_escapes_quotes() -> None:
    script = client_focus._frontmost_by_name_script('we"ird')
    assert 'first process whose name is "we\\"ird"' in script
    assert "System Events" in script
    # no full-process enumeration in the fast path
    assert "whose unix id" not in script


def test_system_events_prefers_name_then_unix_id(monkeypatch) -> None:
    monkeypatch.setattr(client_focus, "_foundation_available", lambda: True)
    seen: list[str] = []

    def fake_run(source: str) -> tuple[bool, str]:
        seen.append(source)
        return ("first process whose name" in source, "")

    monkeypatch.setattr(client_focus, "_run_applescript_in_process", fake_run)

    ok, method, _detail = client_focus.system_events_set_frontmost("kitty", [100, 200])
    assert ok is True
    assert method == "nsapplescript:name"
    assert len(seen) == 1  # name hit, unix-id never tried


def test_system_events_falls_back_to_unix_id_when_name_fails(monkeypatch) -> None:
    monkeypatch.setattr(client_focus, "_foundation_available", lambda: True)

    def fake_run(source: str) -> tuple[bool, str]:
        return ("whose unix id" in source, "" if "whose unix id" in source else "no match")

    monkeypatch.setattr(client_focus, "_run_applescript_in_process", fake_run)

    ok, method, _detail = client_focus.system_events_set_frontmost("kitty", [100])
    assert ok is True
    assert method == "nsapplescript:unix_id"


def test_system_events_uses_osascript_when_pyobjc_absent(monkeypatch) -> None:
    monkeypatch.setattr(client_focus, "_foundation_available", lambda: False)
    monkeypatch.setattr(
        client_focus, "_osascript_unix_id_focus", lambda pids: (True, f"pids {pids}")
    )

    ok, method, detail = client_focus.system_events_set_frontmost("kitty", [100])
    assert ok is True
    assert method == "osascript:unix_id"
    assert "100" in detail


def test_warm_up_precompiles_and_pings_without_focusing(monkeypatch) -> None:
    monkeypatch.setattr(client_focus.sys, "platform", "darwin")
    monkeypatch.setattr(client_focus, "_foundation_available", lambda: True)
    compiled: list[str] = []
    executed: list[str] = []

    def fake_compile(source: str):
        compiled.append(source)
        return object()

    def fake_run(source: str) -> tuple[bool, str]:
        executed.append(source)
        return True, ""

    monkeypatch.setattr(client_focus, "_get_or_compile_locked", fake_compile)
    monkeypatch.setattr(client_focus, "_run_applescript_in_process", fake_run)

    ok, detail = client_focus.warm_up_focus_backend("kitty")

    assert ok is True
    # by-name script precompiled; only the no-op ping is executed (no
    # focus-changing script runs during warm-up)
    assert compiled == [client_focus._frontmost_by_name_script("kitty")]
    assert executed == [client_focus._WARMUP_SCRIPT]
    assert "set frontmost" not in client_focus._WARMUP_SCRIPT


def test_warm_up_skips_when_not_darwin(monkeypatch) -> None:
    monkeypatch.setattr(client_focus.sys, "platform", "linux")
    ok, detail = client_focus.warm_up_focus_backend("kitty")
    assert ok is False
    assert detail == "not darwin"


def test_warm_up_reports_when_pyobjc_absent(monkeypatch) -> None:
    monkeypatch.setattr(client_focus.sys, "platform", "darwin")
    monkeypatch.setattr(client_focus, "_foundation_available", lambda: False)
    ok, detail = client_focus.warm_up_focus_backend("kitty")
    assert ok is False
    assert "Foundation" in detail


def test_precompile_no_op_without_app_name(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        client_focus, "_get_or_compile_locked", lambda s: calls.append(s)
    )
    client_focus.precompile_focus_scripts(None)
    assert calls == []


def test_forced_system_events_skips_appkit_even_when_available(
    tmp_path: Path, monkeypatch
) -> None:
    from homebase.config import store as config_store

    config_store.save_global_config_dict(
        tmp_path, {"tmux_focus": {"method": "system_events"}}
    )
    calls: list[list[str]] = []
    appkit_called: list[int] = []

    def tmux_fn(*_args: str) -> str:
        return "300"

    monkeypatch.setattr(client_focus.sys, "platform", "darwin")
    monkeypatch.setattr(client_focus.subprocess, "run", _fake_run_for_ancestry(calls))
    monkeypatch.setattr(
        client_focus, "_activate_via_appkit", lambda pid: appkit_called.append(pid) or True
    )
    se_calls: list[tuple[str | None, list[int]]] = []
    monkeypatch.setattr(
        client_focus,
        "system_events_set_frontmost",
        lambda name, pids: se_calls.append((name, pids)) or (True, "nsapplescript:name", ""),
    )

    client_focus.focus_tmux_client_app(tmux_fn, tmp_path)

    assert appkit_called == []  # forced backend bypasses the auto waterfall
    assert se_calls == [("kitty", [300, 200, 150, 100])]


def test_forced_appkit_does_not_fall_through_on_failure(
    tmp_path: Path, monkeypatch
) -> None:
    from homebase.config import store as config_store

    config_store.save_global_config_dict(
        tmp_path, {"tmux_focus": {"method": "appkit"}}
    )
    calls: list[list[str]] = []

    def tmux_fn(*_args: str) -> str:
        return "300"

    monkeypatch.setattr(client_focus.sys, "platform", "darwin")
    monkeypatch.setattr(client_focus.subprocess, "run", _fake_run_for_ancestry(calls))
    monkeypatch.setattr(client_focus, "_activate_via_appkit", lambda _pid: False)

    def fail_se(*_args, **_kwargs):
        raise AssertionError("system events must not run when appkit is enforced")

    monkeypatch.setattr(client_focus, "system_events_set_frontmost", fail_se)

    client_focus.focus_tmux_client_app(tmux_fn, tmp_path)

    # Only ancestry lookup; no osascript activate, no System Events fallback.
    assert [cmd[:2] for cmd in calls] == [["ps", "-axo"]]
