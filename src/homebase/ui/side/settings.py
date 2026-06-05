from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from rich.text import Text
from textual.events import Key
from textual.widgets import DataTable, Input, Select, Static, Switch

from ...config.hooks import load_hook_refresh_config, load_hook_specs
from ...config.prefs import (
    load_actions,
    load_archive_timezone_name,
    load_cache_profile_table,
    load_favorites,
    load_file_view_exclude_patterns,
    load_notes_config,
    load_open_mode_config,
    load_reconcile_config,
    load_saved_filter_queries,
    load_suffixes,
    load_wip_symbol_map,
    save_archive_timezone_name,
    save_open_mode_config,
    save_table_behavior_config,
    save_table_columns_config,
)
from ...config.property_defs import load_property_defs
from ...config.store import clear_global_config_cache
from ...core import runtime_init
from ...core.constants import (
    ARCHIVE_TZ_PRESETS,
    BUILTIN_ACTIONS,
    DEFAULT_ARCHIVE_TZ_NAME,
    GLOBAL_CONFIG_FILE_NAME,
    HOMEBASE_DIR_NAME,
    OPEN_MODE_CONFIG,
    OPEN_MODE_PROFILES,
    PREVIEW_ENTRIES_LIMIT_MAX,
    PREVIEW_ENTRIES_LIMIT_MIN,
    discover_tab_actions,
)
from ...core.utils import WIDGET_API_ERRORS
from ..context import UIContext


def _set_notes_height(notes_widget: Static, value: int) -> None:
    try:
        notes_widget.styles.height = value
    except WIDGET_API_ERRORS:
        pass


def _set_cursor_coordinate(table: DataTable, coord: tuple[int, int]) -> None:
    from textual.coordinate import Coordinate

    try:
        table.cursor_coordinate = Coordinate(*coord)
    except WIDGET_API_ERRORS:
        pass


def _refresh_open_settings(app: Any, table: DataTable, notes_widget: Static) -> None:
    _set_notes_height(notes_widget, 15)
    table.add_column("", width=3)
    table.add_column("MODE", width=54)
    rows = app._open_mode_rows()
    selected_profile = str(
        app.open_mode.get("profile", OPEN_MODE_CONFIG["profile"])
    )
    if app.open_settings_index < 0:
        app.open_settings_index = 0
    if app.open_settings_index >= len(rows):
        app.open_settings_index = len(rows) - 1
    for i, (profile_id, mode_line, _details) in enumerate(rows):
        enabled = profile_id == selected_profile
        table.add_row(Text("(x)" if enabled else "( )"), mode_line, key=str(i))
    _set_cursor_coordinate(table, (app.open_settings_index, 0))
    app._update_open_settings_details(rows)


def _refresh_global_settings(table: DataTable, notes_widget: Static) -> None:
    _set_notes_height(notes_widget, 15)
    table.add_column("", width=3)
    table.add_column("ACTION", width=54)
    table.add_row(Text("*"), "Edit global config in $EDITOR", key="0")
    _set_cursor_coordinate(table, (0, 0))
    notes_widget.update(
        "enter/space opens .homebase/config.yaml in $EDITOR\n"
        "when editor exits, runtime config is reloaded"
    )


def _refresh_table_columns(app: Any, table: DataTable, notes_widget: Static) -> None:
    table.add_column("", width=3)
    table.add_column("COLUMN", width=18)
    table.add_column("WIDTH", width=14)
    _set_notes_height(notes_widget, 3)
    notes_widget.update(
        f"For table: {app.view_mode}\nchanges here apply only to this view"
    )
    current_columns = app._table_columns_for_view(app.view_mode)
    if not current_columns:
        return
    if app.table_settings_index < 0:
        app.table_settings_index = 0
    if app.table_settings_index >= len(current_columns):
        app.table_settings_index = len(current_columns) - 1
    enabled_cols = [c for c in current_columns if bool(c.get("enabled", True))]
    last_enabled_id = (
        str(enabled_cols[-1].get("id", "")).strip() if enabled_cols else ""
    )
    effective_widths = dict(
        getattr(app, "_visible_column_effective_width_by_id", {}) or {}
    )
    for i, col in enumerate(current_columns):
        cid = str(col.get("id", ""))
        enabled = bool(col.get("enabled", True))
        try:
            width = int(col.get("width", 12))
        except (TypeError, ValueError):
            width = 12
        cid_short = cid if len(cid) <= 18 else (cid[:15] + "...")
        width_text = str(width)
        effective = int(effective_widths.get(cid, 0) or 0)
        if (
            enabled
            and cid == last_enabled_id
            and effective > 0
            and effective != width
        ):
            width_text = f"{width} ({effective})"
        table.add_row(
            Text("[x]" if enabled else "[ ]"),
            cid_short,
            width_text,
            key=str(i),
        )
    _set_cursor_coordinate(table, (app.table_settings_index, 0))


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
        _refresh_open_settings(app, table, notes_widget)
        return
    if app.side_settings_tab == "table_config":
        populate_config_panel(app)
        return
    if app.side_settings_tab == "global":
        _refresh_global_settings(table, notes_widget)
        return
    _refresh_table_columns(app, table, notes_widget)


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


