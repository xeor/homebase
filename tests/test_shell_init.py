"""Tests for the `b shell-init <shell>` wrapper script generator.

The wrapper is what makes the parent shell `cd` into a target dir
when the binary writes to `HOMEBASE_CD_FILE`. If any of these
literal tokens drift out of the script the integration is silently
broken — these tests pin the contract.
"""
from __future__ import annotations

import pytest

from homebase.cli import parser as cli_parser
from homebase.cli import shell_init


def test_bash_zsh_script_contains_wrapper_contract() -> None:
    """The bash/zsh script must define a `b()` function that wires up
    HOMEBASE_CD_FILE, falls through to `command b` (so we don't
    recurse into the wrapper), and uses `builtin cd` (so a
    user-defined `cd` alias can't break us)."""
    body = shell_init.shell_init_script("bash")
    assert body == shell_init.shell_init_script("zsh"), (
        "bash and zsh share the same wrapper body"
    )
    assert "b() {" in body
    assert "mktemp" in body
    assert "HOMEBASE_CD_FILE=" in body
    assert "command b" in body
    assert "builtin cd" in body
    assert "rm -f" in body


def test_fish_script_contains_wrapper_contract() -> None:
    body = shell_init.shell_init_script("fish")
    assert "function b" in body
    assert "set -l f (mktemp)" in body
    assert "HOMEBASE_CD_FILE=" in body
    assert "command b $argv" in body
    assert "builtin cd" in body
    assert "set -l rc $status" in body


def test_shell_init_script_rejects_unknown_shell() -> None:
    with pytest.raises(ValueError):
        shell_init.shell_init_script("powershell")


def test_parser_accepts_shell_init_subcommand() -> None:
    """`b shell-init fish` parses; an unknown shell exits non-zero."""
    parser = cli_parser.build_cli_parser()
    ns = parser.parse_args(["shell-init", "fish"])
    assert ns.command == "shell-init"
    assert ns.shell == "fish"


def test_parser_rejects_unknown_shell_in_shell_init() -> None:
    parser = cli_parser.build_cli_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["shell-init", "powershell"])


# ============================================================
# open_shell_in_dir — the binary-side half of the protocol.
# ============================================================


def test_open_shell_writes_rendezvous_when_env_set(
    monkeypatch, tmp_path,
) -> None:
    """With ``HOMEBASE_CD_FILE`` set, the function must write the
    target path to that file (with fsync) and return 0 cleanly.
    ``os.execvp`` must NOT fire — we monkeypatch it to raise so a
    fallback would crash the test."""
    from homebase.tmux import flow

    target = tmp_path / "proj"
    target.mkdir()
    cd_file = tmp_path / "rendezvous"
    cd_file.touch()
    monkeypatch.setenv("HOMEBASE_CD_FILE", str(cd_file))

    execvp_called: list[tuple[str, list[str]]] = []
    def boom(prog, argv):
        execvp_called.append((prog, list(argv)))
        raise RuntimeError("must not exec when wrapper handed us a file")
    monkeypatch.setattr(flow.os, "execvp", boom)

    rc = flow.open_shell_in_dir(target)
    assert rc == 0
    assert execvp_called == []
    assert cd_file.read_text() == str(target.resolve())


def test_open_shell_falls_back_to_subshell_with_hint(
    monkeypatch, capsys, tmp_path,
) -> None:
    """No ``HOMEBASE_CD_FILE`` + TTY-on-stdout → exec a sub-shell AND
    print a one-line stderr hint pointing at ``b shell-init``."""
    from homebase.tmux import flow

    target = tmp_path / "proj"
    target.mkdir()
    monkeypatch.delenv("HOMEBASE_CD_FILE", raising=False)
    monkeypatch.delenv("HOMEBASE_QUIET_FALLBACK", raising=False)
    monkeypatch.setenv("SHELL", "/bin/bash")
    monkeypatch.setattr(flow.sys.stdout, "isatty", lambda: True)

    chdir_calls: list[str] = []
    monkeypatch.setattr(flow.os, "chdir", lambda p: chdir_calls.append(str(p)))
    execvp_calls: list[tuple[str, list[str]]] = []
    def fake_execvp(prog, argv):
        execvp_calls.append((prog, list(argv)))
        raise RuntimeError("execvp would have replaced the process")
    monkeypatch.setattr(flow.os, "execvp", fake_execvp)

    with pytest.raises(RuntimeError):
        flow.open_shell_in_dir(target)

    captured = capsys.readouterr()
    assert "shell-init" in captured.err
    assert "Falling back to sub-shell" in captured.err
    assert execvp_calls == [("/bin/bash", ["/bin/bash"])]
    assert chdir_calls == [str(target)]


def test_open_shell_quiet_fallback_env_suppresses_hint(
    monkeypatch, capsys, tmp_path,
) -> None:
    from homebase.tmux import flow

    target = tmp_path / "proj"
    target.mkdir()
    monkeypatch.delenv("HOMEBASE_CD_FILE", raising=False)
    monkeypatch.setenv("HOMEBASE_QUIET_FALLBACK", "1")
    monkeypatch.setenv("SHELL", "/bin/bash")
    monkeypatch.setattr(flow.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(flow.os, "chdir", lambda _p: None)
    monkeypatch.setattr(
        flow.os, "execvp", lambda *_a: (_ for _ in ()).throw(RuntimeError("x"))
    )

    with pytest.raises(RuntimeError):
        flow.open_shell_in_dir(target)

    captured = capsys.readouterr()
    assert captured.err == ""


def test_open_shell_noop_when_not_tty(monkeypatch, tmp_path) -> None:
    from homebase.tmux import flow

    target = tmp_path / "proj"
    target.mkdir()
    monkeypatch.delenv("HOMEBASE_CD_FILE", raising=False)
    monkeypatch.setattr(flow.sys.stdout, "isatty", lambda: False)

    # ``execvp`` would crash the test process. Monkeypatch it to
    # explode just in case the no-op branch is broken.
    monkeypatch.setattr(
        flow.os, "execvp", lambda *_a: pytest.fail("must not exec")
    )

    rc = flow.open_shell_in_dir(target)
    assert rc == 0


def test_open_shell_falls_back_when_rendezvous_unwritable(
    monkeypatch, capsys, tmp_path,
) -> None:
    """If the rendezvous file path can't be opened for writing (e.g.
    the wrapper crashed mid-mktemp), the function must not crash —
    it falls through to the sub-shell path so the user still gets
    SOMETHING useful."""
    from homebase.tmux import flow

    target = tmp_path / "proj"
    target.mkdir()
    bogus = tmp_path / "this-dir-does-not-exist" / "rendezvous"
    monkeypatch.setenv("HOMEBASE_CD_FILE", str(bogus))
    monkeypatch.setenv("SHELL", "/bin/bash")
    monkeypatch.setattr(flow.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(flow.os, "chdir", lambda _p: None)
    execvp_calls: list[tuple[str, list[str]]] = []
    def fake_execvp(prog, argv):
        execvp_calls.append((prog, list(argv)))
        raise RuntimeError("exec")
    monkeypatch.setattr(flow.os, "execvp", fake_execvp)

    with pytest.raises(RuntimeError):
        flow.open_shell_in_dir(target)
    assert execvp_calls == [("/bin/bash", ["/bin/bash"])]
