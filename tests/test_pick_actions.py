from __future__ import annotations

from pathlib import Path

from homebase.ui.actions import pick_actions


class _Row:
    def __init__(self, path: Path, archived: bool = False, packed: bool = False, description: str = "") -> None:
        self.path = path
        self.archived = archived
        self.packed = packed
        self.description = description


class _AppStub:
    def __init__(self) -> None:
        self.custom_called = ""
        self.pending_rename_target = None
        self.global_edit_called = False
        self.global_reload_called = False
        self._selected = _Row(Path("/tmp/a"))
        self.pushed = []

    def _run_custom_action(self, cid: str) -> None:
        self.custom_called = cid

    def _run_readme_button_action(self, _value: str) -> None:
        pass

    def _run_notes_button_action(self, _value: str) -> None:
        pass

    def _target_rows(self):
        return [self._selected]

    def _selected_row(self):
        return self._selected

    @staticmethod
    def _input_screen_cls(title: str, prompt: str, initial: str):
        return (title, prompt, initial)

    @staticmethod
    def _confirm_screen_cls(title: str, details: str):
        return (title, details)

    def push_screen(self, screen, cb):
        self.pushed.append((screen, cb))

    def _on_rename_item(self, _value: str | None) -> None:
        pass

    def _build_bulk_confirm_payload(self, action: str, paths: list[Path]):
        return action, str(paths)

    def _on_confirm_bulk(self, _ok: bool, _action: str, _paths: list[Path]) -> None:
        pass

    def _edit_global_config_and_reload(self) -> None:
        self.global_edit_called = True

    def _reload_global_config(self) -> None:
        self.global_reload_called = True


def test_on_pick_actions_dispatches_custom_action() -> None:
    app = _AppStub()
    pick_actions.on_pick_actions(app, "custom:foo")
    assert app.custom_called == "foo"


def test_on_pick_actions_dispatches_rename_item() -> None:
    app = _AppStub()
    pick_actions.on_pick_actions(app, "rename_item")
    assert app.pending_rename_target == Path("/tmp/a")
    assert app.pushed


def test_on_pick_actions_dispatches_edit_global_config() -> None:
    app = _AppStub()
    pick_actions.on_pick_actions(app, "edit_global_config")
    assert app.global_edit_called is True


def test_on_pick_actions_dispatches_reload_global_config() -> None:
    app = _AppStub()
    pick_actions.on_pick_actions(app, "reload_global_config")
    assert app.global_reload_called is True
