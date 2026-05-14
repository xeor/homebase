from __future__ import annotations

import pytest

from homebase.config import workspace as workspace_settings
from homebase.core.constants import BUILTIN_ACTIONS


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


def test_load_actions_parses_custom_shell_action() -> None:
    out = workspace_settings.load_actions(
        {
            "actions": {
                "open_item_in_codium": {
                    "kind": "shell",
                    "scope": "target",
                    "multi": "joined",
                    "command": "codium {{ paths_q }}",
                }
            }
        },
        builtins=BUILTIN_ACTIONS,
    )
    assert out["open_item_in_codium"].kind == "shell"
    assert out["open_item_in_codium"].source == "config"


def test_load_actions_rejects_builtin_non_override_fields() -> None:
    with pytest.raises(ValueError, match="only `label` and `confirm`"):
        workspace_settings.load_actions(
            {"actions": {"archive": {"kind": "shell", "command": "echo x"}}},
            builtins=BUILTIN_ACTIONS,
        )


def test_load_hotbar_rejects_workspace_scope_action() -> None:
    actions = workspace_settings.load_actions(
        {
            "actions": {
                "open_base": {
                    "kind": "shell",
                    "scope": "workspace",
                    "command": "echo {{ base_dir_q }}",
                }
            },
            "hotbar": ["open_base"],
        },
        builtins=BUILTIN_ACTIONS,
    )
    with pytest.raises(ValueError, match="cannot be on the hotbar"):
        workspace_settings.load_hotbar(
            {"hotbar": ["open_base"]},
            actions=actions,
        )


def test_load_keys_rejects_unknown_action_id() -> None:
    actions = workspace_settings.load_actions({}, builtins=BUILTIN_ACTIONS)
    with pytest.raises(ValueError, match="action not found"):
        workspace_settings.load_keys({"keys": {"f5": "nope"}}, actions=actions)


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


def test_load_notes_config_supports_log_and_rename_blocks() -> None:
    out = workspace_settings.load_notes_config(
        {
            "notes": {
                "path_template": "{{ PROJECT_PATH }}/NOTES.md",
                "log": {
                    "section": {"title": "Journal", "level": 3},
                    "entry": {"timestamp_format": "%Y-%m-%d"},
                },
                "rename": {
                    "enabled": True,
                    "command": "obsidian-rename {{ OLD_NOTE_PATH_Q }} {{ NEW_NOTE_PATH_Q }}",
                },
            }
        },
        defaults={
            "path_template": "{{ PROJECT_PATH }}/NOTES.md",
            "open_command": "vi {{ NOTE_PATH_Q }}",
            "create_command": "touch {{ NOTE_PATH_Q }}",
            "log": {"section": {"title": "Log", "level": 2}, "entry": {"timestamp_format": "iso-seconds"}},
            "rename": {"enabled": True, "command": ""},
        },
    )
    assert out["log"]["section"]["title"] == "Journal"
    assert out["log"]["section"]["level"] == 3
    assert out["log"]["entry"]["timestamp_format"] == "%Y-%m-%d"
    assert out["rename"]["enabled"] is True
    assert out["rename"]["command"] == "obsidian-rename {{ OLD_NOTE_PATH_Q }} {{ NEW_NOTE_PATH_Q }}"
    assert "archive" not in out
    assert "restore" not in out


def test_nested_discovery_set_and_get_roundtrip() -> None:
    updated = workspace_settings.set_nested_discovery_enabled({}, enabled=True)
    assert workspace_settings.nested_discovery_enabled(updated) is True
