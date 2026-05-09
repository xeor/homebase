from __future__ import annotations

from homebase.config.workspace import merge_actions
from homebase.core.constants import BUILTIN_ACTIONS


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
