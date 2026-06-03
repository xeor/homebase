from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from textual.widgets import Tab

from ...core.utils import WIDGET_API_ERRORS


def on_tabs_tab_activated(
    app: Any,
    event: Any,
    *,
    side_top_tabs: list[tuple[str, str]],
    side_child_tabs: dict[str, list[tuple[str, str]]],
) -> None:
    tabs_id = getattr(event.tabs, "id", "")
    tab = getattr(event, "tab", None)
    tab_id = str(getattr(tab, "id", "") or "")
    if tabs_id == "side_main_tabs":
        top_keys = {key for key, _label in side_top_tabs}
        if tab_id in top_keys:
            app.side_main_tab = tab_id
        app._sync_side_tab_visibility()
    elif tabs_id == "side_selected_tabs":
        child_keys = {key for key, _label in side_child_tabs.get("selected", [])}
        if tab_id in child_keys:
            app.side_selected_tab = tab_id
    elif tabs_id == "side_info_tabs":
        child_keys = {key for key, _label in side_child_tabs.get("info", [])}
        if tab_id in child_keys:
            app.side_info_tab = tab_id
    elif tabs_id == "side_settings_tabs":
        child_keys = {key for key, _label in side_child_tabs.get("settings", [])}
        if tab_id in child_keys:
            app.side_settings_tab = tab_id
    app._sync_side_tab_visibility()
    app._mark_state_dirty()
    app._refresh_side()


@dataclass
class _TabActiveFlags:
    settings_table: bool
    settings_config: bool
    settings_global: bool
    selected_readme: bool
    selected_notes: bool

    @property
    def settings(self) -> bool:
        return self.settings_table or self.settings_config


def _compute_active_flags(app: Any) -> _TabActiveFlags:
    return _TabActiveFlags(
        settings_table=(
            app.side_main_tab == "settings"
            and app.side_settings_tab in {"table", "open"}
        ),
        settings_config=(
            app.side_main_tab == "settings"
            and app.side_settings_tab == "table_config"
        ),
        settings_global=(
            app.side_main_tab == "settings" and app.side_settings_tab == "global"
        ),
        selected_readme=(
            app.side_main_tab == "selected" and app.side_selected_tab == "readme"
        ),
        selected_notes=(
            app.side_main_tab == "selected" and app.side_selected_tab == "notes"
        ),
    )


def _apply_side_widths(
    app: Any, projects: Any, side: Any, left: Any, right: Any
) -> None:
    try:
        side_pct = app._table_side_width_pct()
        projects_pct = max(10, 100 - side_pct)
        projects.styles.width = f"{projects_pct}%"
        side.styles.width = f"{side_pct}%"
        left.styles.width = f"{projects_pct}%"
        right.styles.width = f"{side_pct}%"
    except WIDGET_API_ERRORS:
        pass


def _apply_visibility(
    app: Any,
    flags: _TabActiveFlags,
    *,
    side_scroll: Any,
    side_body: Any,
    side_readme_panel: Any,
    side_notes_panel: Any,
    side_global_panel: Any,
    settings_table: Any,
    settings_notes: Any,
    settings_config_panel: Any,
) -> None:
    side_scroll.display = not flags.settings
    side_body.display = (
        not flags.settings
        and not flags.selected_readme
        and not flags.selected_notes
        and not flags.settings_global
    )
    side_readme_panel.display = not flags.settings and flags.selected_readme
    side_notes_panel.display = not flags.settings and flags.selected_notes
    side_global_panel.display = flags.settings_global
    settings_table.display = flags.settings_table
    settings_config_panel.display = flags.settings_config
    settings_notes.display = (
        app.side_main_tab == "settings"
        and app.side_settings_tab in {"table", "open"}
    )


def _try_set(widget: Any, attr: str, value: object) -> None:
    try:
        setattr(widget, attr, value)
    except WIDGET_API_ERRORS:
        pass


def _try_focus(widget: Any) -> None:
    try:
        widget.focus()
    except WIDGET_API_ERRORS:
        pass


