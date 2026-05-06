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
    assert out == []


def test_load_custom_actions_accepts_action_without_command() -> None:
    out = workspace_settings.load_custom_actions(
        {
            "custom_actions": [
                {"id": "x", "scope": "item", "action": "custom:open_item"},
            ]
        }
    )
    assert out == []


def test_load_custom_actions_accepts_target_scope() -> None:
    out = workspace_settings.load_custom_actions(
        {
            "custom_actions": [
                {"id": "x", "scope": "target", "action": "custom:open_item"},
            ]
        }
    )
    assert out == [
        {
            "id": "x",
            "label": "x",
            "scope": "target",
            "action": "custom:open_item",
        }
    ]


def test_load_custom_actions_parses_loop_on_multi() -> None:
    out = workspace_settings.load_custom_actions(
        {
            "custom_actions": [
                {
                    "id": "x",
                    "scope": "target",
                    "command": "open -a DaisyDisk {{ full_path }}",
                    "loop_on_multi": True,
                },
            ]
        }
    )
    assert out == [
        {
            "id": "x",
            "label": "x",
            "scope": "target",
            "command": "open -a DaisyDisk {{ full_path }}",
            "loop_on_multi": "true",
        }
    ]


def test_load_custom_actions_accepts_list_action_form() -> None:
    out = workspace_settings.load_custom_actions(
        {
            "custom_actions": [
                {
                    "id": "drawio",
                    "scope": "target",
                    "list_command": "find {{ full_path }} -name '*.drawio'",
                    "run_command": "drawio {{ selection_q }}",
                }
            ]
        }
    )
    assert out == [
        {
            "id": "drawio",
            "label": "drawio",
            "scope": "target",
            "list_command": "find {{ full_path }} -name '*.drawio'",
            "run_command": "drawio {{ selection_q }}",
        }
    ]


def test_load_custom_hotkeys_filters_invalid_rows() -> None:
    out = workspace_settings.load_custom_hotkeys(
        {
            "custom_hotkeys": [
                {"id": "one", "hotkey": "F5", "target": "custom:open_item"},
                {"id": "two", "hotkey": "", "target": "custom:open_item"},
                {"id": "three", "hotkey": "f6", "target": ""},
            ]
        }
    )
    assert out == [{"id": "one", "hotkey": "f5", "target": "custom:open_item"}]


def test_load_create_templates_filters_and_normalizes() -> None:
    out = workspace_settings.load_create_templates(
        {
            "create_templates": [
                {
                    "key": "tmp",
                    "options": ["prefix-datetime", "changedir", ""],
                    "template": "py",
                    "tags": ["scratch", ""],
                },
                {"key": "tmp"},
                {"options": ["x"]},
            ]
        }
    )
    assert out == [
        {
            "key": "tmp",
            "name": "tmp",
            "options": ["prefix-datetime", "changedir"],
            "template": "py",
            "tags": ["scratch"],
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


def test_load_reconcile_config_supports_cache_profile() -> None:
    out = workspace_settings.load_reconcile_config(
        {
            "cache_profile": {
                "all": {
                    "pri-2": {
                        "update_interval_s": 12,
                        "update_batch_size": 9,
                        "update_priority": 40,
                        "cache_mode": "ttl",
                        "cache_ttl_s": 60,
                        "use_usage_score": False,
                        "usage_weight": 0.5,
                        "stale_boost": False,
                        "max_parallelism": 3,
                    }
                }
            },
            "reconcile": {
                "active": {
                    "cache_profile": "pri-2",
                }
            },
        },
        defaults={
            "active": {"enabled": True, "interval_s": 5.0, "batch_size": 1},
            "archive": {"enabled": True, "interval_s": 12.0, "batch_size": 1},
        },
    )
    assert out["active"]["interval_s"] == 12.0
    assert out["active"]["batch_size"] == 9
    assert out["active"]["parallelism"] == 3
    assert out["active"]["use_usage_score"] is False
    assert out["active"]["usage_weight"] == 0.5
    assert out["active"]["stale_boost"] is False


def test_load_reconcile_config_supports_explicit_extended_fields() -> None:
    out = workspace_settings.load_reconcile_config(
        {
            "reconcile": {
                "active": {
                    "parallelism": 5,
                    "use_usage_score": 0,
                    "usage_weight": 1.75,
                    "stale_boost": 0,
                    "stale_interval_s": 0.2,
                    "stale_parallelism": 7,
                    "stale_batch_size": 6,
                }
            }
        },
        defaults={
            "active": {"enabled": True, "interval_s": 5.0, "batch_size": 1},
            "archive": {"enabled": True, "interval_s": 12.0, "batch_size": 1},
        },
    )
    assert out["active"]["parallelism"] == 5
    assert out["active"]["use_usage_score"] is False
    assert out["active"]["usage_weight"] == 1.75
    assert out["active"]["stale_boost"] is False
    assert out["active"]["stale_interval_s"] == 0.2
    assert out["active"]["stale_parallelism"] == 7
    assert out["active"]["stale_batch_size"] == 6


def test_load_reconcile_config_resolves_default_cache_profile() -> None:
    out = workspace_settings.load_reconcile_config(
        {},
        defaults={
            "active": {"enabled": True, "cache_profile": "reconcile-active"},
            "archive": {"enabled": True, "cache_profile": "reconcile-archive"},
        },
        default_cache_profiles={
            "all": {
                "reconcile-active": {
                    "update_interval_s": 5,
                    "update_batch_size": 2,
                    "update_priority": 30,
                    "cache_mode": "ttl",
                    "cache_ttl_s": 30,
                    "max_parallelism": 3,
                },
                "reconcile-archive": {
                    "update_interval_s": 12,
                    "update_batch_size": 1,
                    "update_priority": 60,
                    "cache_mode": "ttl",
                    "cache_ttl_s": 60,
                    "max_parallelism": 1,
                },
            }
        },
    )
    assert out["active"]["interval_s"] == 5.0
    assert out["active"]["batch_size"] == 2
    assert out["active"]["parallelism"] == 3


def test_load_reconcile_config_default_profile_overrides_apply() -> None:
    out = workspace_settings.load_reconcile_config(
        {},
        defaults={
            "active": {
                "enabled": True,
                "cache_profile": "reconcile-active",
                "cache_profile_overrides": {"active": {"update_batch_size": 7}},
            },
            "archive": {"enabled": True},
        },
        default_cache_profiles={
            "all": {
                "reconcile-active": {
                    "update_interval_s": 5,
                    "update_batch_size": 2,
                    "update_priority": 30,
                    "cache_mode": "ttl",
                    "cache_ttl_s": 30,
                    "max_parallelism": 1,
                }
            }
        },
    )
    assert out["active"]["batch_size"] == 7


def test_nested_discovery_set_and_get_roundtrip() -> None:
    updated = workspace_settings.set_nested_discovery_enabled({}, enabled=True)
    assert workspace_settings.nested_discovery_enabled(updated) is True
