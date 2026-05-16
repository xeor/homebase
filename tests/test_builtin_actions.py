from __future__ import annotations

from homebase.core.constants import BUILTIN_ACTIONS
from homebase.ui.app import _VIEW_CONFIG_DEFAULT


def test_builtin_actions_include_all_legacy_ids() -> None:
    expected_ids = {
        "open_selected",
        "readme_create",
        "readme_edit",
        "notes_create",
        "notes_open",
        "tags_set",
        "reconcile_selection_cache",
        "suffix_set",
        "archive",
        "restore",
        "pack",
        "unpack",
        "toggle_pack",
        "delete",
        "set_desc",
        "rename_item",
        "review_meta",
        "rename_meta_ext",
        "refresh_cache",
        "full_reconcile",
        "reconcile_all_cache",
        "edit_global_config",
        "reload_global_config",
        "hooks_refresh",
        "hooks_refresh_view",
    }
    assert expected_ids == set(BUILTIN_ACTIONS)


def test_builtin_actions_have_default_label_and_help_text() -> None:
    for action_id, meta in BUILTIN_ACTIONS.items():
        assert meta.id == action_id
        assert meta.default_label.strip()
        assert meta.help_text.strip()


def test_builtin_action_view_scope_matches_current_view_config() -> None:
    active_ids = {action_id for action_id, _label in _VIEW_CONFIG_DEFAULT["active"]["actions"]}
    archive_ids = {action_id for action_id, _label in _VIEW_CONFIG_DEFAULT["archive"]["actions"]}
    active_only_ids = {"suffix_set"}
    for action_id, meta in BUILTIN_ACTIONS.items():
        if action_id in active_only_ids:
            expected = ("active",)
        elif action_id in active_ids and action_id in archive_ids:
            expected = ("active", "archive")
        elif action_id in active_ids:
            expected = ("active",)
        elif action_id in archive_ids:
            expected = ("archive",)
        else:
            expected = ("active", "archive")
        assert meta.view_scope == expected
