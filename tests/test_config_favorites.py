from __future__ import annotations

import pytest

from homebase.config.prefs import load_actions, load_favorites, save_favorites
from homebase.core.constants import BUILTIN_ACTIONS


def test_load_favorites_supports_action_entries(tmp_path) -> None:
    save_favorites(
        tmp_path,
        [
            {"target": "archive", "favorite": True},
        ],
    )
    actions = load_actions(tmp_path, builtins=BUILTIN_ACTIONS)
    loaded = load_favorites(tmp_path, actions=actions)
    assert [item["target"] for item in loaded] == ["archive"]
    assert loaded[0]["favorite"] is True


def test_load_favorites_supports_hotkey_only_entry(tmp_path) -> None:
    save_favorites(
        tmp_path,
        [
            {"target": "archive", "hotkey": "f5"},
        ],
    )
    actions = load_actions(tmp_path, builtins=BUILTIN_ACTIONS)
    loaded = load_favorites(tmp_path, actions=actions)
    assert loaded == [
        {"id": "fav_1", "target": "archive", "hotkey": "f5"},
    ]


def test_save_favorites_persists_optional_label(tmp_path) -> None:
    save_favorites(
        tmp_path,
        [
            {"target": "archive", "favorite": True, "label": "Archive now"},
        ],
    )
    actions = load_actions(tmp_path, builtins=BUILTIN_ACTIONS)
    loaded = load_favorites(tmp_path, actions=actions)
    assert loaded[0]["label"] == "Archive now"


def test_favorites_style_rules_roundtrip(tmp_path) -> None:
    save_favorites(
        tmp_path,
        [
            {
                "target": "notes_create",
                "favorite": True,
                "label": "Notes",
                "style": [
                    {"bg_color": "#112233", "fg_color": "#eeeeee", "bold": True, "when": "!n"},
                    {"bg_color": "#334455", "underline": True, "italic": True, "when": "#wip"},
                ],
            },
        ],
    )
    actions = load_actions(tmp_path, builtins=BUILTIN_ACTIONS)
    loaded = load_favorites(tmp_path, actions=actions)
    assert len(loaded) == 1
    assert loaded[0]["target"] == "notes_create"
    assert list(loaded[0]["style"]) == [
        {"bg_color": "#112233", "fg_color": "#eeeeee", "bold": "1", "when": "!n"},
        {"bg_color": "#334455", "underline": "1", "italic": "1", "when": "#wip"},
    ]


def test_favorites_style_requires_valid_hex_color(tmp_path) -> None:
    save_favorites(
        tmp_path,
        [
            {
                "target": "notes_create",
                "favorite": True,
                "style": [{"bg_color": "blue", "when": "#wip"}],
            },
        ],
    )
    actions = load_actions(tmp_path, builtins=BUILTIN_ACTIONS)
    with pytest.raises(ValueError, match="bg_color must be #RRGGBB"):
        load_favorites(tmp_path, actions=actions)


def test_load_favorites_ignores_legacy_hotbar_and_keys(tmp_path) -> None:
    """Legacy `hotbar:` / `keys:` YAML keys must be silently ignored."""
    from homebase.config.store import (
        load_global_config_dict,
        save_global_config_dict,
    )

    data = load_global_config_dict(tmp_path)
    data["hotbar"] = [{"action": "archive"}]
    data["keys"] = {"f5": "archive"}
    save_global_config_dict(tmp_path, data)
    actions = load_actions(tmp_path, builtins=BUILTIN_ACTIONS)
    assert load_favorites(tmp_path, actions=actions) == []


def test_load_favorites_rejects_reserved_hotkey(tmp_path) -> None:
    save_favorites(
        tmp_path,
        [
            {"target": "archive", "hotkey": "ctrl+a"},
        ],
    )
    actions = load_actions(tmp_path, builtins=BUILTIN_ACTIONS)
    with pytest.raises(ValueError, match="reserved"):
        load_favorites(tmp_path, actions=actions)


def test_load_favorites_rejects_duplicate_hotkey(tmp_path) -> None:
    save_favorites(
        tmp_path,
        [
            {"id": "a", "target": "archive", "hotkey": "f5"},
            {"id": "b", "target": "delete", "hotkey": "f5"},
        ],
    )
    actions = load_actions(tmp_path, builtins=BUILTIN_ACTIONS)
    with pytest.raises(ValueError, match="duplicate favorite hotkey"):
        load_favorites(tmp_path, actions=actions)
