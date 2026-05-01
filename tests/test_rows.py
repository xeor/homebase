from __future__ import annotations

from pathlib import Path

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
