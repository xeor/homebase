from __future__ import annotations

from types import SimpleNamespace

from homebase.core.models import Action
from homebase.ui.actions.dispatch import dispatch_action, normalize_action_target


class _App:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.ctx = SimpleNamespace(
            actions={
                "archive": Action(
                    id="archive",
                    label="Archive",
                    kind="builtin",
                    scope="target",
                    multi="joined",
                    source="builtin",
                ),
                "custom_shell": Action(
                    id="custom_shell",
                    label="Shell",
                    kind="shell",
                    scope="target",
                    multi="joined",
                    command="true",
                    source="config",
                ),
            }
        )

    def _on_pick_actions(self, value: str) -> None:
        self.calls.append(("pick", value))

    def _run_custom_action(self, action_id: str) -> None:
        self.calls.append(("custom", action_id))

    def action_open_selected(self) -> None:
        self.calls.append(("open", "open_selected"))

    def _jump_to_side_tab(self, top: str, child_key: str = "") -> None:
        self.calls.append(("tab", f"{top}/{child_key}"))

    def _log(self, msg: str, level: str) -> None:
        self.calls.append(("log", f"{level}:{msg}"))

    def _refresh_side(self) -> None:
        self.calls.append(("refresh", "side"))


def test_normalize_action_target_legacy_prefixes() -> None:
    assert normalize_action_target("action:archive") == "archive"
    assert normalize_action_target("action:custom:open_item_in_codium") == "open_item_in_codium"
    assert normalize_action_target("tab:side_main/selected") == "tab.side_main.selected"


def test_dispatch_action_by_kind() -> None:
    app = _App()
    dispatch_action(app, "archive")
    dispatch_action(app, "custom_shell")
    dispatch_action(app, "open_selected")
    dispatch_action(app, "tab.info.events")
    assert ("pick", "archive") in app.calls
    assert ("custom", "custom_shell") in app.calls
    assert ("open", "open_selected") in app.calls
    assert ("tab", "info/events") in app.calls
