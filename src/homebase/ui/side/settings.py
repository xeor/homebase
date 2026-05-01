from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.text import Text
from textual.events import Key
from textual.widgets import DataTable, Static

from ...config.prefs import (
    save_open_mode_config,
    save_table_behavior_config,
    save_table_columns_config,
)
from ...core.constants import OPEN_MODE_CONFIG, OPEN_MODE_PROFILES, TABLE_SIDE_WIDTH_PRESETS
from ...core.utils import WIDGET_API_ERRORS


def refresh_settings_table(app: Any) -> None:
    table = app.query_one("#side_settings_table", DataTable)
    notes_widget = app.query_one("#side_settings_notes", Static)
    table.clear(columns=True)
    try:
        table.show_horizontal_scrollbar = False
    except WIDGET_API_ERRORS:
        pass
    notes_widget.update("")

    if app.side_settings_tab == "open":
        try:
            notes_widget.styles.height = 15
        except WIDGET_API_ERRORS:
            pass
        table.add_column("", width=3)
        table.add_column("MODE", width=54)
        rows = app._open_mode_rows()
        selected_profile = str(app.open_mode.get("profile", OPEN_MODE_CONFIG["profile"]))

        if app.open_settings_index < 0:
            app.open_settings_index = 0
        if app.open_settings_index >= len(rows):
            app.open_settings_index = len(rows) - 1
        for i, (profile_id, mode_line, _details) in enumerate(rows):
            enabled = profile_id == selected_profile
            table.add_row(Text("(x)" if enabled else "( )"), mode_line, key=str(i))
        try:
            table.cursor_coordinate = (app.open_settings_index, 0)
        except WIDGET_API_ERRORS:
            pass
        app._update_open_settings_details(rows)
        return

    if app.side_settings_tab == "table_config":
        try:
            notes_widget.styles.height = 15
        except WIDGET_API_ERRORS:
            pass
        table.add_column("", width=3)
        table.add_column("OPTION", width=36)
        table.add_column("VALUE", width=14)
        rows = app._table_config_rows()
        if app.table_config_index < 0:
            app.table_config_index = 0
        if app.table_config_index >= len(rows):
            app.table_config_index = max(0, len(rows) - 1)
        for i, (_key, label, _kind, value_text) in enumerate(rows):
            table.add_row(Text("*"), label, value_text, key=str(i))
        if rows:
            try:
                table.cursor_coordinate = (app.table_config_index, 0)
            except WIDGET_API_ERRORS:
                pass
        notes_widget.update(
            "space/enter cycles value\n"
            "pin WIP keeps WIP rows fixed at top while still sorted by current SORT\n"
            "info panel width applies immediately"
        )
        return

    table.add_column("", width=3)
    table.add_column("COLUMN", width=18)
    table.add_column("WIDTH", width=5)
    try:
        notes_widget.styles.height = 3
    except WIDGET_API_ERRORS:
        pass
    notes_widget.update(
        f"For table: {app.view_mode}\n"
        "changes here apply only to this view"
    )

    current_columns = app._table_columns_for_view(app.view_mode)
    if not current_columns:
        return
    if app.table_settings_index < 0:
        app.table_settings_index = 0
    if app.table_settings_index >= len(current_columns):
        app.table_settings_index = len(current_columns) - 1

    for i, col in enumerate(current_columns):
        cid = str(col.get("id", ""))
        enabled = bool(col.get("enabled", True))
        try:
            width = int(col.get("width", 12))
        except (TypeError, ValueError):
            width = 12
        cid_short = cid if len(cid) <= 18 else (cid[:15] + "...")
        table.add_row(Text("[x]" if enabled else "[ ]"), cid_short, str(width), key=str(i))
    try:
        table.cursor_coordinate = (app.table_settings_index, 0)
    except WIDGET_API_ERRORS:
        pass


