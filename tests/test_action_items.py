from __future__ import annotations

from pathlib import Path

from homebase.ui.actions import action_items


class _AppStub:
    def __init__(self) -> None:
        self.custom_actions = [
            {
                "id": "hotkey_open_item",
                "scope": "item",
                "action": "custom:open_item",
            }
        ]
        self.picked: str | None = None

    def _on_pick_actions(self, value: str | None) -> None:
        self.picked = value


def test_run_custom_action_dispatches_action_target() -> None:
    app = _AppStub()
    action_items.run_custom_action(app, "hotkey_open_item", base_dir=Path("/tmp"), fmt_ymd=lambda _x: "")
    assert app.picked == "custom:open_item"
