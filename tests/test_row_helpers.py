from __future__ import annotations

from pathlib import Path

from homebase.core.models import ProjectRow
from homebase.ui.table import row_helpers


def _row(*, properties: list[str] | None = None) -> ProjectRow:
    return ProjectRow(
        path=Path("/tmp/demo"),
        name="demo",
        branch="main",
        dirty="",
        last="2026-01-01",
        src="git",
        created="2026-01-01",
        tags=["cli"],
        properties=properties or [],
        description="demo project",
        created_ts=1,
        last_ts=1,
        git_ts=1,
        opened_ts=1,
        is_fork=False,
        is_tmp=False,
        archived=False,
        restore_target=None,
        archived_ts=0,
        wip=False,
        suffix=None,
    )


def test_match_query_lower_matches_property_token() -> None:
    assert row_helpers.match_query_lower(_row(properties=["act"]), "act")


def test_match_query_lower_returns_false_when_not_present() -> None:
    assert not row_helpers.match_query_lower(_row(properties=["act"]), "does-not-exist")


def test_match_query_lower_blank_query_matches() -> None:
    assert row_helpers.match_query_lower(_row(), "") is True


def test_same_path_handles_none_inputs() -> None:
    assert row_helpers.same_path(None, Path("/x")) is False
    assert row_helpers.same_path(Path("/x"), None) is False
    assert row_helpers.same_path(None, None) is False


def test_same_path_direct_equality() -> None:
    p = Path("/tmp/demo")
    assert row_helpers.same_path(p, p) is True


def test_same_path_resolves_relative(tmp_path: Path) -> None:
    a = tmp_path / "p"
    a.mkdir()
    b = tmp_path / "p" / "."
    assert row_helpers.same_path(a, b) is True


def test_has_open_pane_threshold() -> None:
    counts = {Path("/a"): 0, Path("/b"): 2}
    assert row_helpers.has_open_pane(Path("/a"), counts) is False
    assert row_helpers.has_open_pane(Path("/b"), counts) is True
    assert row_helpers.has_open_pane(Path("/c"), counts) is False


def test_has_readme_file_true_when_present(tmp_path: Path) -> None:
    row_path = tmp_path / "p"
    row_path.mkdir()
    (row_path / "README.md").write_text("hello")
    row = _row()
    row.path = row_path
    assert row_helpers.has_readme_file(row) is True


def test_has_readme_file_false_when_missing(tmp_path: Path) -> None:
    row_path = tmp_path / "p"
    row_path.mkdir()
    row = _row()
    row.path = row_path
    assert row_helpers.has_readme_file(row) is False


def test_has_readme_file_false_for_packed(tmp_path: Path) -> None:
    row = _row()
    row.packed = True
    assert row_helpers.has_readme_file(row) is False


def test_has_readme_file_false_when_path_not_dir(tmp_path: Path) -> None:
    file_path = tmp_path / "f.txt"
    file_path.write_text("x")
    row = _row()
    row.path = file_path
    assert row_helpers.has_readme_file(row) is False


def test_has_notes_file_uses_resolver(tmp_path: Path) -> None:
    notes_path = tmp_path / "notes.md"
    notes_path.write_text("hello")
    row = _row()
    assert row_helpers.has_notes_file(
        row,
        resolve_notes_path_for_row=lambda _r: notes_path,
    ) is True


def test_has_notes_file_false_when_resolver_raises() -> None:
    row = _row()

    def boom(_r: object) -> Path:
        raise ValueError("nope")

    assert row_helpers.has_notes_file(row, resolve_notes_path_for_row=boom) is False


def test_has_notes_file_false_when_file_missing(tmp_path: Path) -> None:
    row = _row()
    assert (
        row_helpers.has_notes_file(
            row,
            resolve_notes_path_for_row=lambda _r: tmp_path / "missing.md",
        )
        is False
    )
