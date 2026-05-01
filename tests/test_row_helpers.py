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