def update_open_settings_details(
    app: Any,
    rows: list[tuple[str, str, str]] | None = None,
) -> None:
    if app.side_settings_tab != "open":
        return
    notes_widget = app.query_one("#side_settings_notes", Static)
    if rows is None:
        rows = app._open_mode_rows()
    if not rows:
        notes_widget.update("")
        return
    idx = max(0, min(app.open_settings_index, len(rows) - 1))
    details = rows[idx][2]
    wrapped = details.splitlines()
    max_lines = 15
    if len(wrapped) > max_lines:
        wrapped = wrapped[: max_lines - 1] + [wrapped[max_lines - 1][:73] + "..."]
    notes_widget.update("\n".join(wrapped))


def table_config_rows(app: Any) -> list[tuple[str, str, str, str]]:
    return [
        (
            "pin_wip_top",
            "Pin WIP rows at top (fixed rows)",
            "toggle",
            "on" if app._table_pin_wip_top_enabled() else "off",
        ),
        (
            "side_width_pct",
            "Info panel width",
            "choice",
            f"{app._table_side_width_pct()}%",
        ),
    ]


def table_config_save(app: Any, *, base_dir: Path) -> None:
    try:
        save_table_behavior_config(base_dir, app.table_behavior)
    except (OSError, TypeError, ValueError) as exc:
        app._show_runtime_error("save table config", exc)


def table_config_toggle_selected(app: Any, *, base_dir: Path) -> None:
    rows = app._table_config_rows()
    if not rows:
        return
    i = max(0, min(app.table_config_index, len(rows) - 1))
    key = rows[i][0]
    if key == "pin_wip_top":
        cur = bool(app.table_behavior.get(key, False))
        app.table_behavior[key] = not cur
    elif key == "side_width_pct":
        cur = app._table_side_width_pct()
        presets = list(TABLE_SIDE_WIDTH_PRESETS)
        if cur not in presets:
            presets.append(cur)
            presets.sort()
        idx = presets.index(cur)
        app.table_behavior[key] = presets[(idx + 1) % len(presets)]
    else:
        return
    table_config_save(app, base_dir=base_dir)
    app._refresh_settings_table()
    app._refresh_table()
    app._sync_side_tab_visibility()
    app._refresh_side()


def table_settings_save(app: Any, *, base_dir: Path) -> None:
    try:
        save_table_columns_config(base_dir, app.table_columns_by_view)
    except (OSError, TypeError, ValueError) as exc:
        app._show_runtime_error("save table settings", exc)


def table_settings_adjust_width(app: Any, delta: int, *, base_dir: Path) -> None:
    current_columns = app._table_columns_for_view(app.view_mode)
    if not current_columns:
        return
    i = max(0, min(app.table_settings_index, len(current_columns) - 1))
    try:
        cur = int(current_columns[i].get("width", 12))
    except (TypeError, ValueError):
        cur = 12
    current_columns[i]["width"] = max(4, min(80, cur + delta))
    table_settings_save(app, base_dir=base_dir)
    app._configure_table_columns()
    app._refresh_table()
    app._refresh_side()


def table_settings_toggle_enabled(app: Any, *, base_dir: Path) -> None:
    current_columns = app._table_columns_for_view(app.view_mode)
    if not current_columns:
        return
    i = max(0, min(app.table_settings_index, len(current_columns) - 1))
    current = bool(current_columns[i].get("enabled", True))
    current_columns[i]["enabled"] = not current
    table_settings_save(app, base_dir=base_dir)
    app._configure_table_columns()
    app._refresh_table()
    app._refresh_side()


def open_mode_save(app: Any, *, base_dir: Path) -> None:
    try:
        save_open_mode_config(base_dir, app.open_mode)
    except (OSError, TypeError, ValueError) as exc:
        app._show_runtime_error("save open mode settings", exc)


