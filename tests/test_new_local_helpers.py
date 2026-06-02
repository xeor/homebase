"""Tests for the private helpers in ``workspace/new/sources/local.py``:
``_debug_enabled``, ``_debug_log``, ``_decide_repo_wrap``."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from homebase.workspace.new.base import NewOptions
from homebase.workspace.new.sources import local as local_source


def _make_options(*, yes: bool = False) -> NewOptions:
    return NewOptions(
        tmp=False,
        timestamp=False,
        open=False,
        confirm=False,
        ts_name=False,
        alpha_name=False,
        ask_name=False,
        ask_source=False,
        archive=False,
        dry_run=False,
        yes=yes,
        multi=False,
        template="",
        tags=(),
        post=(),
        from_project="",
    )


# ---- _debug_enabled -------------------------------------------------


def test_debug_enabled_true_for_env_flag(monkeypatch) -> None:
    monkeypatch.setattr(local_source, "verbose_enabled", lambda _level: False)
    for raw in ("1", "true", "TRUE", "yes", "on", "y"):
        monkeypatch.setenv("HOMEBASE_DEBUG", raw)
        assert local_source._debug_enabled() is True


def test_debug_enabled_false_for_unset_or_falsy(monkeypatch) -> None:
    monkeypatch.setattr(local_source, "verbose_enabled", lambda _level: False)
    monkeypatch.delenv("HOMEBASE_DEBUG", raising=False)
    assert local_source._debug_enabled() is False
    for raw in ("0", "false", "no", "off", "anything-else"):
        monkeypatch.setenv("HOMEBASE_DEBUG", raw)
        assert local_source._debug_enabled() is False


def test_debug_enabled_respects_verbose_flag(monkeypatch) -> None:
    """If ``verbose_enabled(3)`` is on (``-vvv`` etc.) debug is on,
    regardless of the env flag."""
    monkeypatch.setattr(local_source, "verbose_enabled", lambda _level: True)
    monkeypatch.delenv("HOMEBASE_DEBUG", raising=False)
    assert local_source._debug_enabled() is True


# ---- _debug_log -----------------------------------------------------


def test_debug_log_suppresses_output_when_disabled(monkeypatch, capsys) -> None:
    monkeypatch.setattr(local_source, "_debug_enabled", lambda: False)
    local_source._debug_log("should not appear")
    err = capsys.readouterr().err
    assert err == ""


def test_debug_log_writes_to_stderr_when_enabled(monkeypatch, capsys) -> None:
    monkeypatch.setattr(local_source, "_debug_enabled", lambda: True)
    local_source._debug_log("hello")
    err = capsys.readouterr().err
    assert "[debug] local: hello" in err


# ---- _decide_repo_wrap ----------------------------------------------


def test_decide_repo_wrap_false_when_no_git_dir(tmp_path: Path) -> None:
    """A plain directory (no ``.git/``) is never wrapped — there's no
    repo to nest under ``repo/``."""
    src = tmp_path / "plain"
    src.mkdir()
    assert local_source._decide_repo_wrap(src, _make_options()) is False


def test_decide_repo_wrap_true_with_git_and_yes(tmp_path: Path) -> None:
    """``--yes`` skips the prompt and wraps unconditionally."""
    src = tmp_path / "repo"
    src.mkdir()
    (src / ".git").mkdir()
    assert local_source._decide_repo_wrap(src, _make_options(yes=True)) is True


def test_decide_repo_wrap_true_non_interactive_no_tty(monkeypatch, tmp_path: Path) -> None:
    """Without an interactive stdin (e.g. piped invocations) the
    helper wraps unconditionally — the user can't answer the prompt
    so we pick the safer default."""
    src = tmp_path / "repo"
    src.mkdir()
    (src / ".git").mkdir()
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert local_source._decide_repo_wrap(src, _make_options()) is True


def test_decide_repo_wrap_falls_back_to_true_on_prompt_error(
    monkeypatch, tmp_path: Path,
) -> None:
    """If the confirm prompt raises (no readline, EOF, etc.) the
    helper picks the documented default — wrap."""
    src = tmp_path / "repo"
    src.mkdir()
    (src / ".git").mkdir()
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    def _boom(*_a, **_kw):
        raise local_source.PromptError("no readline")

    monkeypatch.setattr(local_source, "confirm", _boom)
    assert local_source._decide_repo_wrap(src, _make_options()) is True


def test_decide_repo_wrap_uses_confirm_answer_when_interactive(
    monkeypatch, tmp_path: Path,
) -> None:
    src = tmp_path / "repo"
    src.mkdir()
    (src / ".git").mkdir()
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    answers: list[Any] = [False]
    monkeypatch.setattr(local_source, "confirm", lambda *_a, **_kw: answers.pop(0))
    assert local_source._decide_repo_wrap(src, _make_options()) is False


def test_decide_repo_wrap_recognises_git_file_as_well(tmp_path: Path) -> None:
    """``.git`` can be either a directory (regular repo) or a file
    (worktree marker pointing at the parent admin dir). The helper
    only checks ``.exists()`` — both should trigger the wrap."""
    src = tmp_path / "wt"
    src.mkdir()
    (src / ".git").write_text("gitdir: /elsewhere\n")
    assert local_source._decide_repo_wrap(src, _make_options(yes=True)) is True
