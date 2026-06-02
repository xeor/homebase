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
        cmd_list=lambda _b: 0,
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


def _stub_tty(monkeypatch, *, isatty: bool = True) -> None:
    class TTY:
        def __init__(self, val: bool) -> None:
            self._val = val

        def isatty(self) -> bool:
            return self._val

    monkeypatch.setattr(interactive_flow.sys, "stdin", TTY(isatty))
    monkeypatch.setattr(interactive_flow.sys, "stdout", TTY(isatty))


def test_no_arg_flow_falls_back_to_cmd_list_when_not_tty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_tty(monkeypatch, isatty=False)
    seen: list[Path] = []
    rc = interactive_flow.no_arg_flow(
        Path("/tmp/base"),
        Path("/tmp/base"),
        initial_filter_expr="",
        cmd_list=lambda bd: (seen.append(bd) or 7),
        run_textual_ui=lambda _b, _c, _q: ("open", Path("/p"), []),
        run_post_commands=lambda _p, _c: None,
        open_with_mode=lambda _b, _p: 0,
        cmd_archive_mv=lambda _b, _p: 0,
        open_shell_in_dir=lambda _p: 0,
        cmd_archive_restore_entry=lambda _b, _p: 0,
        cmd_rm=lambda _p: 0,
    )
    assert rc == 7
    assert seen == [Path("/tmp/base")]


