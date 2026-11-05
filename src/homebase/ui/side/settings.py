from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rich.text import Text
from textual.events import Key
from textual.widgets import DataTable, Static

from ...config.hooks import load_hook_refresh_config, load_hook_specs
from ...config.prefs import (
    load_actions,
    load_archive_timezone_name,
    load_cache_profile_table,
    load_favorites,
    load_file_view_exclude_patterns,
    load_notes_config,
    load_open_mode_config,
    load_raycast_config,
    load_reconcile_config,
    load_saved_filter_queries,
    load_suffixes,
    load_wip_symbol_map,
    save_table_columns_config,
)
from ...config.property_defs import load_property_defs
from ...config.store import clear_global_config_cache
from ...core import runtime_init
from ...core.constants import (
    BUILTIN_ACTIONS,
    DEFAULT_ARCHIVE_TZ_NAME,
    GLOBAL_CONFIG_FILE_NAME,
    HOMEBASE_DIR_NAME,
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


def settings_general_info_text(app: Any, *, base_dir: Path) -> str:
    config_path = base_dir / HOMEBASE_DIR_NAME / GLOBAL_CONFIG_FILE_NAME
    exists = config_path.is_file()
    mtime_text = "-"
    if exists:
        try:
            stat = config_path.stat()
            mtime_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
        except OSError:
            pass
    custom_hotkeys = getattr(app, "custom_hotkeys", getattr(app.ctx, "favorites", []))
    lines = [
        "[bold]Global config[/]",
        f"[cyan]path[/]: {app._esc(config_path)}",
        f"[cyan]exists[/]: {'yes' if exists else 'no (created on first edit)'}",
        f"[cyan]modified[/]: {app._esc(mtime_text)}",
        "",
        f"[cyan]archive timezone[/]: {app._esc(app.ctx.archive_tz_name)}",
        f"[cyan]open profile[/]: {app._esc(str(app.open_mode.get('profile', '')))}",
        f"[cyan]named filters[/]: {len(app.ctx.named_filters)}",
        f"[cyan]saved filters[/]: {len(app.ctx.saved_filter_queries)}",
        f"[cyan]suffixes[/]: {len(app.ctx.suffixes)}",
        f"[cyan]custom actions[/]: {len(app.custom_actions)}",
        f"[cyan]key bindings[/]: {len(custom_hotkeys)}",
    ]
    return "\n".join(lines)


def refresh_settings_table(app: Any) -> None:
    table = app.query_one("#side_settings_table", DataTable)
    notes_widget = app.query_one("#side_settings_notes", Static)
    table.clear(columns=True)
    try:
        table.show_horizontal_scrollbar = False
    except WIDGET_API_ERRORS:
        pass
    notes_widget.update("")
    _refresh_table_columns(app, table, notes_widget)


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


_SETTINGS_TABLE_KEY_ACTIONS: dict[str, Callable[[Any, Path], None]] = {
    "space": lambda app, base_dir: table_settings_toggle_enabled(app, base_dir=base_dir),
    "left": lambda app, base_dir: table_settings_reorder(app, -1, base_dir=base_dir),
    "right": lambda app, base_dir: table_settings_reorder(app, 1, base_dir=base_dir),
    "minus": lambda app, base_dir: table_settings_adjust_width(app, -1, base_dir=base_dir),
    "plus": lambda app, base_dir: table_settings_adjust_width(app, 1, base_dir=base_dir),
    "equals": lambda app, base_dir: table_settings_adjust_width(app, 1, base_dir=base_dir),
}


def handle_settings_table_key(app: Any, event: Key, *, base_dir: Path) -> bool:
    if app.side_main_tab != "settings" or app.side_settings_tab != "table":
        return False
    current_columns = app._table_columns_for_view(app.view_mode)
    if not current_columns:
        return False
    if event.key in {"tab", "shift+tab", "backtab"}:
        step = -1 if event.key in {"shift+tab", "backtab"} else 1
        app.table_settings_index = (app.table_settings_index + step) % len(current_columns)
        app._refresh_side()
        return True
    action = _SETTINGS_TABLE_KEY_ACTIONS.get(event.key)
    if action is None:
        return False
    action(app, base_dir)
    return True


def open_config_editor_modal(app: Any, *, base_dir: Path) -> None:
    import shutil
    import sys

    from ...config.store import load_global_config_dict, save_global_config_dict
    from ...core.config_editor import ConfigEditorScreen
    from ...core.config_presets import ConfigEnv, build_presets

    env = ConfigEnv(
        platform=sys.platform,
        has_git=bool(shutil.which("git")),
        has_tmux=bool(shutil.which("tmux")),
        shell=Path(os.environ.get("SHELL", "")).name,  # nosec B604 - dataclass field, not a subprocess shell
    )
    presets = build_presets(env)
    current = dict(load_global_config_dict(base_dir))
    applied = False

    def _on_apply(desired: dict[str, Any]) -> None:
        nonlocal applied
        try:
            save_global_config_dict(base_dir, desired)
        except (OSError, TypeError, ValueError) as exc:
            app._show_runtime_error("save global config", exc)
            return
        applied = True

    def _on_close(_result: Any) -> None:
        # Only reload when an apply actually wrote the file; a peek-and-escape
        # must not trigger a full reload or a misleading status toast.
        if applied:
            reload_global_config(app, base_dir=base_dir)

    app.push_screen(
        ConfigEditorScreen(presets, current, _on_apply, env=env),
        _on_close,
    )


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
            load_raycast_config=load_raycast_config,
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
