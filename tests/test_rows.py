from __future__ import annotations

from pathlib import Path

from homebase.core import utils as core_utils
from homebase.core.constants import ARCHIVE_DIR_NAME, ARCHIVE_TZ, PACKED_ARCHIVE_SUFFIX
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


def test_archived_restore_target_handles_packed_archive_suffix() -> None:
    base_dir = Path("/tmp/base")
    suffix = core_utils.archive_iso_from_ts(1_700_000_000, ARCHIVE_TZ)
    archived_entry = base_dir / ARCHIVE_DIR_NAME / f"demo.{suffix}{PACKED_ARCHIVE_SUFFIX}"
    target = rows.archived_restore_target(base_dir, archived_entry)
    assert target == base_dir / "demo"
