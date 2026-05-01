from __future__ import annotations

from homebase.config import workspace as workspace_settings


def test_load_suffixes_normalizes_and_deduplicates() -> None:
    out = workspace_settings.load_suffixes(
        {"suffixes": [".Tmp", "fork", "tmp", ""]},
        default_suffixes=["tmp", "fork"],
    )
    assert out == ["tmp", "fork"]


def test_load_file_view_exclude_patterns_merges_legacy() -> None:
    out = workspace_settings.load_file_view_exclude_patterns(
        {"files_view": {"exclude_patterns": [".git"], "exclude_dirs": ["node_modules", ".git"]}}
    )
    assert out == [".git", "node_modules"]


def test_load_custom_actions_filters_invalid_rows() -> None:
    out = workspace_settings.load_custom_actions(
        {
            "custom_actions": [
                {"command": "echo ok", "scope": "bad"},
                {"id": "x", "command": ""},
            ]
        }
    )
    assert out == [
        {
            "id": "custom_1",
            "label": "custom_1",
            "scope": "item",
            "command": "echo ok",
        }
    ]


def test_load_reconcile_config_applies_bounds() -> None:
    out = workspace_settings.load_reconcile_config(
        {
            "reconcile": {
                "active": {"interval_s": 0, "batch_size": 0},
                "archive": {"enabled": 1},
            }
        },
        defaults={
            "active": {"enabled": False, "interval_s": 10.0, "batch_size": 5},
            "archive": {"enabled": False, "interval_s": 10.0, "batch_size": 5},
        },
    )
    assert out["active"]["interval_s"] == 1.0
    assert out["active"]["batch_size"] == 1
    assert out["archive"]["enabled"] is True


def test_nested_discovery_set_and_get_roundtrip() -> None:
    updated = workspace_settings.set_nested_discovery_enabled({}, enabled=True)
    assert workspace_settings.nested_discovery_enabled(updated) is True
