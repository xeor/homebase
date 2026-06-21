from __future__ import annotations

from pathlib import Path

import pytest

from homebase.config import prefs
from homebase.config import store as config_store
from homebase.core.constants import (
    DEFAULT_ARCHIVE_TZ_NAME,
    NAMED_FILTERS,
    NEW_PROJECT_DEFAULTS,
    SAVED_FILTER_QUERIES,
    WIP_OPEN_SYMBOL_MAP,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    config_store.clear_global_config_cache()
    NAMED_FILTERS.clear()
    SAVED_FILTER_QUERIES.clear()


def test_load_post_command_options_strings(tmp_path: Path) -> None:
    config_store.save_global_config_dict(
        tmp_path,
        {"new": {"post-commands": ["echo hi", "  ", "echo hi"]}},
    )
    out = prefs.load_post_command_options(tmp_path)
    keys = [item.key for item in out]
    assert keys[0] == "echo_hi"
    assert "echo_hi_2" in keys


def test_load_post_command_options_dicts(tmp_path: Path) -> None:
    config_store.save_global_config_dict(
        tmp_path,
        {
            "new": {
                "post-commands": [
                    {"label": "Setup", "command": "make setup"},
                    {"command": "echo only-command"},
                    {"label": "", "command": ""},  # skipped
                    "not-a-dict-or-str-skipped",
                    123,
                ]
            }
        },
    )
    out = prefs.load_post_command_options(tmp_path)
    assert [(o.label, o.command) for o in out] == [
        ("Setup", "make setup"),
        ("echo only-command", "echo only-command"),
        ("not-a-dict-or-str-skipped", "not-a-dict-or-str-skipped"),
    ]


def test_load_post_command_options_handles_invalid_shapes(tmp_path: Path) -> None:
    config_store.save_global_config_dict(tmp_path, {"new": "scalar"})
    assert prefs.load_post_command_options(tmp_path) == []

    config_store.clear_global_config_cache()
    config_store.save_global_config_dict(
        tmp_path, {"new": {"post-commands": "scalar"}}
    )
    assert prefs.load_post_command_options(tmp_path) == []


def test_load_and_save_archive_timezone(tmp_path: Path) -> None:
    assert prefs.load_archive_timezone_name(tmp_path) == DEFAULT_ARCHIVE_TZ_NAME
    prefs.save_archive_timezone_name(tmp_path, "Europe/Oslo")
    assert prefs.load_archive_timezone_name(tmp_path) == "Europe/Oslo"
    # blank reverts to default
    prefs.save_archive_timezone_name(tmp_path, "  ")
    assert prefs.load_archive_timezone_name(tmp_path) == DEFAULT_ARCHIVE_TZ_NAME


def test_load_archive_timezone_handles_invalid_shape(tmp_path: Path) -> None:
    config_store.save_global_config_dict(tmp_path, {"archive": "scalar"})
    assert prefs.load_archive_timezone_name(tmp_path) == DEFAULT_ARCHIVE_TZ_NAME


def test_load_wip_symbol_map_defaults_when_missing(tmp_path: Path) -> None:
    assert prefs.load_wip_symbol_map(tmp_path) == dict(WIP_OPEN_SYMBOL_MAP)


def test_load_wip_symbol_map_supports_int_and_list_entries(tmp_path: Path) -> None:
    config_store.save_global_config_dict(
        tmp_path,
        {
            "wip": {
                "hotkeys": {
                    "1": "★",
                    2: ["♠", "♣"],
                    "3": None,  # skipped
                }
            }
        },
    )
    out = prefs.load_wip_symbol_map(tmp_path)
    assert out["★"] == 1
    assert out["♠"] == 2
    assert out["♣"] == 2


def test_load_wip_symbol_map_returns_defaults_on_invalid_shape(tmp_path: Path) -> None:
    config_store.save_global_config_dict(tmp_path, {"wip": "scalar"})
    assert prefs.load_wip_symbol_map(tmp_path) == dict(WIP_OPEN_SYMBOL_MAP)

    config_store.clear_global_config_cache()
    config_store.save_global_config_dict(tmp_path, {"wip": {"hotkeys": "scalar"}})
    assert prefs.load_wip_symbol_map(tmp_path) == dict(WIP_OPEN_SYMBOL_MAP)


def test_load_and_save_new_project_defaults(tmp_path: Path) -> None:
    initial = prefs.load_new_project_defaults(tmp_path)
    assert initial.keys() == set(NEW_PROJECT_DEFAULTS.keys())

    prefs.save_new_project_defaults(
        tmp_path,
        {
            "name_options": ["b", "a", "  "],
            "template": "  ",
            "post_commands": ["echo", "echo"],
            "tags": ["alpha", "beta"],
            "after_create": "  ",
        },
    )
    loaded = prefs.load_new_project_defaults(tmp_path)
    assert loaded["name_options"] == ["a", "b"]
    assert loaded["template"] is None
    assert loaded["post_commands"] == ["echo"]
    assert loaded["tags"] == ["alpha", "beta"]
    assert loaded["after_create"] == "open"


def test_load_new_project_defaults_returns_defaults_for_invalid_shape(
    tmp_path: Path,
) -> None:
    config_store.save_global_config_dict(tmp_path, {"new_project": "scalar"})
    assert prefs.load_new_project_defaults(tmp_path).keys() == set(
        NEW_PROJECT_DEFAULTS.keys()
    )


def test_nested_discovery_toggle_persists(tmp_path: Path) -> None:
    assert prefs.nested_discovery_enabled(tmp_path) is False
    prefs.set_nested_discovery_enabled(tmp_path, True)
    assert prefs.nested_discovery_enabled(tmp_path) is True
    prefs.set_nested_discovery_enabled(tmp_path, False)
    assert prefs.nested_discovery_enabled(tmp_path) is False


def test_save_and_load_filter_query_roundtrip(tmp_path: Path) -> None:
    prefs.save_filter_query(tmp_path, "#x", name="x")
    named, saved = prefs.load_saved_filter_queries(tmp_path)
    assert named == {"x": "#x"}
    assert saved == ["#x"]
    assert NAMED_FILTERS == {"x": "#x"}


def test_delete_named_filter_persists_only_on_removal(tmp_path: Path) -> None:
    prefs.save_filter_query(tmp_path, "#x", name="x")
    assert prefs.delete_named_filter(tmp_path, "unknown") is False
    assert prefs.delete_named_filter(tmp_path, "x") is True
    named, _saved = prefs.load_saved_filter_queries(tmp_path)
    assert "x" not in named


def test_resolve_filter_expression_handles_blank(tmp_path: Path) -> None:
    expr, err = prefs.resolve_filter_expression(tmp_path, "  ")
    assert (expr, err) == ("", None)


def test_resolve_filter_expression_expands_named(tmp_path: Path) -> None:
    prefs.save_filter_query(tmp_path, "#core", name="core")
    expr, err = prefs.resolve_filter_expression(tmp_path, "@core")
    assert err is None
    assert "#core" in expr


def test_resolve_filter_expression_unknown_name_returns_error(tmp_path: Path) -> None:
    expr, err = prefs.resolve_filter_expression(tmp_path, "@ghost")
    assert expr == "@ghost"
    assert err is not None
    assert "not found" in err


def test_resolve_named_filters_for_display_uses_global_map(tmp_path: Path) -> None:
    NAMED_FILTERS["core"] = "#alpha"
    out = prefs.resolve_named_filters_for_display("@core")
    assert "#alpha" in out


def test_load_table_columns_config_returns_view_lists(tmp_path: Path) -> None:
    out = prefs.load_table_columns_config(tmp_path)
    assert isinstance(out, dict)
    assert {"active", "archive"} <= set(out.keys())
    for view, cols in out.items():
        for col in cols:
            assert "id" in col
            assert "enabled" in col
            assert "width" in col


def test_save_and_load_table_columns_roundtrip(tmp_path: Path) -> None:
    initial = prefs.load_table_columns_config(tmp_path)
    altered = {
        view: [{"id": c["id"], "enabled": False, "width": 7} for c in cols]
        for view, cols in initial.items()
    }
    prefs.save_table_columns_config(tmp_path, altered)
    loaded = prefs.load_table_columns_config(tmp_path)
    for view, cols in loaded.items():
        for c in cols:
            assert c["width"] >= 1


def test_save_table_columns_skips_unknown_and_blank(tmp_path: Path) -> None:
    bad_payload = {
        "all": [{"id": "  ", "enabled": True}, "not-a-dict"],
        "active": [],
        "archive": [],
    }
    prefs.save_table_columns_config(tmp_path, bad_payload)
    out = prefs.load_table_columns_config(tmp_path)
    assert all(isinstance(c, dict) for cols in out.values() for c in cols)


def test_table_behavior_roundtrip(tmp_path: Path) -> None:
    initial = prefs.load_table_behavior_config(tmp_path)
    prefs.save_table_behavior_config(
        tmp_path,
        {
            "pin_wip_top": True,
            "side_width_pct": "99",
            "preview_entries_limit": "0",
        },
    )
    out = prefs.load_table_behavior_config(tmp_path)
    assert isinstance(out["side_width_pct"], int)
    assert isinstance(out["preview_entries_limit"], int)
    assert out["pin_wip_top"] is True
    # invalid inputs still resolve to a value
    assert initial.keys() == out.keys()


def test_load_table_behavior_handles_invalid_shape(tmp_path: Path) -> None:
    config_store.save_global_config_dict(
        tmp_path, {"table": {"behavior": "scalar"}}
    )
    out = prefs.load_table_behavior_config(tmp_path)
    assert "pin_wip_top" in out


def test_load_table_date_column_styles_uses_default_when_missing(tmp_path: Path) -> None:
    out = prefs.load_table_date_column_styles(tmp_path)
    assert {"all", "active", "archive"} <= set(out.keys())


def test_load_table_date_column_styles_parses_numeric_stops(tmp_path: Path) -> None:
    config_store.save_global_config_dict(
        tmp_path,
        {
            "table": {
                "columns_style": {
                    "date": {
                        "all": {
                            "created": {
                                "0": "#FFFFFF",
                                "10": "#000000",
                            }
                        }
                    }
                }
            }
        },
    )
    out = prefs.load_table_date_column_styles(tmp_path)
    stops = out["all"]["created"]["stops"]
    assert stops[0]["days"] == 0.0
    assert stops[0]["color"] == "#FFFFFF"
    assert stops[-1]["color"] == "#000000"


def test_load_table_date_column_styles_falls_back_to_from_to_pair(tmp_path: Path) -> None:
    config_store.save_global_config_dict(
        tmp_path,
        {
            "table": {
                "date_columns": {
                    "active": {
                        "created": {
                            "from_color": "#aaaaaa",
                            "to_color": "#000000",
                            "range_days": "10",
                        }
                    }
                }
            }
        },
    )
    out = prefs.load_table_date_column_styles(tmp_path)
    stops = out["active"]["created"]["stops"]
    assert {stop["color"] for stop in stops} == {"#aaaaaa", "#000000"}


def test_save_and_load_open_mode_config(tmp_path: Path) -> None:
    prefs.save_open_mode_config(tmp_path, {"profile": "cd-current"})
    out = prefs.load_open_mode_config(tmp_path)
    assert isinstance(out, dict)
    assert "profile" in out


def test_load_suffixes_falls_back_to_defaults(tmp_path: Path) -> None:
    out = prefs.load_suffixes(tmp_path)
    assert "tmp" in out and "fork" in out


def test_table_catalog_for_view_filters_by_view() -> None:
    out = prefs._table_catalog_for_view("active")
    assert all("active" in (col.get("views") or []) for col in out)


def test_normalize_side_width_pct_snaps_to_preset() -> None:
    out = prefs._normalize_side_width_pct(33)
    assert isinstance(out, int)
    assert out > 0


def test_normalize_preview_entries_limit_clamps() -> None:
    very_small = prefs._normalize_preview_entries_limit(-9999)
    very_large = prefs._normalize_preview_entries_limit(999_999)
    assert very_small >= 1
    assert very_large <= 10_000
    # invalid value resolves to default
    out = prefs._normalize_preview_entries_limit("not-a-number")
    assert isinstance(out, int)


def test_save_ui_state_roundtrip(tmp_path: Path) -> None:
    prefs.save_ui_state(tmp_path, {"view": "archive", "sort": "name"})
    out = prefs.load_ui_state(tmp_path)
    assert out["view"] == "archive"
    assert out["sort"] == "name"


def test_load_cache_profile_table_returns_three_scopes(tmp_path: Path) -> None:
    out = prefs.load_cache_profile_table(tmp_path)
    assert {"all", "active", "archive"} <= set(out.keys())


def test_load_raycast_config_defaults_and_validates_sort(tmp_path: Path) -> None:
    assert prefs.load_raycast_config(tmp_path) == {
        "sort": "name",
        "secondary_info": [],
        "secondary_separator": " • ",
    }

    config_store.save_global_config_dict(tmp_path, {"raycast": {"sort": "opened"}})
    assert prefs.load_raycast_config(tmp_path)["sort"] == "opened"

    config_store.save_global_config_dict(tmp_path, {"raycast": {"sort": "bad"}})
    assert prefs.load_raycast_config(tmp_path)["sort"] == "name"


def test_load_raycast_config_supports_secondary_info(tmp_path: Path) -> None:
    config_store.save_global_config_dict(
        tmp_path,
        {
            "raycast": {
                "secondary_info": ["{{ opened_ago }}", " {{ tags_space }} "],
                "secondary_separator": " | ",
            }
        },
    )

    out = prefs.load_raycast_config(tmp_path)

    assert out["secondary_info"] == ["{{ opened_ago }}", "{{ tags_space }}"]
    assert out["secondary_separator"] == " | "
