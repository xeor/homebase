from __future__ import annotations

from pathlib import Path

from homebase.core.constants import ARCHIVE_DIR_NAME
from homebase.core.models import ProjectRow
from homebase.workspace import rows


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


def test_match_query_matches_property_token() -> None:
    assert rows.match_query(_row(properties=["act"]), "act")


def test_match_query_matches_path_text() -> None:
    assert rows.match_query(_row(), "tmp/demo")


def test_archived_restore_target_handles_new_packed_name() -> None:
    base_dir = Path("/tmp/base")
    archived_entry = base_dir / ARCHIVE_DIR_NAME / "2026-05-11_demo.tgz"
    target = rows.archived_restore_target(base_dir, archived_entry)
    assert target == base_dir / "demo"


def test_archived_restore_target_strips_year_subdir() -> None:
    base_dir = Path("/tmp/base")
    archived_entry = base_dir / ARCHIVE_DIR_NAME / "2024" / "2024-05-01_demo"
    target = rows.archived_restore_target(base_dir, archived_entry)
    assert target == base_dir / "demo"


def test_archived_restore_target_strips_year_for_packed() -> None:
    base_dir = Path("/tmp/base")
    archived_entry = base_dir / ARCHIVE_DIR_NAME / "2024" / "2024-05-01_demo.tgz"
    target = rows.archived_restore_target(base_dir, archived_entry)
    assert target == base_dir / "demo"


def test_archived_restore_target_strips_prefix_with_zero_segments() -> None:
    base_dir = Path("/tmp/base")
    archived_entry = base_dir / ARCHIVE_DIR_NAME / "2003" / "2003-00-00_ghost"
    target = rows.archived_restore_target(base_dir, archived_entry)
    assert target == base_dir / "ghost"
