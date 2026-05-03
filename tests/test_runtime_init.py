from __future__ import annotations

from pathlib import Path

from homebase.core import runtime_init as runtime_init


def test_resolve_initial_filter_expression_promotes_named() -> None:
    out = runtime_init.resolve_initial_filter_expression(
        "recent",
        resolve_filter_expression=lambda expr: (expr, None),
    )
    assert out == "@recent"


def test_load_runtime_config_uses_loaders(tmp_path: Path) -> None:
    cfg = runtime_init.load_runtime_config(
        tmp_path,
        default_archive_tz_name="UTC",
        load_property_defs=lambda _p: ["a"],
        load_wip_symbol_map=lambda _p: {"!": 1},
        load_saved_filter_queries=lambda _p: ({"n": "#x"}, ["#x"]),
        load_suffixes=lambda _p: ["tmp"],
        load_file_view_exclude_patterns=lambda _p: ["*.pyc"],
        load_custom_actions=lambda _p: [],
        load_open_mode_config=lambda _p: {},
        load_notes_config=lambda _p: {},
        load_reconcile_config=lambda _p: {},
        load_cache_profile_table=lambda _p: {},
        load_archive_timezone_name=lambda _p: "UTC",
    )
    assert cfg.property_defs == ["a"]
    assert cfg.named_filters == {"n": "#x"}