def table_config_save(app: Any, *, base_dir: Path) -> None:
    try:
        save_table_behavior_config(base_dir, app.table_behavior)
    except (OSError, TypeError, ValueError) as exc:
        app._show_runtime_error("save table config", exc)


CONFIG_WIDGET_IDS: frozenset[str] = frozenset(
    {"cfg_pin_wip", "cfg_side_width", "cfg_preview_limit", "cfg_archive_tz"}
)


def populate_config_panel(app: Any) -> None:
    prev_loading = bool(getattr(app, "_settings_config_loading", False))
    app._settings_config_loading = True
    try:
        sw = app.query_one("#cfg_pin_wip", Switch)
        sw.value = bool(app._table_pin_wip_top_enabled())

        width_select = app.query_one("#cfg_side_width", Select)
        try:
            width_select.value = app._table_side_width_pct()
        except WIDGET_API_ERRORS:
            pass

        preview_input = app.query_one("#cfg_preview_limit", Input)
        preview_input.value = str(app._preview_entries_limit())

        tz_select = app.query_one("#cfg_archive_tz", Select)
        cur_tz = str(app.ctx.archive_tz_name)
        presets = list(ARCHIVE_TZ_PRESETS)
        if cur_tz and cur_tz not in presets:
            presets = [cur_tz, *presets]
            tz_select.set_options([(tz, tz) for tz in presets])
        try:
            tz_select.value = cur_tz or presets[0]
        except WIDGET_API_ERRORS:
            pass
    except WIDGET_API_ERRORS:
        pass
    finally:
        app._settings_config_loading = prev_loading


def on_config_widget_changed(app: Any, event: Any) -> None:
    if getattr(app, "_settings_config_loading", False):
        return
    control = getattr(event, "control", None)
    wid = str(getattr(control, "id", "") or "")
    if wid not in CONFIG_WIDGET_IDS:
        return
    base_dir: Path = app.base_dir

    if wid == "cfg_pin_wip":
        app.table_behavior["pin_wip_top"] = bool(event.value)
        table_config_save(app, base_dir=base_dir)
        app._configure_table_columns()
        app._refresh_table()
        app._refresh_side()
        return

    if wid == "cfg_side_width":
        try:
            new_pct = int(event.value)
        except (TypeError, ValueError):
            return
        app.table_behavior["side_width_pct"] = new_pct
        table_config_save(app, base_dir=base_dir)
        app._sync_side_tab_visibility()
        app._refresh_side()
        return

    if wid == "cfg_preview_limit":
        raw = str(getattr(event, "value", "")).strip()
        try:
            n = int(raw)
        except (TypeError, ValueError):
            populate_config_panel(app)
            return
        clamped = max(PREVIEW_ENTRIES_LIMIT_MIN, min(PREVIEW_ENTRIES_LIMIT_MAX, n))
        app.table_behavior["preview_entries_limit"] = clamped
        table_config_save(app, base_dir=base_dir)
        if clamped != n:
            populate_config_panel(app)
        app._refresh_side()
        return

    if wid == "cfg_archive_tz":
        new_tz = str(event.value)
        if not new_tz or new_tz == str(app.ctx.archive_tz_name):
            return
        try:
            save_archive_timezone_name(base_dir, new_tz)
        except (OSError, TypeError, ValueError) as exc:
            app._show_runtime_error("save archive timezone", exc)
            return
        reload_global_config(app, base_dir=base_dir)
        return


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
        "open",
        "global",
    }:
        return False
    if app.side_settings_tab == "global":
        if event.key in {"space", "enter"}:
            edit_global_config_and_reload(app, base_dir=base_dir)
            return True
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


