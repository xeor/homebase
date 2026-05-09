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


def test_match_query_uses_precomputed_haystack(monkeypatch) -> None:
    from homebase.workspace import projects as projects_mod

    row = _row()
    row.haystack_lower = "preset-cached-token"

    def _explode(**_kwargs):
        raise AssertionError("haystack must not be rebuilt when precomputed")

    monkeypatch.setattr(
        projects_mod,
        "build_row_haystack_lower",
        _explode,
    )
    monkeypatch.setattr(
        filter_compile,
        "build_row_haystack_lower",
        _explode,
    )

    assert filter_compile.match_query(row, "preset-cached-token")
    assert not filter_compile.match_query(row, "no-such-thing")


def test_match_query_falls_back_when_haystack_missing() -> None:
    row = _row()
    assert row.haystack_lower == ""
    assert filter_compile.match_query(row, "demo")
    assert filter_compile.match_query(row, "main")


def test_project_row_post_init_derives_tags_lower() -> None:
    row = _row()
    assert row.tags_lower == frozenset({"cli"})


def test_compile_filter_expr_tag_match_uses_cached_set() -> None:
    row = _row()
    row.tags = ["original-only-in-tags"]
    row.tags_lower = frozenset({"only-in-cache"})
    pred_cached, _ = filter_compile.compile_filter_expr("#only-in-cache")
    pred_tags, _ = filter_compile.compile_filter_expr("#original-only-in-tags")
    assert pred_cached(row) is True
    assert pred_tags(row) is False
