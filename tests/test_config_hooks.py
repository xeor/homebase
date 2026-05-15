from __future__ import annotations

import pytest

from homebase.config.hooks import HookConfigError, load_hook_specs
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
    assert all(specs[("pre", event)] == [] for event in ("rename", "tag_change", "new_project", "delete"))


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