def test_no_arg_flow_quit_returns_0(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_tty(monkeypatch)
    rc = interactive_flow.no_arg_flow(
        Path("/tmp/base"),
        Path("/tmp/base"),
        initial_filter_expr="",
        cmd_list=lambda _b: 99,
        run_textual_ui=lambda _b, _c, _q: ("quit", None, []),
        run_post_commands=lambda _p, _c: None,
        open_with_mode=lambda _b, _p: 0,
        cmd_archive_mv=lambda _b, _p: 0,
        open_shell_in_dir=lambda _p: 0,
        cmd_archive_restore_entry=lambda _b, _p: 0,
        cmd_rm=lambda _p: 0,
    )
    assert rc == 0


def test_no_arg_flow_open_returns_error_when_post_command_fails(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    _stub_tty(monkeypatch)

    def fail(_p, _c):
        raise ValueError("post boom")

    rc = interactive_flow.no_arg_flow(
        Path("/tmp/base"),
        Path("/tmp/base"),
        initial_filter_expr="",
        cmd_list=lambda _b: 0,
        run_textual_ui=lambda _b, _c, _q: ("open", Path("/tmp/base/p"), ["echo x"]),
        run_post_commands=fail,
        open_with_mode=lambda _b, _p: 0,
        cmd_archive_mv=lambda _b, _p: 0,
        open_shell_in_dir=lambda _p: 0,
        cmd_archive_restore_entry=lambda _b, _p: 0,
        cmd_rm=lambda _p: 0,
    )
    err = capsys.readouterr().err
    assert rc == 1
    assert "post boom" in err


def test_no_arg_flow_archive_runs_archive_mv_and_opens_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_tty(monkeypatch)
    opened: list[Path] = []
    rc = interactive_flow.no_arg_flow(
        Path("/tmp/base"),
        Path("/tmp/base"),
        initial_filter_expr="",
        cmd_list=lambda _b: 0,
        run_textual_ui=lambda _b, _c, _q: ("archive", Path("/tmp/base/p"), []),
        run_post_commands=lambda _p, _c: None,
        open_with_mode=lambda _b, _p: 0,
        cmd_archive_mv=lambda _b, _p: 0,
        open_shell_in_dir=lambda p: (opened.append(p), 0)[1],
        cmd_archive_restore_entry=lambda _b, _p: 0,
        cmd_rm=lambda _p: 0,
    )
    assert rc == 0
    assert opened == [Path("/tmp/base")]


def test_no_arg_flow_archive_propagates_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_tty(monkeypatch)
    rc = interactive_flow.no_arg_flow(
        Path("/tmp/base"),
        Path("/tmp/base"),
        initial_filter_expr="",
        cmd_list=lambda _b: 0,
        run_textual_ui=lambda _b, _c, _q: ("archive", Path("/tmp/base/p"), []),
        run_post_commands=lambda _p, _c: None,
        open_with_mode=lambda _b, _p: 0,
        cmd_archive_mv=lambda _b, _p: 5,
        open_shell_in_dir=lambda _p: 0,
        cmd_archive_restore_entry=lambda _b, _p: 0,
        cmd_rm=lambda _p: 0,
    )
    assert rc == 5


def test_no_arg_flow_restore_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_tty(monkeypatch)
    rc = interactive_flow.no_arg_flow(
        Path("/tmp/base"),
        Path("/tmp/base"),
        initial_filter_expr="",
        cmd_list=lambda _b: 0,
        run_textual_ui=lambda _b, _c, _q: ("restore", Path("/tmp/base/p"), []),
        run_post_commands=lambda _p, _c: None,
        open_with_mode=lambda _b, _p: 0,
        cmd_archive_mv=lambda _b, _p: 0,
        open_shell_in_dir=lambda _p: 0,
        cmd_archive_restore_entry=lambda _b, _p: 22,
        cmd_rm=lambda _p: 0,
    )
    assert rc == 22


def test_no_arg_flow_delete_opens_parent_when_cwd_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_tty(monkeypatch)
    opened: list[Path] = []
    target = Path("/tmp/base/p")
    rc = interactive_flow.no_arg_flow(
        Path("/tmp/base"),
        target,
        initial_filter_expr="",
        cmd_list=lambda _b: 0,
        run_textual_ui=lambda _b, _c, _q: ("delete", target, []),
        run_post_commands=lambda _p, _c: None,
        open_with_mode=lambda _b, _p: 0,
        cmd_archive_mv=lambda _b, _p: 0,
        open_shell_in_dir=lambda p: (opened.append(p), 0)[1],
        cmd_archive_restore_entry=lambda _b, _p: 0,
        cmd_rm=lambda _p: 0,
    )
    assert rc == 0
    assert opened == [Path("/tmp/base")]


def test_no_arg_flow_delete_returns_cmd_rm_when_cwd_differs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_tty(monkeypatch)
    rc = interactive_flow.no_arg_flow(
        Path("/tmp/base"),
        Path("/elsewhere"),
        initial_filter_expr="",
        cmd_list=lambda _b: 0,
        run_textual_ui=lambda _b, _c, _q: ("delete", Path("/tmp/base/p"), []),
        run_post_commands=lambda _p, _c: None,
        open_with_mode=lambda _b, _p: 0,
        cmd_archive_mv=lambda _b, _p: 0,
        open_shell_in_dir=lambda _p: 99,
        cmd_archive_restore_entry=lambda _b, _p: 0,
        cmd_rm=lambda _p: 0,
    )
    assert rc == 0


def test_no_arg_flow_lazygit_runs_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_tty(monkeypatch)
    runs: list[tuple[list[str], object]] = []

    def fake_run(*args, **kwargs) -> object:
        runs.append((args[0], kwargs.get("cwd")))
        return None

    monkeypatch.setattr(interactive_flow.subprocess, "run", fake_run)

    rc = interactive_flow.no_arg_flow(
        Path("/tmp/base"),
        Path("/tmp/base"),
        initial_filter_expr="",
        cmd_list=lambda _b: 0,
        run_textual_ui=lambda _b, _c, _q: ("lazygit", Path("/tmp/base/p"), []),
        run_post_commands=lambda _p, _c: None,
        open_with_mode=lambda _b, _p: 0,
        cmd_archive_mv=lambda _b, _p: 0,
        open_shell_in_dir=lambda _p: 0,
        cmd_archive_restore_entry=lambda _b, _p: 0,
        cmd_rm=lambda _p: 0,
    )
    assert rc == 0
    assert runs and runs[0][0][0] == "lazygit"


def test_no_arg_flow_unknown_action_returns_0(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_tty(monkeypatch)
    rc = interactive_flow.no_arg_flow(
        Path("/tmp/base"),
        Path("/tmp/base"),
        initial_filter_expr="",
        cmd_list=lambda _b: 0,
        run_textual_ui=lambda _b, _c, _q: ("unknown", None, []),
        run_post_commands=lambda _p, _c: None,
        open_with_mode=lambda _b, _p: 0,
        cmd_archive_mv=lambda _b, _p: 0,
        open_shell_in_dir=lambda _p: 0,
        cmd_archive_restore_entry=lambda _b, _p: 0,
        cmd_rm=lambda _p: 0,
    )
    assert rc == 0
