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
