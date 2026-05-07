from __future__ import annotations

from pathlib import Path

from homebase.ui.side import settings as settings_panel


class _AppStub:
    def __init__(self) -> None:
        self.side_main_tab = "settings"
        self.side_settings_tab = "global"
        self.opened: Path | None = None
        self.status = ""

    def _open_editor_for_path(self, path: Path, wait: bool = False, on_done=None) -> None:
        self.opened = path
        if on_done is not None:
            on_done()

    def _reset_query_completion(self) -> None:
        return None

    def _mark_state_dirty(self) -> None:
        return None

    def _queue_query_apply(self) -> None:
        return None

    def _refresh_settings_table(self) -> None:
        return None

    def _refresh_side(self) -> None:
        return None

    def _set_runtime_status(self, text: str, _level: str, ttl_s: float = 0.0) -> None:
        self.status = f"{text}:{ttl_s}"

    def _show_runtime_error(self, _op: str, exc: Exception) -> None:
        raise AssertionError(str(exc))


def test_handle_settings_table_key_global_opens_editor_and_reloads(tmp_path: Path) -> None:
    app = _AppStub()

    class _Event:
        key = "enter"

    handled = settings_panel.handle_settings_table_key(app, _Event(), base_dir=tmp_path)
    assert handled is True
    assert app.opened == tmp_path / ".homebase" / "config.yaml"
    assert app.status.startswith("global config reloaded")
