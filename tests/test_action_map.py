from __future__ import annotations

import pytest

from homebase.config.workspace import load_actions, load_hotbar, merge_actions
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


def test_load_hotbar_rejects_tab_action() -> None:
    builtins = dict(BUILTIN_ACTIONS)
    builtins.update(discover_tab_actions())
    actions = load_actions({}, builtins=builtins)
    with pytest.raises(ValueError, match="cannot be on the hotbar"):
        load_hotbar({"hotbar": ["tab.info.events"]}, actions=actions)
