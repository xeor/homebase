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


def test_compile_filter_expr_double_hash_uses_configured_tree(
    tmp_path: Path, monkeypatch,
) -> None:
    """End-to-end: when BASE_DIR points at a workspace with tag_rules,
    ``##X`` walks the configured ancestor tree."""
    import yaml

    from homebase.config import tag_rules
    from homebase.config.store import clear_global_config_cache
    from homebase.core.constants import (
        ENV_BASE_DIR,
        GLOBAL_CONFIG_FILE_NAME,
        HOMEBASE_DIR_NAME,
    )

    base = tmp_path / "base"
    (base / HOMEBASE_DIR_NAME).mkdir(parents=True)
    cfg = base / HOMEBASE_DIR_NAME / GLOBAL_CONFIG_FILE_NAME
    cfg.write_text(yaml.safe_dump({"tag_rules": [
        {"match": "^prio:", "parents": ["priority"]},
        {"tags": ["priority"], "parents": ["meta"]},
    ]}))
    clear_global_config_cache()
    tag_rules.clear_tag_rules_cache()
    monkeypatch.setenv(ENV_BASE_DIR, str(base))

    pred, err = filter_compile.compile_filter_expr("##priority")
    assert err is None

    row_direct = _row()
    row_direct.tags = ["priority"]
    row_direct.tags_lower = frozenset({"priority"})
    assert pred(row_direct) is True

    row_child = _row()
    row_child.tags = ["prio:p0"]
    row_child.tags_lower = frozenset({"prio:p0"})
    assert pred(row_child) is True

    row_unrelated = _row()
    row_unrelated.tags = ["home"]
    row_unrelated.tags_lower = frozenset({"home"})
    assert pred(row_unrelated) is False

    # ``##meta`` reaches prio:p0 transitively (priority → meta).
    pred_meta, _ = filter_compile.compile_filter_expr("##meta")
    assert pred_meta(row_child) is True
    assert pred_meta(row_direct) is True  # priority itself rolls up
    assert pred_meta(row_unrelated) is False


def test_compile_filter_expr_double_hash_without_base_dir_falls_back(
    monkeypatch,
) -> None:
    """No BASE_DIR env → no tree lookup, but a direct hit on the
    parent tag still matches."""
    from homebase.core.constants import ENV_BASE_DIR

    monkeypatch.delenv(ENV_BASE_DIR, raising=False)
    pred, _err = filter_compile.compile_filter_expr("##priority")
    row = _row()
    row.tags = ["priority"]
    row.tags_lower = frozenset({"priority"})
    assert pred(row) is True
    row.tags = ["prio:p0"]
    row.tags_lower = frozenset({"prio:p0"})
    assert pred(row) is False
