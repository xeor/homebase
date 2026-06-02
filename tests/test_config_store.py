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


def test_load_global_config_dict_handles_invalid_yaml(tmp_path: Path) -> None:
    config_store.clear_global_config_cache()
    (tmp_path / ".homebase").mkdir()
    (tmp_path / ".homebase" / "config.yaml").write_text(":\n  bad: [")
    assert config_store.load_global_config_dict(tmp_path) == {}


def test_load_global_config_dict_returns_empty_for_non_mapping(tmp_path: Path) -> None:
    config_store.clear_global_config_cache()
    (tmp_path / ".homebase").mkdir()
    (tmp_path / ".homebase" / "config.yaml").write_text("[1,2,3]\n")
    assert config_store.load_global_config_dict(tmp_path) == {}


def test_load_global_config_dict_caches_result(tmp_path: Path, monkeypatch) -> None:
    config_store.clear_global_config_cache()
    data = {"key": "val"}
    config_store.save_global_config_dict(tmp_path, data)

    parses = {"count": 0}
    real = config_store.yaml.safe_load

    def counter(text: str) -> object:
        parses["count"] += 1
        return real(text)

    monkeypatch.setattr(config_store.yaml, "safe_load", counter)

    config_store.clear_global_config_cache()
    assert config_store.load_global_config_dict(tmp_path) == data
    assert config_store.load_global_config_dict(tmp_path) == data
    assert parses["count"] == 1


def test_clear_global_config_cache_specific_base(tmp_path: Path) -> None:
    config_store.clear_global_config_cache()
    config_store.save_global_config_dict(tmp_path, {"x": 1})
    config_store.load_global_config_dict(tmp_path)
    config_store.clear_global_config_cache(tmp_path)
    assert config_store._GLOBAL_CONFIG_DATA is None
    other = tmp_path / "other"
    other.mkdir()
    # different base should not be cleared
    config_store.save_global_config_dict(other, {"y": 2})
    config_store.load_global_config_dict(other)
    config_store.clear_global_config_cache(tmp_path)  # different base, no-op
    assert config_store._GLOBAL_CONFIG_DATA == {"y": 2}


def test_save_filter_query_to_data_no_op_for_blank() -> None:
    out, named, saved = config_store.save_filter_query_to_data(
        {"filters": {"saved": ["#a"]}}, "  "
    )
    assert saved == ["#a"]
    assert "filters" in out
    assert named == {}


def test_save_filter_query_to_data_moves_existing_to_front_and_caps_to_100() -> None:
    initial = {"filters": {"saved": [f"#{i}" for i in range(120)]}}
    out, _named, saved = config_store.save_filter_query_to_data(initial, "#50")
    assert saved[0] == "#50"
    assert len(saved) == 100


def test_save_filter_query_to_data_recovers_from_non_dict_filters() -> None:
    out, named, saved = config_store.save_filter_query_to_data(
        {"filters": "not-a-dict"}, "#a"
    )
    assert saved == ["#a"]
    assert named == {}


def test_delete_named_filter_from_data_removes_named_and_returns_true() -> None:
    initial = {"filters": {"named": {"foo": "#foo"}}}
    _out, ok, named = config_store.delete_named_filter_from_data(initial, "foo")
    assert ok is True
    assert "foo" not in named


def test_delete_named_filter_from_data_blank_name_returns_false() -> None:
    out, ok, named = config_store.delete_named_filter_from_data({"filters": {}}, "  ")
    assert ok is False
    assert named == {}
    assert out == {"filters": {}}


def test_delete_named_filter_from_data_unknown_name_returns_false() -> None:
    initial = {"filters": {"named": {"foo": "#foo"}}}
    _out, ok, named = config_store.delete_named_filter_from_data(initial, "bar")
    assert ok is False
    assert named == {"foo": "#foo"}


def test_resolve_named_filters_for_display_blank_returns_dash() -> None:
    token_re = re.compile(r"[^\s()]+")
    assert (
        config_store.resolve_named_filters_for_display("  ", {}, token_re)
        == "-"
    )


def test_resolve_named_filters_for_display_caps_recursion() -> None:
    token_re = re.compile(r"[^\s()]+")
    named = {"a": "@b", "b": "@a"}
    out = config_store.resolve_named_filters_for_display("@a", named, token_re)
    assert "@a" in out or "@b" in out


def test_save_ui_state_to_data_normalises_negatives() -> None:
    out = config_store.save_ui_state_to_data(
        {},
        {"cursor_row": -5, "scroll_y": "nope", "view": "active"},
        state_key_side_main="side_main",
        state_key_side_selected="side_selected",
        state_key_side_info="side_info",
        state_key_side_settings="side_settings",
        side_tab_selected_default="selected",
        side_tab_overview_default="overview",
        side_tab_events_default="events",
        side_tab_table_default="table",
    )
    assert out["state"]["cursor_row"] == 0
    assert out["state"]["scroll_y"] == 0


def test_load_ui_state_propagates_selected_path_into_view_specific(tmp_path: Path) -> None:
    out = config_store.load_ui_state_from_data(
        {
            "state": {
                "view": "archive",
                "selected_path": "/base/some",
            }
        },
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
    assert out["selected_path_archive"] == "/base/some"


def test_load_saved_filter_queries_from_data_caps_at_100_and_strips() -> None:
    raw = {
        "filters": {
            "saved": ["  #x  ", ""] + [f"#{i}" for i in range(200)],
            "named": {"a": "  #foo  ", " ": "skip-blank", "good": ""},
        }
    }
    named, saved = config_store.load_saved_filter_queries_from_data(raw)
    assert "#x" in saved
    assert len(saved) == 100
    assert named == {"a": "#foo"}


def test_load_saved_filter_queries_from_data_invalid_filters_section() -> None:
    named, saved = config_store.load_saved_filter_queries_from_data(
        {"filters": "not-a-dict"}
    )
    assert (named, saved) == ({}, [])


def test_load_saved_filter_queries_from_data_root_not_dict() -> None:
    assert config_store.load_saved_filter_queries_from_data("not-a-dict") == ({}, [])


def test_load_saved_filter_queries_from_data_saved_not_list() -> None:
    named, saved = config_store.load_saved_filter_queries_from_data(
        {"filters": {"saved": "scalar"}}
    )
    assert saved == []
    assert named == {}
