from __future__ import annotations

import pytest

from homebase.config.prefs import load_actions, load_hotbar, load_keys, save_hotbar, save_keys
from homebase.core.constants import BUILTIN_ACTIONS


def test_load_hotbar_supports_action_entries(tmp_path) -> None:
    save_hotbar(
        tmp_path,
        [
            {"action": "archive"},
        ],
    )
    actions = load_actions(tmp_path, builtins=BUILTIN_ACTIONS)
    loaded = load_hotbar(tmp_path, actions=actions)
    assert [item.action for item in loaded] == ["archive"]


def test_save_keys_drops_invalid_entries(tmp_path) -> None:
    save_keys(
        tmp_path,
        {
            "": {"action": "archive"},
            "f5": {"action": "archive"},
        },
    )
    actions = load_actions(tmp_path, builtins=BUILTIN_ACTIONS)
    loaded = load_keys(tmp_path, actions=actions)
    assert set(loaded) == {"f5"}


def test_save_hotbar_persists_optional_label(tmp_path) -> None:
    save_hotbar(
        tmp_path,
        [
            {
                "action": "archive",
                "label": "Archive now",
            },
        ],
    )
    actions = load_actions(tmp_path, builtins=BUILTIN_ACTIONS)
    loaded = load_hotbar(tmp_path, actions=actions)
    assert [(item.action, item.label) for item in loaded] == [("archive", "Archive now")]


def test_hotbar_style_rules_roundtrip(tmp_path) -> None:
    save_hotbar(
        tmp_path,
        [
            {
                "action": "notes_create",
                "label": "Notes",
                "style": [
                    {"bg_color": "#112233", "fg_color": "#eeeeee", "bold": True, "when": "!n"},
                    {"bg_color": "#334455", "underline": True, "italic": True, "when": "#wip"},
                ],
            },
        ],
    )
    actions = load_actions(tmp_path, builtins=BUILTIN_ACTIONS)
    loaded = load_hotbar(tmp_path, actions=actions)
    assert len(loaded) == 1
    assert loaded[0].action == "notes_create"
    assert list(loaded[0].style) == [
        {"bg_color": "#112233", "fg_color": "#eeeeee", "bold": "1", "when": "!n"},
        {"bg_color": "#334455", "underline": "1", "italic": "1", "when": "#wip"},
    ]


def test_hotbar_style_requires_valid_hex_color(tmp_path) -> None:
    save_hotbar(
        tmp_path,
        [
            {
                "action": "notes_create",
                "style": [{"bg_color": "blue", "when": "#wip"}],
            },
        ],
    )
    actions = load_actions(tmp_path, builtins=BUILTIN_ACTIONS)
    with pytest.raises(ValueError, match="bg_color must be #RRGGBB"):
        load_hotbar(tmp_path, actions=actions)
