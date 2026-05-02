from __future__ import annotations

from .actions import wip_actions as textual_ui_wip_actions
from .query import selection_events as textual_ui_selection_events
from .table import nav as textual_ui_table_nav
from .table import tabs_state as textual_ui_tabs_state


class AppActionsMixin:
    def action_cycle_tabs(self) -> None:
        textual_ui_tabs_state.action_cycle_tabs(self)

    def action_cycle_tabs_prev(self) -> None:
        textual_ui_tabs_state.action_cycle_tabs_prev(self)

    def action_query_left(self) -> None:
        textual_ui_table_nav.action_query_left(self)

    def action_query_right(self) -> None:
        textual_ui_table_nav.action_query_right(self)

    def action_query_home(self) -> None:
        textual_ui_table_nav.action_query_home(self)

    def action_query_end(self) -> None:
        textual_ui_table_nav.action_query_end(self)

    def action_table_scroll_left(self) -> None:
        textual_ui_table_nav.action_table_scroll_left(self)

    def action_table_scroll_right(self) -> None:
        textual_ui_table_nav.action_table_scroll_right(self)

    def action_route_left(self) -> None:
        textual_ui_table_nav.action_route_left(self)

    def action_route_right(self) -> None:
        textual_ui_table_nav.action_route_right(self)

    def action_route_home(self) -> None:
        textual_ui_table_nav.action_route_home(self)

    def action_route_end(self) -> None:
        textual_ui_table_nav.action_route_end(self)

    def action_toggle_select_mode(self) -> None:
        textual_ui_selection_events.action_toggle_select_mode(self)

    def action_toggle_selected(self) -> None:
        textual_ui_selection_events.action_toggle_selected(self)

    def action_refresh_details(self) -> None:
        textual_ui_wip_actions.action_refresh_details(self)

    def action_open_wip_1(self) -> None:
        textual_ui_wip_actions.action_open_wip_index(self, 1)

    def action_open_wip_2(self) -> None:
        textual_ui_wip_actions.action_open_wip_index(self, 2)

    def action_open_wip_3(self) -> None:
        textual_ui_wip_actions.action_open_wip_index(self, 3)

    def action_open_wip_4(self) -> None:
        textual_ui_wip_actions.action_open_wip_index(self, 4)

    def action_open_wip_5(self) -> None:
        textual_ui_wip_actions.action_open_wip_index(self, 5)

    def action_open_wip_6(self) -> None:
        textual_ui_wip_actions.action_open_wip_index(self, 6)

    def action_open_wip_7(self) -> None:
        textual_ui_wip_actions.action_open_wip_index(self, 7)

    def action_open_wip_8(self) -> None:
        textual_ui_wip_actions.action_open_wip_index(self, 8)

    def action_open_wip_9(self) -> None:
        textual_ui_wip_actions.action_open_wip_index(self, 9)