def _apply_focus_rules(
    app: Any,
    projects: Any,
    side: Any,
    settings_table: Any,
    flags: _TabActiveFlags,
    projects_locked: bool,
) -> None:
    _try_set(projects, "can_focus", not projects_locked)
    _try_set(projects, "disabled", projects_locked)
    _try_set(settings_table, "can_focus", flags.settings_table)
    _try_set(side, "can_focus", False)
    if (
        flags.settings_table
        and not settings_table.has_focus
        and not app._modal_active()
    ):
        _try_focus(settings_table)
    if flags.settings_config and not app._modal_active():
        try:
            first_cfg = app.query_one("#cfg_pin_wip")
            if not first_cfg.has_focus:
                first_cfg.focus()
        except WIDGET_API_ERRORS:
            pass
    if (
        app._main_table_was_locked
        and not projects_locked
        and not app._modal_active()
    ):
        _try_focus(projects)


def sync_side_tab_visibility(app: Any, *, widget_projects: str) -> None:
    side = app.query_one("#side")
    projects = app.query_one(widget_projects)
    selected_tabs = app.query_one("#side_selected_tabs")
    info_tabs = app.query_one("#side_info_tabs")
    settings_tabs = app.query_one("#side_settings_tabs")
    side_scroll = app.query_one("#side_scroll")
    global_meta_left = app.query_one("#global_meta_left")
    global_meta_right = app.query_one("#global_meta_right")
    side_body = app.query_one("#side_body")
    side_readme_panel = app.query_one("#side_readme_panel")
    side_notes_panel = app.query_one("#side_notes_panel")
    side_global_panel = app.query_one("#side_global_panel")
    settings_table = app.query_one("#side_settings_table")
    settings_notes = app.query_one("#side_settings_notes")
    settings_config_panel = app.query_one("#side_settings_config_panel")
    app._refresh_settings_tab_labels(settings_tabs)
    selected_tabs.display = app.side_main_tab == "selected"
    info_tabs.display = app.side_main_tab == "info"
    settings_tabs.display = app.side_main_tab == "settings"
    flags = _compute_active_flags(app)
    _apply_side_widths(app, projects, side, global_meta_left, global_meta_right)
    _apply_visibility(
        app,
        flags,
        side_scroll=side_scroll,
        side_body=side_body,
        side_readme_panel=side_readme_panel,
        side_notes_panel=side_notes_panel,
        side_global_panel=side_global_panel,
        settings_table=settings_table,
        settings_notes=settings_notes,
        settings_config_panel=settings_config_panel,
    )
    projects_locked = main_table_interaction_locked(app)
    _apply_focus_rules(
        app, projects, side, settings_table, flags, projects_locked
    )
    app._main_table_was_locked = projects_locked


def main_table_interaction_locked(app: Any) -> bool:
    if app.side_main_tab == "settings" and app.side_settings_tab in {
        "table",
        "table_config",
        "open",
    }:
        return True
    if app.side_main_tab == "selected" and app.side_selected_tab in {
        "readme",
        "notes",
    }:
        return True
    return False


def refresh_settings_tab_labels(app: Any, settings_tabs: Any) -> None:
    view_suffix = f"[{app.view_mode}]"
    for tab in settings_tabs.query(Tab):
        tab_id = str(getattr(tab, "id", "") or "")
        try:
            if tab_id == "table":
                tab.label = f"Table {view_suffix}"
            elif tab_id == "table_config":
                tab.label = "Config"
            elif tab_id == "open":
                tab.label = "Open"
            elif tab_id == "global":
                tab.label = "Config-file"
        except WIDGET_API_ERRORS:
            continue


def set_tabs_active_safe(tabs: Any, tab_id: str) -> None:
    if not tab_id:
        return
    try:
        tabs.active = tab_id
    except WIDGET_API_ERRORS:
        pass


def child_key_for_top(app: Any, top_key: str) -> str:
    if top_key == "selected":
        return app.side_selected_tab
    if top_key == "info":
        return app.side_info_tab
    return app.side_settings_tab


