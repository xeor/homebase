from __future__ import annotations

from types import SimpleNamespace

from homebase.core.constants import SIDE_CHILD_TABS, SIDE_TOP_TABS, discover_tab_actions
from homebase.core.models import Action
from homebase.ui.actions.dispatch import dispatch_action


def test_discover_tab_actions_includes_top_and_child_ids() -> None:
    actions = discover_tab_actions()
    for top_key, _top_label in SIDE_TOP_TABS:
        assert f"tab.{top_key}" in actions
        for child_key, _child_label in SIDE_CHILD_TABS.get(top_key, []):
            assert f"tab.{top_key}.{child_key}" in actions


def test_dispatch_routes_tab_action_to_jump() -> None:
    seen: dict[str, str] = {}

    class _App:
        def __init__(self) -> None:
            self.ctx = SimpleNamespace(
                actions={
                    "tab.info.events": Action(
                        id="tab.info.events",
                        label="Events",
                        kind="builtin",
                        scope="tab",
                        multi="joined",
                        source="builtin",
                    )
                }
            )

        def _jump_to_side_tab(self, top: str, child_key: str = "") -> None:
            seen["tab"] = f"{top}/{child_key}" if child_key else top

        def _on_pick_actions(self, _value: str) -> None:
            return

        def _run_custom_action(self, _aid: str) -> None:
            return

    app = _App()
    dispatch_action(app, "tab.info.events")
    assert seen["tab"] == "info/events"
