from __future__ import annotations

import pytest

from homebase.config.workspace import load_actions, load_favorites
from homebase.core.constants import BUILTIN_ACTIONS, discover_tab_actions


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