def set_child_key_for_top(app: Any, top_key: str, child_key: str) -> None:
    if top_key == "selected":
        app.side_selected_tab = child_key
    elif top_key == "info":
        app.side_info_tab = child_key
    elif top_key == "settings":
        app.side_settings_tab = child_key


def jump_to_side_tab(
    app: Any,
    top_key: str,
    *,
    child_key: str = "",
    side_top_tabs: list[tuple[str, str]],
    side_child_tabs: dict[str, list[tuple[str, str]]],
) -> None:
    valid_top = {k for k, _label in side_top_tabs}
    if top_key not in valid_top:
        return
    app.side_main_tab = top_key
    if child_key:
        valid_child = {k for k, _label in side_child_tabs.get(top_key, [])}
        if child_key in valid_child:
            app._set_child_key_for_top(top_key, child_key)
    app._apply_side_tab_state_to_widgets()
    app._sync_side_tab_visibility()
    app._mark_state_dirty()
    app._refresh_side()


def apply_side_tab_state_to_widgets(app: Any) -> None:
    main_tabs = app.query_one("#side_main_tabs")
    sel_tabs = app.query_one("#side_selected_tabs")
    info_tabs = app.query_one("#side_info_tabs")
    settings_tabs = app.query_one("#side_settings_tabs")
    app._set_tabs_active_safe(main_tabs, app.side_main_tab)
    app._set_tabs_active_safe(sel_tabs, app.side_selected_tab)
    app._set_tabs_active_safe(info_tabs, app.side_info_tab)
    app._set_tabs_active_safe(settings_tabs, app.side_settings_tab)


def cycle_tabs(
    app: Any,
    *,
    reverse: bool = False,
    side_top_tabs: list[tuple[str, str]],
    side_child_tabs: dict[str, list[tuple[str, str]]],
) -> None:
    top_order = [key for key, _label in side_top_tabs]
    if not top_order:
        return
    if app.side_main_tab not in top_order:
        app.side_main_tab = top_order[0]

    children = [key for key, _label in side_child_tabs.get(app.side_main_tab, [])]
    if children:
        current_child = app._child_key_for_top(app.side_main_tab)
        if current_child not in children:
            app._set_child_key_for_top(
                app.side_main_tab, children[-1] if reverse else children[0]
            )
        else:
            idx = children.index(current_child)
            if reverse:
                if idx > 0:
                    app._set_child_key_for_top(app.side_main_tab, children[idx - 1])
                else:
                    top_idx = top_order.index(app.side_main_tab)
                    app.side_main_tab = top_order[(top_idx - 1) % len(top_order)]
                    prev_children = [
                        key for key, _label in side_child_tabs.get(app.side_main_tab, [])
                    ]
                    if prev_children:
                        app._set_child_key_for_top(app.side_main_tab, prev_children[-1])
            else:
                if idx < len(children) - 1:
                    app._set_child_key_for_top(app.side_main_tab, children[idx + 1])
                else:
                    top_idx = top_order.index(app.side_main_tab)
                    app.side_main_tab = top_order[(top_idx + 1) % len(top_order)]
                    next_children = [
                        key for key, _label in side_child_tabs.get(app.side_main_tab, [])
                    ]
                    if next_children:
                        app._set_child_key_for_top(app.side_main_tab, next_children[0])
    else:
        top_idx = top_order.index(app.side_main_tab)
        app.side_main_tab = (
            top_order[(top_idx - 1) % len(top_order)]
            if reverse
            else top_order[(top_idx + 1) % len(top_order)]
        )

    app._sync_side_tab_visibility()
    app._apply_side_tab_state_to_widgets()
    app._mark_state_dirty()
    app._refresh_side()


def action_cycle_tabs(app: Any) -> None:
    app._cycle_tabs(reverse=False)


def action_cycle_tabs_prev(app: Any) -> None:
    app._cycle_tabs(reverse=True)
