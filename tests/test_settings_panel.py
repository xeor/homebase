from __future__ import annotations

from pathlib import Path

from homebase.config.store import load_global_config_dict
from homebase.core.config_editor import ConfigEditorScreen
from homebase.ui.side import settings as settings_panel


class _AppStub:
    def __init__(self) -> None:
        self.side_main_tab = "settings"
        self.side_settings_tab = "table"
        self.view_mode = "active"
        self.table_settings_index = 0
        self.pushed: list[object] = []
        self.push_callbacks: list[object] = []

    def _table_columns_for_view(self, _view: str) -> list[dict[str, object]]:
        return []

    def push_screen(self, screen: object, callback: object = None) -> None:
        self.pushed.append(screen)
        self.push_callbacks.append(callback)

    def _show_runtime_error(self, _op: str, exc: Exception) -> None:
        raise AssertionError(str(exc))


def test_handle_settings_table_key_ignores_non_table_tab(tmp_path: Path) -> None:
    app = _AppStub()
    app.side_settings_tab = "other"

    class _Event:
        key = "enter"

    handled = settings_panel.handle_settings_table_key(app, _Event(), base_dir=tmp_path)
    assert handled is False


def test_open_config_editor_modal_pushes_screen_and_saves(tmp_path: Path) -> None:
    app = _AppStub()

    settings_panel.open_config_editor_modal(app, base_dir=tmp_path)

    assert len(app.pushed) == 1
    screen = app.pushed[0]
    assert isinstance(screen, ConfigEditorScreen)
    # on-close callback is wired for autoreload
    assert callable(app.push_callbacks[0])

    # on_apply persists the desired config to disk
    screen._on_apply({"archive": {"timezone": "UTC"}})
    assert load_global_config_dict(tmp_path) == {"archive": {"timezone": "UTC"}}


def test_close_reloads_only_after_apply(tmp_path: Path, monkeypatch) -> None:
    app = _AppStub()
    calls: list[Path] = []
    monkeypatch.setattr(
        settings_panel,
        "reload_global_config",
        lambda _app, *, base_dir: calls.append(base_dir),
    )

    settings_panel.open_config_editor_modal(app, base_dir=tmp_path)
    close_cb = app.push_callbacks[0]

    # peek-and-escape: no apply happened, so no reload/toast
    close_cb(None)
    assert calls == []

    # after a successful apply, closing reloads once
    app.pushed[0]._on_apply({"archive": {"timezone": "UTC"}})
    close_cb(None)
    assert calls == [tmp_path]
