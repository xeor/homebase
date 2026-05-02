from __future__ import annotations

from pathlib import Path

from homebase.core.models import ProjectRow
from homebase.workspace import filter_compile


def _row() -> ProjectRow:
    return ProjectRow(
        path=Path("/tmp/demo"),
        name="demo",
        branch="main",
        dirty="",
        last="2026-01-01",
        src="git",
        created="2026-01-01",
        tags=["cli"],
        properties=["act"],
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
    assert filter_compile.match_query(_row(), "act")


def test_compile_filter_expr_supports_tag_query() -> None:
    pred, err = filter_compile.compile_filter_expr("#cli")
    assert err is None
    assert pred(_row())
