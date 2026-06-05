from __future__ import annotations

import pytest

from homebase.config.workspace import load_actions, load_favorites, merge_actions
from homebase.core.constants import BUILTIN_ACTIONS, discover_tab_actions


def test_merge_actions_with_empty_user_actions_returns_builtins() -> None:
    merged = merge_actions(BUILTIN_ACTIONS, {}, [])
    assert set(merged) == set(BUILTIN_ACTIONS)
    assert all(action.source == "builtin" for action in merged.values())


def test_merge_actions_adds_custom_action_as_config_source() -> None:
    merged = merge_actions(
        BUILTIN_ACTIONS,
        {},
        [{"id": "open_codium", "scope": "target", "command": "codium {{ full_path }}"}],
    )
    assert merged["open_codium"].source == "config"
    assert merged["open_codium"].kind == "shell"


def test_merge_actions_overrides_builtin_label_source() -> None:
    merged = merge_actions(
        BUILTIN_ACTIONS,
        {"archive": {"label": "Archive now"}},
        [],
    )
    assert merged["archive"].source == "overridden"
    assert merged["archive"].label == "Archive now"


def test_load_favorites_allows_tab_target_without_action_lookup() -> None:
    builtins = dict(BUILTIN_ACTIONS)
    builtins.update(discover_tab_actions())
    actions = load_actions({}, builtins=builtins)
    out = load_favorites(
        {"favorites": [{"target": "tab:projects/log", "favorite": True}]},
        actions=actions,
    )
    assert out and out[0]["target"] == "tab:projects/log"


def test_load_favorites_rejects_unknown_action_target() -> None:
    actions = load_actions({}, builtins=BUILTIN_ACTIONS)
    with pytest.raises(ValueError, match="favorite action not found"):
        load_favorites(
            {"favorites": [{"target": "no_such_action", "favorite": True}]},
            actions=actions,
        )
