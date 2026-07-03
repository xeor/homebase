"""Pilot tests for the settings side-tab (config-editor buttons + modal)."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from textual.containers import Vertical
from textual.widgets import Button, DataTable, Static

from homebase.core.config_editor import ConfigEditorScreen
from homebase.ui.app import BApp
from homebase.ui.context import UIContext


def _ctx(tmp_path) -> UIContext:
    return UIContext(
        base_dir=tmp_path,
        archive_tz=ZoneInfo("UTC"),
        archive_tz_name="UTC",
        property_defs=[],
        wip_open_symbol_map={},
        named_filters={},
        saved_filter_queries=[],
        suffixes=[],
        file_view_exclude_patterns=[],
        custom_actions=[],
        favorites=[],
        actions={},
        open_mode_config={"profile": "terminal"},
        notes_config={},
        reconcile_config={
            "active": {"enabled": False, "interval_s": 11.0},
            "archive": {"enabled": False, "interval_s": 22.0},
        },
    )


async def test_settings_general_tab_shows_info_and_buttons(tmp_path) -> None:
    app = BApp(tmp_path, ctx=_ctx(tmp_path))
    async with app.run_test() as pilot:
        app.side_main_tab = "settings"
        app.side_settings_tab = "general"
        app._apply_side_tab_state_to_widgets()
        app._sync_side_tab_visibility()
        app._refresh_side()
        await pilot.pause()

        general = app.query_one("#side_settings_general", Vertical)
        table = app.query_one("#side_settings_table", DataTable)
        assert general.display is True
        assert table.display is False
        # both config buttons are inside the general panel
        app.query_one("#side_config_editor_open", Button)
        app.query_one("#side_config_file_open", Button)
        info = app.query_one("#side_settings_general_info", Static)
        assert "Global config" in str(info.render())


async def test_settings_table_tab_shows_table_hides_general(tmp_path) -> None:
    app = BApp(tmp_path, ctx=_ctx(tmp_path))
    async with app.run_test() as pilot:
        app.side_main_tab = "settings"
        app.side_settings_tab = "table"
        app._apply_side_tab_state_to_widgets()
        app._sync_side_tab_visibility()
        await pilot.pause()

        general = app.query_one("#side_settings_general", Vertical)
        table = app.query_one("#side_settings_table", DataTable)
        assert general.display is False
        assert table.display is True


async def test_settings_editor_button_pushes_config_editor_screen(tmp_path) -> None:
    app = BApp(tmp_path, ctx=_ctx(tmp_path))
    async with app.run_test() as pilot:
        app.side_main_tab = "settings"
        app.side_settings_tab = "general"
        app._sync_side_tab_visibility()
        await pilot.pause()

        app._open_config_editor_modal()
        await pilot.pause()

        assert isinstance(app.screen, ConfigEditorScreen)
        app.screen.dismiss(None)
        await pilot.pause()
