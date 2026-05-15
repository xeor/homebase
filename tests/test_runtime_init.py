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
        load_actions=lambda _p: {},
        load_hotbar=lambda _p, _actions: [],
        load_keys=lambda _p, _actions: {},
        load_open_mode_config=lambda _p: {},
        load_notes_config=lambda _p: {},
        load_reconcile_config=lambda _p: {},
        load_cache_profile_table=lambda _p: {},
        load_hook_specs=lambda _p: {},
        load_archive_timezone_name=lambda _p: "UTC",
    )
    assert cfg.property_defs == ["a"]
    assert cfg.named_filters == {"n": "#x"}


def test_validate_custom_hotkeys_accepts_unique_non_reserved() -> None:
    err = runtime_init.validate_custom_hotkeys(
        [
            {"id": "vscode", "hotkey": "f5", "target": "custom:vscode"},
            {"id": "term", "hotkey": "ctrl+f5", "target": "custom:term"},
        ],
        reserved_hotkeys={"ctrl+a", "tab"},
    )
    assert err is None


def test_validate_custom_hotkeys_rejects_duplicates() -> None:
    err = runtime_init.validate_custom_hotkeys(
        [
            {"id": "one", "hotkey": "f5", "target": "archive"},
            {"id": "two", "hotkey": "F5", "target": "restore"},
        ],
        reserved_hotkeys=set(),
    )
    assert err is not None
    assert "f5" in err
    assert "one" in err
    assert "two" in err


def test_validate_custom_hotkeys_rejects_reserved() -> None:
    err = runtime_init.validate_custom_hotkeys(
        [{"id": "bad", "hotkey": "ctrl+a", "target": "archive"}],
        reserved_hotkeys={"ctrl+a", "tab"},
    )
    assert err is not None
    assert "ctrl+a" in err
    assert "bad" in err
