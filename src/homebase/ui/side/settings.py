from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from rich.text import Text
from textual.events import Key
from textual.widgets import DataTable, Static

from ...config import workspace as workspace_settings
from ...config.prefs import (
    load_archive_timezone_name,
    load_cache_profile_table,
    load_custom_actions,
    load_custom_hotkeys,
    load_file_view_exclude_patterns,
    load_notes_config,
    load_open_mode_config,
    load_reconcile_config,
    load_saved_filter_queries,
    load_suffixes,
    load_wip_symbol_map,
    save_open_mode_config,
    save_table_behavior_config,
    save_table_columns_config,
)
from ...config.property_defs import load_property_defs
from ...config.store import clear_global_config_cache, load_global_config_dict
from ...core import runtime_init
from ...core.constants import (
    BUILTIN_ACTIONS,
    DEFAULT_ARCHIVE_TZ_NAME,
    GLOBAL_CONFIG_FILE_NAME,
    HOMEBASE_DIR_NAME,
    OPEN_MODE_CONFIG,
    OPEN_MODE_PROFILES,
    TABLE_SIDE_WIDTH_PRESETS,
)
from ...core.utils import WIDGET_API_ERRORS
from ..context import UIContext


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

    if app.side_settings_tab == "global":
        try:
            notes_widget.styles.height = 15
        except WIDGET_API_ERRORS:
            pass
        table.add_column("", width=3)
        table.add_column("ACTION", width=54)
        table.add_row(Text("*"), "Edit global config in $EDITOR", key="0")
        try:
            table.cursor_coordinate = (0, 0)
        except WIDGET_API_ERRORS:
            pass
        notes_widget.update(
            "enter/space opens .homebase/config.yaml in $EDITOR\n"
            "when editor exits, runtime config is reloaded"
        )
        return

    table.add_column("", width=3)
    table.add_column("COLUMN", width=18)
    table.add_column("WIDTH", width=14)
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

    enabled_cols = [c for c in current_columns if bool(c.get("enabled", True))]
    last_enabled_id = str(enabled_cols[-1].get("id", "")).strip() if enabled_cols else ""
    effective_widths = dict(getattr(app, "_visible_column_effective_width_by_id", {}) or {})

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
        if enabled and cid == last_enabled_id and effective > 0 and effective != width:
            width_text = f"{width} ({effective})"
        table.add_row(Text("[x]" if enabled else "[ ]"), cid_short, width_text, key=str(i))
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
    app._sync_side_tab_visibility()
    app._configure_table_columns()
    app._refresh_table()
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

    def _load_actions(base_path: Path, custom_actions: list[dict[str, str]]) -> dict[str, object]:
        data = load_global_config_dict(base_path)
        user_actions = data.get("actions", {}) if isinstance(data, dict) else {}
        if not isinstance(user_actions, dict):
            user_actions = {}
        return workspace_settings.merge_actions(BUILTIN_ACTIONS, user_actions, custom_actions)

    try:
        runtime_cfg = runtime_init.load_runtime_config(
            base_dir,
            default_archive_tz_name=DEFAULT_ARCHIVE_TZ_NAME,
            load_property_defs=load_property_defs,
            load_wip_symbol_map=load_wip_symbol_map,
            load_saved_filter_queries=load_saved_filter_queries,
            load_suffixes=load_suffixes,
            load_file_view_exclude_patterns=load_file_view_exclude_patterns,
            load_custom_actions=load_custom_actions,
            load_custom_hotkeys=load_custom_hotkeys,
            load_actions=_load_actions,
            load_open_mode_config=load_open_mode_config,
            load_notes_config=load_notes_config,
            load_reconcile_config=load_reconcile_config,
            load_cache_profile_table=load_cache_profile_table,
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
        custom_actions=list(runtime_cfg.custom_actions),
        custom_hotkeys=list(runtime_cfg.custom_hotkeys),
        actions=dict(runtime_cfg.actions),
        open_mode_config=dict(runtime_cfg.open_mode_config),
        notes_config=dict(runtime_cfg.notes_config),
        reconcile_config={mode: dict(conf) for mode, conf in runtime_cfg.reconcile_config.items()},
        cache_profile_table={
            scope: {name: dict(profile) for name, profile in table.items()}
            for scope, table in runtime_cfg.cache_profile_table.items()
        },
    )
    app.actions = dict(app.ctx.actions)
    app.custom_actions = [
        action for action in app.actions.values() if action.source != "builtin"
    ]
    app.custom_hotkeys = list(app.ctx.custom_hotkeys)
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
        f"[cyan]custom hotkeys[/]: {len(app.custom_hotkeys)}",
        "",
        "[dim]Use the button below to edit config and auto-reload when editor exits.[/]",
    ]
    return "\n".join(lines)
