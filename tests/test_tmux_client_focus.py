from __future__ import annotations

import subprocess

from homebase.tmux import client_focus


def test_focus_tmux_client_app_activates_outermost_app(monkeypatch) -> None:
    calls: list[list[str]] = []

    def tmux_fn(*_args: str) -> str:
        return "300"

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

    monkeypatch.setattr(client_focus.sys, "platform", "darwin")
    monkeypatch.setattr(client_focus.subprocess, "run", fake_run)

    client_focus.focus_tmux_client_app(tmux_fn)

    assert [cmd[:2] for cmd in calls] == [["ps", "-axo"], ["osascript", "-e"]]
    assert calls[1][-1] == 'tell application "/Applications/kitty.app" to activate'
