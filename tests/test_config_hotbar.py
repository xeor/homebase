from __future__ import annotations

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
