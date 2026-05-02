from __future__ import annotations

from textual.events import Key
from textual.widgets import DataTable

from .query import key_input as textual_ui_key_input
from .query import selection_events as textual_ui_selection_events
from .side import tabs as textual_ui_side_tabs


class AppEventsMixin:
    def on_button_pressed(self, event) -> None:
        textual_ui_side_tabs.on_button_pressed(self, event)

    def on_data_table_row_highlighted(
        self, event: DataTable.RowHighlighted
    ) -> None:
        textual_ui_selection_events.on_data_table_row_highlighted(self, event)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        textual_ui_selection_events.on_data_table_row_selected(self, event)

    def on_key(self, event: Key) -> None:
        textual_ui_key_input.on_key(
            self,
            event,
            widget_projects="#projects",
            wip_open_symbol_map=self.ctx.wip_open_symbol_map,
        )
