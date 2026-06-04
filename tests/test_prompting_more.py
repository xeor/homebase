from __future__ import annotations

import io

import pytest

from homebase.core import prompting


def _force_non_interactive(monkeypatch: pytest.MonkeyPatch, stdin_text: str) -> None:
    monkeypatch.setattr(prompting.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(prompting.sys.stdout, "isatty", lambda: False)
    monkeypatch.setattr(prompting.sys, "stdin", io.StringIO(stdin_text))


def test_prompt_readline_non_interactive_returns_non_interactive_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _force_non_interactive(monkeypatch, "")
    out = prompting.prompt_readline(
        "?: ",
        default="d",
        non_interactive_default="ni",
    )
    assert out == "ni"


def test_prompt_readline_non_interactive_blank_uses_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _force_non_interactive(monkeypatch, "")
    assert prompting.prompt_readline("?: ", default="d") == "d"


def test_prompt_readline_non_interactive_blank_text_uses_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _force_non_interactive(monkeypatch, "   \n")
    assert prompting.prompt_readline("?: ", default="d") == "d"


def test_prompt_readline_non_interactive_returns_stripped_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _force_non_interactive(monkeypatch, "  hello  \n")
    assert prompting.prompt_readline("?: ", default="d") == "hello"


def test_prompt_readline_cancel_tokens_return_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for token in ("q", "quit", "exit", "Cancel", "ABORT"):
        _force_non_interactive(monkeypatch, f"{token}\n")
        assert prompting.prompt_readline("?: ", default="d") is None


def test_prompt_yes_no_default_used_on_blank_non_interactive(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(prompting.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(prompting.sys.stdout, "isatty", lambda: False)
    assert (
        prompting.prompt_yes_no(
            "ok?", default=True, read=lambda *a, **kw: ""
        )
        is True
    )
    out = capsys.readouterr().out
    assert "non-interactive, using default" in out


def test_prompt_yes_no_returns_false_when_read_returns_none() -> None:
    assert (
        prompting.prompt_yes_no("ok?", default=True, read=lambda *a, **kw: None)
        is False
    )


def test_prompt_yes_no_invalid_non_interactive_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(prompting.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(prompting.sys.stdout, "isatty", lambda: False)
    assert (
        prompting.prompt_yes_no(
            "ok?", default=False, read=lambda *a, **kw: "huh"
        )
        is False
    )
    assert "invalid non-interactive answer" in capsys.readouterr().out


def test_prompt_yes_no_accepts_no_text() -> None:
    assert (
        prompting.prompt_yes_no("ok?", default=True, read=lambda *a, **kw: "no")
        is False
    )


def test_prompt_readline_interactive_eof_returns_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prompting.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(prompting.sys.stdout, "isatty", lambda: True)

    def fake_input(_prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", fake_input)
    assert prompting.prompt_readline("?: ", default="fallback") == "fallback"
