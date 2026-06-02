"""Unit tests for the pure helpers on ``RestorePathScreen``.

We bypass Textual's compose/mount lifecycle by allocating bare
instances via ``__new__`` and wiring just the attributes the helpers
actually read."""
from __future__ import annotations

from pathlib import Path

from homebase.ui.screens.restore import RestorePathScreen


def _stub(base_dir: Path, default: Path) -> RestorePathScreen:
    screen = RestorePathScreen.__new__(RestorePathScreen)
    screen.base_dir_ref = base_dir
    screen.default_target = default
    return screen


def test_resolve_returns_empty_path_for_blank_input(tmp_path: Path) -> None:
    screen = _stub(tmp_path, tmp_path / "x")
    assert screen._resolve("") == Path("")
    assert screen._resolve("   ") == Path("")


def test_resolve_keeps_absolute_path_as_is(tmp_path: Path) -> None:
    screen = _stub(tmp_path, tmp_path / "x")
    target = tmp_path.resolve() / "alpha"
    assert screen._resolve(str(target)) == target


def test_resolve_joins_relative_path_under_base_dir(tmp_path: Path) -> None:
    screen = _stub(tmp_path, tmp_path / "x")
    assert screen._resolve("sub/proj") == tmp_path / "sub/proj"


def test_validate_rejects_empty_input(tmp_path: Path) -> None:
    screen = _stub(tmp_path, tmp_path / "x")
    ok, msg, resolved = screen._validate("")
    assert ok is False
    assert "empty" in msg
    assert resolved is None


def test_validate_rejects_existing_target(tmp_path: Path) -> None:
    """The check is "does the path already exist" — if yes the restore
    is refused (we don't want to silently overwrite)."""
    (tmp_path / "occupied").mkdir()
    screen = _stub(tmp_path, tmp_path / "x")
    ok, msg, resolved = screen._validate("occupied")
    assert ok is False
    assert "exists" in msg
    assert resolved is not None  # the resolved path is still reported


def test_validate_rejects_outside_base_dir(tmp_path: Path, monkeypatch) -> None:
    """The screen calls ``normalize_restore_target`` with
    ``allow_outside_base=False`` — paths outside the base dir must be
    refused with a ValueError translated into ``(False, msg)``."""
    screen = _stub(tmp_path, tmp_path / "x")
    # /tmp is outside tmp_path on every CI / dev box.
    ok, msg, resolved = screen._validate("/tmp/nope")
    assert ok is False
    assert msg
    assert resolved is None


def test_validate_accepts_path_under_base(tmp_path: Path) -> None:
    screen = _stub(tmp_path, tmp_path / "x")
    ok, msg, resolved = screen._validate("brand-new")
    assert ok is True
    assert resolved == tmp_path / "brand-new"
    assert "ok" in msg


def test_validate_flags_missing_parent_as_warning_but_ok(tmp_path: Path) -> None:
    """A path whose parent doesn't exist is still acceptable — the
    restore step will create it. The status message just notes that
    the parent will be created so the user isn't surprised."""
    screen = _stub(tmp_path, tmp_path / "x")
    ok, msg, resolved = screen._validate("deep/nest/target")
    assert ok is True
    assert "parent will be created" in msg
    assert resolved == tmp_path / "deep" / "nest" / "target"
