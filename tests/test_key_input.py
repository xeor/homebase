from __future__ import annotations

from homebase.ui.query import key_input


class _Event:
    def __init__(self, key: str, character: str | None = None) -> None:
        self.key = key
        self.character = character
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class _DataTableStub:
    def __init__(self, has_focus: bool = True) -> None:
        self.has_focus = has_focus


class _AppStub:
    def __init__(self) -> None:
        self.focused = None
        self.side_main_tab = "selected"
        self.side_selected_tab = "overview"
        self.select_mode = False
        self.query = ""
        self.query_cursor = 0
        self.filter_expr = ""
        self.dispatched_target = ""
        self._table = _DataTableStub(has_focus=True)

    def _modal_active(self) -> bool:
        return False

    def _handle_settings_table_key(self, _event) -> bool:
        return False

    def _table_is_active_focus(self) -> bool:
        return True

    def _cancel_restore_for_current_view(self) -> None:
        return None

    def _open_wip_index(self, _idx: int) -> None:
        return None

    def _dispatch_hotkey_target(self, value: str) -> None:
        self.dispatched_target = value

    def query_one(self, _selector: str, _cls):
        return self._table


def test_on_key_dispatches_custom_hotkey_target() -> None:
    app = _AppStub()
    event = _Event("f5")
    key_input.on_key(
        app,
        event,
        widget_projects="#projects",
        wip_open_symbol_map={},
        custom_hotkey_targets={"f5": "custom:vscode"},
    )
    assert app.dispatched_target == "custom:vscode"
    assert event.stopped is True


def test_on_key_dispatches_custom_hotkey_target_from_character() -> None:
    app = _AppStub()
    event = _Event("t", character="†")
    key_input.on_key(
        app,
        event,
        widget_projects="#projects",
        wip_open_symbol_map={},
        custom_hotkey_targets={"†": "custom:open_item_in_tmux_window"},
    )
    assert app.dispatched_target == "custom:open_item_in_tmux_window"
    assert event.stopped is True
