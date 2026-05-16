from __future__ import annotations

import pytest

from homebase.config.hooks import (
    HookConfigError,
    load_hook_refresh_config,
    load_hook_specs,
)
from homebase.config.store import save_global_config_dict


def test_load_hook_specs_empty_config_has_all_slots(tmp_path) -> None:
    save_global_config_dict(tmp_path, {})
    specs = load_hook_specs(tmp_path)
    assert len(specs) == 8
    assert [spec.name for spec in specs[("post", "rename")]] == [
        "notes_rename",
        "tag_symlink_sync",
    ]
    assert [spec.name for spec in specs[("post", "tag_change")]] == ["tag_symlink_sync"]
    assert [spec.name for spec in specs[("post", "new_project")]] == ["tag_symlink_sync"]
    assert [spec.name for spec in specs[("post", "delete")]] == ["tag_symlink_sync"]
    assert specs[("pre", "rename")] == []
    assert specs[("pre", "tag_change")] == []
    assert specs[("pre", "new_project")] == []
    assert [spec.name for spec in specs[("pre", "delete")]] == ["confirm_delete"]
    assert specs[("pre", "delete")][0].enabled is False
    assert all(spec.enabled is False for spec in specs[("post", "rename")])
    assert all(spec.enabled is False for spec in specs[("post", "tag_change")])
    assert all(spec.enabled is False for spec in specs[("post", "new_project")])
    assert all(spec.enabled is False for spec in specs[("post", "delete")])


def test_load_hook_specs_parses_bundled_entry(tmp_path) -> None:
    save_global_config_dict(
        tmp_path,
        {
            "hooks_pre": {
                "rename": [
                    {
                        "name": "validate_branch_name",
                        "source": "bundled",
                        "enabled": True,
                        "views": ["active"],
                        "config": {"x": 1},
                        "slow_warn_s": 12,
                    }
                ]
            }
        },
    )
    specs = load_hook_specs(tmp_path)
    spec = specs[("pre", "rename")][0]
    assert spec.name == "validate_branch_name"
    assert spec.source == "bundled"
    assert spec.enabled is True
    assert spec.views == ("active",)
    assert spec.config == {"x": 1}
    assert spec.slow_warn_s == 12.0


def test_load_hook_specs_missing_name_raises(tmp_path) -> None:
    save_global_config_dict(tmp_path, {"hooks_post": {"rename": [{"source": "custom"}]}})
    with pytest.raises(HookConfigError, match="missing `name`"):
        load_hook_specs(tmp_path)


def test_load_hook_specs_unknown_event_raises(tmp_path) -> None:
    save_global_config_dict(tmp_path, {"hooks_post": {"rename-item": []}})
    with pytest.raises(HookConfigError, match="unknown hook event"):
        load_hook_specs(tmp_path)


def test_load_hook_specs_bad_views_entry_raises(tmp_path) -> None:
    save_global_config_dict(
        tmp_path,
        {"hooks_post": {"rename": [{"name": "x", "views": ["active", "bogus"]}]}},
    )
    with pytest.raises(HookConfigError, match="unknown view"):
        load_hook_specs(tmp_path)


def test_load_hook_specs_non_mapping_config_raises(tmp_path) -> None:
    save_global_config_dict(
        tmp_path,
        {"hooks_post": {"rename": [{"name": "x", "config": ["bad"]}]}},
    )
    with pytest.raises(HookConfigError, match="`config` must be a mapping"):
        load_hook_specs(tmp_path)


def test_load_hook_specs_invalid_slow_warn_raises(tmp_path) -> None:
    save_global_config_dict(
        tmp_path,
        {"hooks_post": {"rename": [{"name": "x", "slow_warn_s": "nope"}]}},
    )
    with pytest.raises(HookConfigError, match="invalid `slow_warn_s`"):
        load_hook_specs(tmp_path)


def test_load_hook_specs_default_slow_warn(tmp_path) -> None:
    save_global_config_dict(tmp_path, {"hooks_post": {"rename": [{"name": "x"}]}})
    specs = load_hook_specs(tmp_path)
    assert specs[("post", "rename")][0].slow_warn_s == 30.0


def test_load_hook_specs_refresh_defaults(tmp_path) -> None:
    save_global_config_dict(tmp_path, {"hooks_post": {"rename": [{"name": "x"}]}})
    specs = load_hook_specs(tmp_path)
    spec = specs[("post", "rename")][0]
    assert spec.refresh_enabled is False
    assert spec.refresh_min_interval_s == 60.0


def test_load_hook_specs_refresh_fields(tmp_path) -> None:
    save_global_config_dict(
        tmp_path,
        {
            "hooks_post": {
                "tag_change": [
                    {
                        "name": "tag_files_sync",
                        "source": "bundled",
                        "refresh_enabled": True,
                        "refresh_min_interval_s": 120,
                    }
                ]
            }
        },
    )
    spec = load_hook_specs(tmp_path)[("post", "tag_change")][0]
    assert spec.refresh_enabled is True
    assert spec.refresh_min_interval_s == 120.0


def test_load_hook_specs_invalid_refresh_min_raises(tmp_path) -> None:
    save_global_config_dict(
        tmp_path,
        {"hooks_post": {"rename": [{"name": "x", "refresh_min_interval_s": "bad"}]}},
    )
    with pytest.raises(HookConfigError, match="invalid `refresh_min_interval_s`"):
        load_hook_specs(tmp_path)


def test_load_hook_refresh_config_defaults(tmp_path) -> None:
    save_global_config_dict(tmp_path, {})
    cfg = load_hook_refresh_config(tmp_path)
    assert cfg.enabled is False
    assert cfg.worker.batch_size == 4
    assert cfg.worker.jitter_pct == 15.0
    assert cfg.worker.skip_when_busy is True


def test_load_hook_refresh_config_parses_section(tmp_path) -> None:
    save_global_config_dict(
        tmp_path,
        {
            "hooks_refresh": {
                "enabled": True,
                "worker": {
                    "batch_size": 8,
                    "jitter_pct": 30,
                    "skip_when_busy": False,
                },
            }
        },
    )
    cfg = load_hook_refresh_config(tmp_path)
    assert cfg.enabled is True
    assert cfg.worker.batch_size == 8
    assert cfg.worker.jitter_pct == 30.0
    assert cfg.worker.skip_when_busy is False


def test_load_hook_refresh_config_non_mapping_raises(tmp_path) -> None:
    save_global_config_dict(tmp_path, {"hooks_refresh": ["bad"]})
    with pytest.raises(HookConfigError, match="must be a mapping"):
        load_hook_refresh_config(tmp_path)