def open_mode_rows() -> list[tuple[str, str, str]]:
    return [
        (
            str(p.get("id", "")),
            str(p.get("name", "")),
            (
                f"[cyan]name[/]: {p.get('name', '')}\n"
                f"[cyan]tmux tab[/]: {'[green]yes[/]' if p.get('use_tmux') else '[red]no[/]'}\n"
                f"[cyan]tmux load[/]: {'[green]yes[/]' if p.get('run_load') else '[red]no[/]'}\n"
                f"[cyan]goto loaded pane[/]: {'[green]yes[/]' if p.get('goto_loaded') else '[red]no[/]'}\n"
                f"[cyan]fallback cd (no tmux)[/]: {'[green]yes[/]' if p.get('fallback_cd') else '[red]no[/]'}\n"
                "[dim]press space/enter to select this mode[/]"
            ),
        )
        for p in OPEN_MODE_PROFILES
    ]


def open_mode_select_selected(app: Any, *, base_dir: Path) -> None:
    rows = app._open_mode_rows()
    if not rows:
        return
    i = max(0, min(app.open_settings_index, len(rows) - 1))
    profile_id = rows[i][0]
    if str(app.open_mode.get("profile", "")) == profile_id:
        return
    app.open_mode["profile"] = profile_id
    open_mode_save(app, base_dir=base_dir)
    app._refresh_settings_table()
    app._update_open_settings_details(rows)


def table_settings_reorder(app: Any, delta: int, *, base_dir: Path) -> None:
    current_columns = app._table_columns_for_view(app.view_mode)
    if not current_columns:
        return
    i = max(0, min(app.table_settings_index, len(current_columns) - 1))
    j = i + delta
    if j < 0 or j >= len(current_columns):
        return
    current_columns[i], current_columns[j] = current_columns[j], current_columns[i]
    app.table_settings_index = j
    table_settings_save(app, base_dir=base_dir)
    app._configure_table_columns()
    app._refresh_table()
    app._refresh_side()


def handle_settings_table_key(app: Any, event: Key, *, base_dir: Path) -> bool:
    if app.side_main_tab != "settings" or app.side_settings_tab not in {
        "table",
        "table_config",
        "open",
    }:
        return False
    if app.side_settings_tab == "open":
        rows_count = len(app._open_mode_rows())
        if rows_count <= 0:
            return False
        if event.key in {"tab", "shift+tab", "backtab"}:
            step = -1 if event.key in {"shift+tab", "backtab"} else 1
            app.open_settings_index = (app.open_settings_index + step) % rows_count
            app._refresh_settings_table()
            app._update_open_settings_details()
            return True
        if event.key in {"space", "enter"}:
            open_mode_select_selected(app, base_dir=base_dir)
            return True
        return False

    if app.side_settings_tab == "table_config":
        rows_count = len(app._table_config_rows())
        if rows_count <= 0:
            return False
        if event.key in {"tab", "shift+tab", "backtab"}:
            step = -1 if event.key in {"shift+tab", "backtab"} else 1
            app.table_config_index = (app.table_config_index + step) % rows_count
            app._refresh_settings_table()
            return True
        if event.key in {"space", "enter"}:
            table_config_toggle_selected(app, base_dir=base_dir)
            return True
        return False

    current_columns = app._table_columns_for_view(app.view_mode)
    if not current_columns:
        return False
    if event.key in {"tab", "shift+tab", "backtab"}:
        step = -1 if event.key in {"shift+tab", "backtab"} else 1
        app.table_settings_index = (app.table_settings_index + step) % len(current_columns)
        app._refresh_side()
        return True
    if event.key == "space":
        table_settings_toggle_enabled(app, base_dir=base_dir)
        return True
    if event.key == "left":
        table_settings_reorder(app, -1, base_dir=base_dir)
        return True
    if event.key == "right":
        table_settings_reorder(app, 1, base_dir=base_dir)
        return True
    if event.key in {"minus"}:
        table_settings_adjust_width(app, -1, base_dir=base_dir)
        return True
    if event.key in {"plus", "equals"}:
        table_settings_adjust_width(app, 1, base_dir=base_dir)
        return True
    return False
