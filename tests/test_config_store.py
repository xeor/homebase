from __future__ import annotations

import re
from pathlib import Path

from homebase.config import store as config_store


def test_global_config_roundtrip(tmp_path: Path) -> None:
    data = {"filters": {"saved": ["#api"]}}
    config_store.save_global_config_dict(tmp_path, data)
    loaded = config_store.load_global_config_dict(tmp_path)
    assert loaded == data


def test_save_filter_query_to_data_updates_named_and_saved() -> None:
    data, named, saved = config_store.save_filter_query_to_data(
        {"filters": {"saved": ["#old"], "named": {"old": "#old"}}},
        "#new",
        "new",
    )
    assert saved[0] == "#new"
    assert named["new"] == "#new"
    assert isinstance(data, dict)


def test_resolve_named_filters_for_display_expands_nested() -> None:
    token_re = re.compile(r"\([^()]*\)|[^\s()]+")
    out = config_store.resolve_named_filters_for_display(
        "@a",
        {"a": "#one OR @b", "b": "#two"},
        token_re,
    )
    assert "#one" in out
    assert "#two" in out


def test_load_ui_state_from_data_normalizes_values() -> None:
    out = config_store.load_ui_state_from_data(
        {"state": {"view": "bad", "sort": "bad", "cursor_row": -2}},
        state_key_side_main="side_main",
        state_key_side_selected="side_selected",
        state_key_side_info="side_info",
        state_key_side_settings="side_settings",
        side_tab_selected_default="selected",
        side_tab_overview_default="overview",
        side_tab_events_default="events",
        side_tab_table_default="table",
        side_top_tabs=[("selected", "Selected")],
        side_child_tabs={
            "selected": [("overview", "Overview")],
            "info": [("events", "Events")],
            "settings": [("table", "Table")],
        },
        sort_mode_ids={"last", "name"},
    )
    assert out["view"] == "active"
    assert out["sort"] == "last"
    assert out["cursor_row"] == 0
