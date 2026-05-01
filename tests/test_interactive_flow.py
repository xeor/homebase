from __future__ import annotations

from pathlib import Path

import pytest

from homebase.commands import interactive_flow as interactive_flow


def test_no_arg_flow_open_action_runs_open_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    class _TTY:
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(interactive_flow.sys, "stdin", _TTY())
    monkeypatch.setattr(interactive_flow.sys, "stdout", _TTY())

    rc = interactive_flow.no_arg_flow(
        Path("/tmp/base"),
        Path("/tmp/base"),
        initial_filter_expr="",
        cmd_status=lambda _b: 0,
        run_textual_ui=lambda _b, _c, _q: ("open", Path("/tmp/base/p"), []),
        run_post_commands=lambda _p, _c: called.append("post"),
        open_with_mode=lambda _b, _p: 9,
        cmd_archive_mv=lambda _b, _p: 0,
        open_shell_in_dir=lambda _p: 0,
        cmd_archive_restore_entry=lambda _b, _p: 0,
        cmd_rm=lambda _p: 0,
    )
    assert rc == 9
    assert called == ["post"]
