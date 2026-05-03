from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from rich.text import Text
from textual.widgets import DataTable

from ...core.constants import COLOR_PENDING_HEX
from ...core.models import ProjectRow
from ...core.utils import WIDGET_API_ERRORS


def refresh_table(
    app: Any,
    *,
    widget_projects: str,
    mode_active: str,
    base_dir: Path,
    color_error_hex: str,
    color_success_hex: str,
    color_archive_hex: str,
    color_accent_hex: str,
    color_warn_hex: str,
    color_interactive_hex: str,
    fmt_ymd: Callable[[int], str],
    fmt_size_human: Callable[[int], str],
    property_tokens_text: Callable[[list[str]], str],
) -> None:
    table = app.query_one(widget_projects, DataTable)
    prev_scroll_x = 0
    prev_scroll_y = 0
    prev_row_count = 0
    try:
        prev_scroll_x = int(getattr(table, "scroll_x", 0) or 0)
        prev_scroll_y = int(getattr(table, "scroll_y", 0) or 0)
        prev_row_count = int(getattr(table, "row_count", 0) or 0)
    except (AttributeError, TypeError, ValueError):
        prev_scroll_x = 0
        prev_scroll_y = 0
        prev_row_count = 0

    app._suspend_project_row_highlight = True
    table.clear(columns=False)
    rows = app._current_rows()

    fixed_rows = 0
    if app.view_mode == mode_active and app._table_pin_wip_top_enabled():
        fixed_rows = sum(1 for row in rows if row.wip)
    try:
        table.fixed_rows = max(0, fixed_rows)
    except WIDGET_API_ERRORS:
        pass

    visible_cols = app._table_visible_columns_for_view(app.view_mode)
    if not visible_cols:
        visible_cols = [{"id": "name"}]

    wip_index: dict[Path, int] = {
        row.path: i for i, row in enumerate(app._wip_rows_sorted()[:9], start=1)
    }
    table_width = max(80, table.size.width)
    is_active_view = app.view_mode == "active"
    tags_width = max(40, int(table_width * (0.36 if is_active_view else 0.30)))
    restore_width = max(14, int(table_width * 0.16))
    property_cell_cache: dict[tuple[str, ...], object] = {}

    def trunc_ellipsis(value: str, width: int) -> str:
        text = value.strip()
        if not text:
            return "-"
        if len(text) <= width:
            return text
        if width <= 3:
            return text[:width]
        return text[: width - 3] + "..."

    def row_status_mark(row: ProjectRow) -> Text:
        select_char = "*" if row.path in app.multi_selected else " "
        if row.stale:
            cache_char = "!"
        elif app.cache_last_refresh_ts <= 0:
            cache_char = "?"
        elif app.cache_worker_running:
            cache_char = "~"
        else:
            cache_char = " "
        count = app.open_pane_count_by_project.get(row.path, 0)
        open_char = str(min(9, count)) if count > 0 else " "
        out = Text(f"{select_char}{cache_char}{open_char} ")
        if row.path in app.open_pane_overflow_projects:
            out.stylize(color_error_hex, 2, 3)
        return out

    for row in rows:
        mark = row_status_mark(row)
        idx = wip_index.get(row.path)
        display_name = f"{row.name} [{idx}]" if idx else row.name

        name_style = ""
        if row.wip:
            name_style = color_success_hex
        if row.archived and not row.wip:
            name_style = color_archive_hex
        if row.packed and row.archived:
            name_style = "dim"
        name_cell = Text(display_name, style=name_style) if name_style else Text(display_name)

        if row.branch in {"-", "?"}:
            git_cell = Text("-", style="dim")
        else:
            dirty_part = row.dirty or ""
            if row.path in app.git_refresh_paths:
                dirty_part = app._busy_frames[app._busy_frame_index]
            git_text = f"{row.branch}{dirty_part}"
            if row.path in app.git_refresh_paths:
                git_style = color_accent_hex
            elif dirty_part == "":
                git_style = color_success_hex
            elif dirty_part == "*":
                git_style = color_warn_hex
            elif dirty_part == "~":
                git_style = color_interactive_hex
            else:
                git_style = color_error_hex
            if row.stale:
                git_style = "dim"
            git_cell = Text(git_text, style=git_style)

        archived_at = "-"
        restore_short = "-"
        if row.archived_ts > 0:
            archived_at = fmt_ymd(row.archived_ts)
        if row.restore_target is not None:
            restore_rel = row.restore_target
            try:
                restore_rel = row.restore_target.relative_to(base_dir)
            except ValueError:
                pass
            restore_short = trunc_ellipsis(str(restore_rel), restore_width)

        prop_key = tuple(row.properties)
        prop_cell = property_cell_cache.get(prop_key)
        if prop_cell is None:
            prop_cell = property_tokens_text(row.properties)
            property_cell_cache[prop_key] = prop_cell
        elif isinstance(prop_cell, Text):
            prop_cell = prop_cell.copy()

        row_cells: dict[str, object] = {
            "mark": mark,
            "name": name_cell,
            "git": git_cell,
            "last_modified": row.last,
            "created": row.created,
            "last_opened": fmt_ymd(row.opened_ts) if row.opened_ts > 0 else "-",
            "properties": prop_cell,
            "tags": Text(trunc_ellipsis(",".join(row.tags), tags_width)),
            "description": Text(
                trunc_ellipsis(str(row.description), max(12, int(table_width * 0.22)))
            ),
            "size": fmt_size_human(row.size_bytes),
            "archived_at": archived_at,
            "restore_to": restore_short,
        }

        if row.packed and row.archived:
            for cid, cell in list(row_cells.items()):
                if cid in {"mark", "name", "git", "properties", "size"}:
                    continue
                if isinstance(cell, Text):
                    cell.stylize("dim")
                else:
                    row_cells[cid] = Text(str(cell), style="dim")

        if row.path in app.pending_tag_updates:
            tag_cell = row_cells.get("tags")
            if isinstance(tag_cell, Text):
                tag_cell.stylize(COLOR_PENDING_HEX)
            else:
                row_cells["tags"] = Text(str(tag_cell or ""), style=COLOR_PENDING_HEX)

        values: list[object] = []
        for col in visible_cols:
            cid = str(col.get("id", "")).strip()
            if cid not in row_cells:
                continue
            values.append(row_cells[cid])
        if not values:
            values = [name_cell]
        table.add_row(*values, key=str(row.path))

    if rows:
        first = rows[0].path
        selected_idx = (
            next(
                (i for i, row in enumerate(rows) if app._same_path(row.path, app.selected_path)),
                -1,
            )
            if app.selected_path is not None
            else -1
        )
        idx = selected_idx
        if idx < 0:
            target = app._restore_target_path.get(app.view_mode)
            target_idx = (
                next(
                    (i for i, row in enumerate(rows) if app._same_path(row.path, target)),
                    -1,
                )
                if target is not None
                else -1
            )
            if target_idx >= 0:
                idx = target_idx
                app.selected_path = rows[idx].path
                app._view_selected_path[app.view_mode] = app.selected_path
                app._restore_target_path[app.view_mode] = app.selected_path
            elif app._restore_pending.get(app.view_mode, False):
                idx = min(max(0, app._state_cursor_row), len(rows) - 1)
            else:
                app.selected_path = first
                idx = 0

        table.cursor_coordinate = (idx, 0)
        apply_saved_scroll = bool(
            app._restore_pending.get(app.view_mode, False)
            or app._restore_apply_scroll.get(app.view_mode, False)
            or prev_row_count <= 0
        )
        target_scroll_y = max(0, prev_scroll_y)
        if apply_saved_scroll:
            saved_offset = max(0, int(app._view_row_offset.get(app.view_mode, 0) or 0))
            target_scroll_y = max(0, idx - saved_offset)
        try:
            table.scroll_to(x=max(0, prev_scroll_x), y=target_scroll_y, animate=False)
        except (
            LookupError,
            KeyError,
            IndexError,
            AttributeError,
            RuntimeError,
            ValueError,
            TypeError,
        ):
            pass
        if apply_saved_scroll:
            app._restore_apply_scroll[app.view_mode] = False
    else:
        app.selected_path = None

    row_paths = {row.path for row in rows}
    app.multi_selected = {path for path in app.multi_selected if path in row_paths}
    app.call_after_refresh(app._clear_project_row_highlight_suspend)
