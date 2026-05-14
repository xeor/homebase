from __future__ import annotations

import io
from pathlib import Path

import pytest

from homebase.cli.parser import build_cli_parser
from homebase.workspace.new import cmd_new


def _run(base: Path, cwd: Path, args: list[str]) -> int:
    ns = build_cli_parser().parse_args(["new", *args])
    return cmd_new(ns, base, cwd)


class _FakeTTY(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.fixture
def fake_stdin(monkeypatch):
    def _set(text: str) -> None:
        monkeypatch.setattr("sys.stdin", _FakeTTY(text))
    return _set


def test_ask_name_uses_user_input(tmp_path: Path, fake_stdin) -> None:
    fake_stdin("typed-name\n")
    rc = _run(tmp_path, tmp_path, ["myproj", "--ask-name"])
    assert rc == 0
    assert (tmp_path / "typed-name").is_dir()
    assert not (tmp_path / "myproj").exists()


def test_ask_name_falls_back_to_inferred_default(tmp_path: Path, fake_stdin) -> None:
    # Empty input → use the suggested default (which is `myproj` itself).
    fake_stdin("\n")
    rc = _run(tmp_path, tmp_path, ["myproj", "--ask-name"])
    assert rc == 0
    assert (tmp_path / "myproj").is_dir()


def test_ask_name_rejects_explicit_name_positional(tmp_path: Path, fake_stdin) -> None:
    fake_stdin("\n")
    rc = _run(tmp_path, tmp_path, ["myproj", "altname", "--ask-name"])
    assert rc == 2


def test_ask_name_non_tty_fails(tmp_path: Path) -> None:
    # Default sys.stdin in pytest is not a TTY.
    rc = _run(tmp_path, tmp_path, ["myproj", "--ask-name"])
    assert rc == 2


def test_ask_source_overrides_detection(tmp_path: Path, fake_stdin) -> None:
    # `myproj` would auto-detect as empty. With --ask-source we type
    # "empty" explicitly to confirm the prompt fires.
    fake_stdin("empty\n")
    rc = _run(tmp_path, tmp_path, ["myproj", "--ask-source"])
    assert rc == 0
    assert (tmp_path / "myproj").is_dir()


def test_ask_source_invalid_key_fails(tmp_path: Path, fake_stdin) -> None:
    fake_stdin("nope\n")
    rc = _run(tmp_path, tmp_path, ["myproj", "--ask-source"])
    assert rc == 2


def test_ask_source_skipped_when_mode_flag_set(tmp_path: Path) -> None:
    # No stdin needed because --empty bypasses ask-source.
    rc = _run(tmp_path, tmp_path, ["myproj", "--empty", "--ask-source"])
    assert rc == 0


def test_multi_with_ask_name_per_item(tmp_path: Path, fake_stdin) -> None:
    fake_stdin("first\nsecond\n")
    rc = _run(tmp_path, tmp_path, ["--multi", "a", "b", "--ask-name"])
    assert rc == 0
    assert (tmp_path / "first").is_dir()
    assert (tmp_path / "second").is_dir()
    assert not (tmp_path / "a").exists()
    assert not (tmp_path / "b").exists()


def test_confirm_yes_proceeds(tmp_path: Path, fake_stdin) -> None:
    fake_stdin("y\n")
    rc = _run(tmp_path, tmp_path, ["myproj", "--confirm"])
    assert rc == 0
    assert (tmp_path / "myproj").is_dir()


def test_confirm_no_aborts(tmp_path: Path, fake_stdin) -> None:
    fake_stdin("n\n")
    rc = _run(tmp_path, tmp_path, ["myproj", "--confirm"])
    assert rc == 1
    assert not (tmp_path / "myproj").exists()


def test_confirm_yes_flag_skips_prompt(tmp_path: Path) -> None:
    # No stdin manipulation: --yes should bypass confirm entirely.
    rc = _run(tmp_path, tmp_path, ["myproj", "--confirm", "--yes"])
    assert rc == 0