def edit_global_config_and_reload(app: Any, *, base_dir: Path) -> None:
    config_path = base_dir / HOMEBASE_DIR_NAME / GLOBAL_CONFIG_FILE_NAME
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.touch(exist_ok=True)
    except OSError as exc:
        app._show_runtime_error("prepare global config", exc)
        return

    try:
        app._open_editor_for_path(
            config_path,
            wait=True,
            on_done=lambda: reload_global_config(app, base_dir=base_dir),
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        app._show_runtime_error("open global config in editor", exc)
        return


def reload_global_config(app: Any, *, base_dir: Path) -> None:
    clear_global_config_cache(base_dir)

    try:
        runtime_builtins = dict(BUILTIN_ACTIONS)
        runtime_builtins.update(discover_tab_actions())
        runtime_cfg = runtime_init.load_runtime_config(
            base_dir,
            default_archive_tz_name=DEFAULT_ARCHIVE_TZ_NAME,
            load_property_defs=load_property_defs,
            load_wip_symbol_map=load_wip_symbol_map,
            load_saved_filter_queries=load_saved_filter_queries,
            load_suffixes=load_suffixes,
            load_file_view_exclude_patterns=load_file_view_exclude_patterns,
            load_actions=lambda bd: load_actions(bd, builtins=runtime_builtins),
            load_favorites=lambda bd, actions: load_favorites(bd, actions=actions),
            load_open_mode_config=load_open_mode_config,
            load_notes_config=load_notes_config,
            load_reconcile_config=load_reconcile_config,
            load_cache_profile_table=load_cache_profile_table,
            load_hook_specs=load_hook_specs,
            load_hook_refresh_config=load_hook_refresh_config,
            load_archive_timezone_name=load_archive_timezone_name,
        )
    except (OSError, TypeError, ValueError) as exc:
        app._show_runtime_error("reload global config", exc)
        return

    app.ctx = UIContext(
        base_dir=base_dir,
        archive_tz=runtime_cfg.archive_tz,
        archive_tz_name=runtime_cfg.archive_tz_name,
        property_defs=list(runtime_cfg.property_defs),
        wip_open_symbol_map=dict(runtime_cfg.wip_open_symbol_map),
        named_filters=dict(runtime_cfg.named_filters),
        saved_filter_queries=list(runtime_cfg.saved_filter_queries),
        suffixes=list(runtime_cfg.suffixes),
        file_view_exclude_patterns=list(runtime_cfg.file_view_exclude_patterns),
        actions=dict(runtime_cfg.actions),
        favorites=[dict(row) for row in runtime_cfg.favorites],
        open_mode_config=dict(runtime_cfg.open_mode_config),
        notes_config=dict(runtime_cfg.notes_config),
        reconcile_config={mode: dict(conf) for mode, conf in runtime_cfg.reconcile_config.items()},
        cache_profile_table={
            scope: {name: dict(profile) for name, profile in table.items()}
            for scope, table in runtime_cfg.cache_profile_table.items()
        },
        hook_specs=dict(runtime_cfg.hook_specs),
        hook_refresh_config=runtime_cfg.hook_refresh_config,
    )
    app.actions = dict(app.ctx.actions)
    app.custom_actions = [
        action for action in app.actions.values() if action.source != "builtin"
    ]
    bind_builder = getattr(app, "_favorites_from_ctx", None)
    if callable(bind_builder):
        app.custom_hotkeys = bind_builder()
    else:
        app.custom_hotkeys = list(getattr(app.ctx, "favorites", []))
    app.open_mode = dict(app.ctx.open_mode_config)
    app.notes_config = dict(app.ctx.notes_config)
    app.reconcile_config = {
        "active": dict(app.ctx.reconcile_config.get("active", {})),
        "archive": dict(app.ctx.reconcile_config.get("archive", {})),
    }
    app._reset_query_completion()
    app._mark_state_dirty()
    app._queue_query_apply()
    app._refresh_settings_table()
    app._refresh_side()
    app._set_runtime_status("global config reloaded", "info", ttl_s=5.0)


def global_config_status_text(app: Any, *, base_dir: Path) -> str:
    config_path = base_dir / HOMEBASE_DIR_NAME / GLOBAL_CONFIG_FILE_NAME
    exists = config_path.is_file()
    mtime_text = "-"
    size_text = "-"
    if exists:
        try:
            stat = config_path.stat()
            mtime_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
            size_text = str(max(0, int(stat.st_size)))
        except OSError:
            pass

    lines = [
        "[bold]Global Config[/]",
        f"[cyan]path[/]: {app._esc(config_path)}",
        f"[cyan]exists[/]: {'yes' if exists else 'no (created on first edit)'}",
        f"[cyan]modified[/]: {app._esc(mtime_text)}",
        f"[cyan]size bytes[/]: {app._esc(size_text)}",
        "",
        f"[cyan]archive timezone[/]: {app._esc(app.ctx.archive_tz_name)}",
        f"[cyan]open profile[/]: {app._esc(str(app.open_mode.get('profile', '')))}",
        f"[cyan]named filters[/]: {len(app.ctx.named_filters)}",
        f"[cyan]saved filters[/]: {len(app.ctx.saved_filter_queries)}",
        f"[cyan]suffixes[/]: {len(app.ctx.suffixes)}",
        f"[cyan]custom actions[/]: {len(app.custom_actions)}",
        f"[cyan]keys[/]: {len(app.ctx.keys)}",
        "",
        "[dim]Use the button below to edit config and auto-reload when editor exits.[/]",
    ]
    return "\n".join(lines)
