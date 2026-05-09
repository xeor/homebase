from __future__ import annotations

import colorsys
import functools
import hashlib
from pathlib import Path
from typing import Any, Callable

from rich.text import Text
from textual.widgets import DataTable

from ...core.constants import COLOR_PENDING_HEX
from ...core.models import ProjectRow
from ...core.utils import WIDGET_API_ERRORS


@functools.lru_cache(maxsize=4096)
def _tag_color(tag: str) -> str:
    digest = hashlib.sha1(tag.encode("utf-8", errors="ignore")).digest()
    hue = int.from_bytes(digest[:2], "big") / 65535.0
    sat = 0.32
    val = 0.95
    r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


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
    property_defs_signature: int = -1,
) -> None:
    table = app.query_one(widget_projects, DataTable)
    rows = app._current_rows()
    visible_cols = app._table_visible_columns_for_view(app.view_mode)
    if not visible_cols:
        visible_cols = [{"id": "name"}]

    def _row_sig(row: ProjectRow) -> tuple[object, ...]:
        return (
            str(row.path),
            row.name,
            row.branch,
            row.dirty,
            row.last,
            row.created,
            row.opened_ts,
            row.size_bytes,
            row.archived,
            row.archived_ts,
            str(row.restore_target) if row.restore_target is not None else "",
            row.wip,
            row.stale,
            row.packed,
            row.description,
            tuple(row.tags),
            tuple(row.properties),
        )

    col_sig_parts: list[tuple[object, ...]] = []
    for col in visible_cols:
        try:
            col_width = int(col.get("width", 12) or 12)
        except (TypeError, ValueError):
            col_width = 12
        col_sig_parts.append(
            (
                str(col.get("id", "")).strip(),
                str(col.get("label", "")),
                bool(col.get("enabled", True)),
                col_width,
            )
        )
    col_sig = tuple(col_sig_parts)
    row_sig = tuple(_row_sig(row) for row in rows)
    busy_frame_sig = app._busy_frame_index if app.git_refresh_paths else 0
    render_sig = (
        app.view_mode,
        col_sig,
        row_sig,
        tuple(sorted(str(path) for path in app.multi_selected)),
        tuple(sorted(str(path) for path in app.pending_tag_updates)),
        tuple(sorted(str(path) for path in app.git_refresh_paths)),
        tuple(
            sorted(
                (str(path), int(count))
                for path, count in app.open_pane_count_by_project.items()
                if count > 0
            )
        ),
        tuple(sorted(str(path) for path in app.open_pane_overflow_projects)),
        busy_frame_sig,
    )
    prev_sig = app._table_render_signature_by_view.get(app.view_mode)
    if (
        prev_sig == render_sig
        and not app._restore_pending.get(app.view_mode, False)
        and not app._restore_apply_scroll.get(app.view_mode, False)
    ):
        return
    app._table_render_signature_by_view[app.view_mode] = render_sig

    prev_scroll_x = 0
    prev_scroll_y = 0
    prev_row_count = 0
    prev_cursor_row = 0
    try:
        prev_scroll_x = int(getattr(table, "scroll_x", 0) or 0)
        prev_scroll_y = int(getattr(table, "scroll_y", 0) or 0)
        prev_row_count = int(getattr(table, "row_count", 0) or 0)
        prev_cursor_row = int(getattr(table, "cursor_row", 0) or 0)
    except (AttributeError, TypeError, ValueError):
        prev_scroll_x = 0
        prev_scroll_y = 0
        prev_row_count = 0
        prev_cursor_row = 0

    app._suspend_project_row_highlight = True

    fixed_rows = 0
    if app.view_mode == mode_active and app._table_pin_wip_top_enabled():
        fixed_rows = sum(1 for row in rows if row.wip)
    try:
        table.fixed_rows = max(0, fixed_rows)
    except WIDGET_API_ERRORS:
        pass

    effective_widths = dict(getattr(app, "_visible_column_effective_width_by_id", {}) or {})
    width_by_id: dict[str, int] = {}
    for col in visible_cols:
        cid = str(col.get("id", "")).strip()
        try:
            width = int(col.get("width", 12))
        except (TypeError, ValueError):
            width = 12
        configured = max(4, min(80, width))
        effective = int(effective_widths.get(cid, 0) or 0)
        width_by_id[cid] = max(configured, effective)

    wip_index: dict[Path, int] = {
        row.path: i for i, row in enumerate(app._wip_rows_sorted()[:9], start=1)
    }
    table_width = max(80, table.size.width)
    restore_width = max(14, int(table_width * 0.16))
    if getattr(app, "_property_cell_cache_sig", -1) != property_defs_signature:
        app._property_cell_cache = {}
        app._property_cell_cache_sig = property_defs_signature
    property_cell_cache: dict[tuple[str, ...], object] = app._property_cell_cache

    def trunc_ellipsis(value: str, width: int) -> str:
        text = value.strip()
        if not text:
            return "-"
        if len(text) <= width:
            return text
        if width <= 3:
            return text[:width]
        return text[: width - 3] + "..."

    def _tag_cell(tags: list[str], width: int) -> Text:
        if not tags:
            return Text("-", style="dim")
        labels = [str(t).strip() for t in tags]
        labels = [label for label in labels if label]
        if not labels:
            return Text("-", style="dim")
        budget = max(6, int(width))
        sep_len = 2
        suffix = "  ++"
        suffix_len = len(suffix)
        parts: list[str] = []
        cur_len = 0
        i = 0
        while i < len(labels):
            label = labels[i]
            sep = sep_len if parts else 0
            remaining = len(labels) - i - 1
            reserve = suffix_len if remaining > 0 else 0
            if cur_len + sep + len(label) + reserve > budget:
                if parts and reserve == 0 and cur_len + sep + len(label) <= budget:
                    parts.append(label)
                    cur_len += sep + len(label)
                    i += 1
                    continue
                break
            parts.append(label)
            cur_len += sep + len(label)
            i += 1
        hidden = len(labels) - len(parts)
        if not parts:
            return Text(trunc_ellipsis(labels[0], budget), style=_tag_color(labels[0]))
        out = Text()
        for j, label in enumerate(parts):
            if j > 0:
                out.append("  ")
            out.append(label, style=_tag_color(label))
        if hidden > 0:
            out.append(suffix, style="dim")
        return out

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

    table_rows: list[tuple[str, list[object]]] = []
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
        cached_prop_cell = property_cell_cache.get(prop_key)
        if cached_prop_cell is None:
            cached_prop_cell = property_tokens_text(row.properties)
            property_cell_cache[prop_key] = cached_prop_cell
        if isinstance(cached_prop_cell, Text):
            prop_cell = cached_prop_cell.copy()
        else:
            prop_cell = cached_prop_cell

        row_cells: dict[str, object] = {
            "mark": mark,
            "name": name_cell,
            "git": git_cell,
            "last_modified": row.last,
            "created": row.created,
            "last_opened": fmt_ymd(row.opened_ts) if row.opened_ts > 0 else "-",
            "properties": prop_cell,
            "tags": _tag_cell(row.tags, width_by_id.get("tags", 24)),
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
        table_rows.append((str(row.path), values))

    can_patch_in_place = (
        not app._restore_pending.get(app.view_mode, False)
        and not app._restore_apply_scroll.get(app.view_mode, False)
    )
    if can_patch_in_place:
        try:
            current_row_count = int(getattr(table, "row_count", 0) or 0)
        except (AttributeError, TypeError, ValueError):
            current_row_count = -1
        if current_row_count == len(table_rows):
            same_keys = True
            for idx, (row_key, _vals) in enumerate(table_rows):
                try:
                    existing_key, _ = table.coordinate_to_cell_key((idx, 0))
                    existing_key_text = str(getattr(existing_key, "value", existing_key))
                except WIDGET_API_ERRORS:
                    same_keys = False
                    break
                if existing_key_text != row_key:
                    same_keys = False
                    break
            if same_keys:
                for idx, (_row_key, vals) in enumerate(table_rows):
                    for col_idx, value in enumerate(vals):
                        try:
                            table.update_cell_at((idx, col_idx), value)
                        except WIDGET_API_ERRORS:
                            same_keys = False
                            break
                    if not same_keys:
                        break
                if same_keys:
                    row_paths = {row.path for row in rows}
                    app.multi_selected = {path for path in app.multi_selected if path in row_paths}
                    app.call_after_refresh(app._clear_project_row_highlight_suspend)
                    return

    table.clear(columns=False)
    for row_key, values in table_rows:
        table.add_row(*values, key=row_key)

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
                idx = min(max(0, prev_cursor_row), len(rows) - 1)
                app.selected_path = rows[idx].path if rows else first

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
