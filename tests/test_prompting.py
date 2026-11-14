from __future__ import annotations

import builtins

import pytest

from homebase.core import prompting as prompting


def test_prompt_yes_no_accepts_yes() -> None:
    out = prompting.prompt_yes_no(
        "q?",
        default=False,
        read=lambda *_args, **_kwargs: "y",
    )
    assert out is True


def test_confirm_raises_on_cancel() -> None:
    with pytest.raises(KeyboardInterrupt):
        prompting.confirm(lambda *_args, **_kwargs: None)


def test_prompt_readline_keyboard_interrupt_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompting.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(prompting.sys.stdout, "isatty", lambda: True)

    def _raise(_prompt: str) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(builtins, "input", _raise)
    assert prompting.prompt_readline("q? ") is None


def test_prompt_readline_keyboard_interrupt_can_abort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompting.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(prompting.sys.stdout, "isatty", lambda: True)

    def _raise(_prompt: str) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(builtins, "input", _raise)
    with pytest.raises(KeyboardInterrupt):
        prompting.prompt_readline("q? ", abort_on_interrupt=True)


def test_line_mode_tty_sets_and_restores_canonical_mode() -> None:
    """Regression: from fish's fish_prompt hook the tty has -icanon -icrnl, so
    input() never saw Enter (b herdr load --ask hung)."""
    import os
    import termios

    from homebase.core.prompting import line_mode_tty

    master, slave = os.openpty()
    try:
        raw = termios.tcgetattr(slave)
        raw[0] &= ~termios.ICRNL
        raw[3] &= ~(termios.ICANON | termios.ECHO)
        termios.tcsetattr(slave, termios.TCSANOW, raw)
        with line_mode_tty(slave):
            mode = termios.tcgetattr(slave)
            assert mode[0] & termios.ICRNL
            assert mode[3] & termios.ICANON and mode[3] & termios.ECHO
            os.write(master, b"y\r")
            assert os.read(slave, 10) == b"y\n"
        assert termios.tcgetattr(slave)[:6] == raw[:6]
    finally:
        os.close(master)
        os.close(slave)


def test_line_mode_tty_ignores_non_tty(tmp_path) -> None:
    from homebase.core.prompting import line_mode_tty

    with (tmp_path / "f").open("w") as handle, line_mode_tty(handle.fileno()):
        pass
