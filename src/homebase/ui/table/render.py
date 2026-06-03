from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from rich.text import Text
from textual.widgets import DataTable

from ...config.tag_rules import is_group_only, resolve_for_display
from ...core.constants import COLOR_PENDING_HEX, COLOR_WORKTREE_PARENT_HEX
from ...core.models import ProjectRow
from ...core.utils import WIDGET_API_ERRORS


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
        row.worktree_of,
    )


def _trunc_ellipsis(value: str, width: int) -> str:
    text = value.strip()
    if not text:
        return "-"
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def _hex_rgb(value: str) -> tuple[int, int, int] | None:
    text = str(value).strip()
    if len(text) != 7 or not text.startswith("#"):
        return None
    try:
        return (int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16))
    except ValueError:
        return None


def _mix_rgb(
    a: tuple[int, int, int], b: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    p = max(0.0, min(1.0, float(t)))
    return (
        int(round(a[0] + (b[0] - a[0]) * p)),
        int(round(a[1] + (b[1] - a[1]) * p)),
        int(round(a[2] + (b[2] - a[2]) * p)),
    )


def _rgb_hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def _resolve_date_rule(
    table_date_color_ranges: dict[str, dict[str, dict[str, object]]] | None,
    view_mode: str,
    col_id: str,
) -> dict[str, object]:
    ranges = table_date_color_ranges or {}
    if not isinstance(ranges, dict):
        return {}
    view_table = ranges.get(view_mode, {})
    all_table = ranges.get("all", {})
    rule = view_table.get(col_id, {}) if isinstance(view_table, dict) else {}
    if not rule and isinstance(all_table, dict):
        rule = all_table.get(col_id, {})
    if not isinstance(rule, dict):
        return {}
    return rule


def _parse_color_stops(stops_raw: object) -> list[tuple[float, tuple[int, int, int]]]:
    if not isinstance(stops_raw, list) or not stops_raw:
        return []
    stops: list[tuple[float, tuple[int, int, int]]] = []
    for stop in stops_raw:
        if not isinstance(stop, dict):
            continue
        try:
            days = max(0.0, float(stop.get("days", 0.0)))
        except (TypeError, ValueError):
            continue
        color = _hex_rgb(str(stop.get("color", "")).strip())
        if color is None:
            continue
        stops.append((days, color))
    stops.sort(key=lambda item: item[0])
    return stops


def _interpolate_stops(
    stops: list[tuple[float, tuple[int, int, int]]], age_days: float
) -> str:
    if age_days <= stops[0][0]:
        return _rgb_hex(stops[0][1])
    if age_days >= stops[-1][0]:
        return _rgb_hex(stops[-1][1])
    for idx in range(1, len(stops)):
        left_days, left_color = stops[idx - 1]
        right_days, right_color = stops[idx]
        if age_days <= right_days:
            span = max(0.0001, right_days - left_days)
            t = (age_days - left_days) / span
            return _rgb_hex(_mix_rgb(left_color, right_color, t))
    return _rgb_hex(stops[-1][1])


def _date_color_for(
    col_id: str,
    ts: int,
    *,
    view_mode: str,
    table_date_color_ranges: dict[str, dict[str, dict[str, object]]] | None,
    now_ts: int,
) -> str:
    if ts <= 0:
        return ""
    rule = _resolve_date_rule(table_date_color_ranges, view_mode, col_id)
    stops = _parse_color_stops(rule.get("stops", []))
    if not stops:
        return ""
    age_days = max(0.0, (now_ts - int(ts)) / 86400.0)
    return _interpolate_stops(stops, age_days)


def _tag_cell_parts(
    resolved: list[Any], budget: int, sep_len: int, suffix_len: int
) -> tuple[list[tuple[str, str]], int]:
    parts: list[tuple[str, str]] = []
    cur_len = 0
    i = 0
    while i < len(resolved):
        entry = resolved[i]
        display_len = len(entry.display)
        sep = sep_len if parts else 0
        remaining = len(resolved) - i - 1
        reserve = suffix_len if remaining > 0 else 0
        if cur_len + sep + display_len + reserve > budget:
            if parts and reserve == 0 and cur_len + sep + display_len <= budget:
                parts.append((entry.display, entry.style_spec))
                cur_len += sep + display_len
                i += 1
                continue
            break
        parts.append((entry.display, entry.style_spec))
        cur_len += sep + display_len
        i += 1
    return parts, len(resolved) - len(parts)


def _tag_cell(tags: list[str], width: int, *, base_dir: Path) -> Text:
    if not tags:
        return Text("-", style="dim")
    labels = [str(t).strip() for t in tags if str(t).strip()]
    # Group-only tags are virtual grouping nodes — hide them from the
    # visible cell. They still drive ``##tag`` filters.
    labels = [label for label in labels if not is_group_only(label, base_dir)]
    if not labels:
        return Text("-", style="dim")
    resolved = [resolve_for_display(label, base_dir) for label in labels]
    budget = max(6, int(width))
    suffix = "  ++"
    parts, hidden = _tag_cell_parts(resolved, budget, sep_len=2, suffix_len=len(suffix))
    if not parts:
        first = resolved[0]
        return Text(_trunc_ellipsis(first.display, budget), style=first.style_spec)
    out = Text()
    for j, (display, spec) in enumerate(parts):
        if j > 0:
            out.append("  ")
        out.append(display, style=spec)
    if hidden > 0:
        out.append(suffix, style="dim")
    return out


def _row_status_mark(
    row: ProjectRow,
    *,
    multi_selected: set[Path],
    cache_last_refresh_ts: int,
    cache_worker_running: bool,
    open_pane_count_by_project: dict[Path, int],
    open_pane_overflow_projects: set[Path],
    color_error_hex: str,
) -> Text:
    select_char = "*" if row.path in multi_selected else " "
    if row.stale:
        cache_char = "!"
    elif cache_last_refresh_ts <= 0:
        cache_char = "?"
    elif cache_worker_running:
        cache_char = "~"
    else:
        cache_char = " "
    count = open_pane_count_by_project.get(row.path, 0)
    open_char = str(min(9, count)) if count > 0 else " "
    out = Text(f"{select_char}{cache_char}{open_char} ")
    if row.path in open_pane_overflow_projects:
        out.stylize(color_error_hex, 2, 3)
    return out


def _col_sig(visible_cols: list[dict[str, object]]) -> tuple[tuple[object, ...], ...]:
    parts: list[tuple[object, ...]] = []
    for col in visible_cols:
        try:
            col_width = int(col.get("width", 12) or 12)
        except (TypeError, ValueError):
            col_width = 12
        cid = str(col.get("id", "")).strip()
        label = str(col.get("label", "")) if "label" in col else cid.upper()
        parts.append((cid, label, bool(col.get("enabled", True)), col_width))
    return tuple(parts)


def _compute_render_signature(
    app: Any, visible_cols: list[dict[str, object]], rows: list[ProjectRow]
) -> tuple[object, ...]:
    busy_frame_sig = app._busy_frame_index if app.git_refresh_paths else 0
    return (
        app.view_mode,
        _col_sig(visible_cols),
        tuple(_row_sig(row) for row in rows),
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


def _capture_prev_state(table: DataTable) -> tuple[int, int, int, int]:
    try:
        return (
            int(getattr(table, "scroll_x", 0) or 0),
            int(getattr(table, "scroll_y", 0) or 0),
            int(getattr(table, "row_count", 0) or 0),
            int(getattr(table, "cursor_row", 0) or 0),
        )
    except (AttributeError, TypeError, ValueError):
        return (0, 0, 0, 0)


def _compute_width_by_id(
    visible_cols: list[dict[str, object]], effective_widths: dict[str, int]
) -> dict[str, int]:
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
    return width_by_id


def _name_cell_style(
    row: ProjectRow, *, color_success_hex: str, color_archive_hex: str
) -> str:
    if row.packed and row.archived:
        return "dim"
    if row.archived and not row.wip:
        return color_archive_hex
    if row.wip:
        return color_success_hex
    return ""


def _git_cell(
    row: ProjectRow,
    app: Any,
    *,
    color_accent_hex: str,
    color_success_hex: str,
    color_warn_hex: str,
    color_interactive_hex: str,
    color_error_hex: str,
) -> Text:
    if row.branch in {"-", "?"}:
        return Text("-", style="dim")
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
    cell = Text(git_text, style=git_style)
    if row.worktree_of:
        cell.append(f"  ↪{row.worktree_of}", style=COLOR_WORKTREE_PARENT_HEX)
    return cell


def _restore_short(row: ProjectRow, base_dir: Path, restore_width: int) -> str:
    if row.restore_target is None:
        return "-"
    restore_rel: Any = row.restore_target
    try:
        restore_rel = row.restore_target.relative_to(base_dir)
    except ValueError:
        pass
    return _trunc_ellipsis(str(restore_rel), restore_width)


def _property_cell(
    properties: list[str],
    property_cell_cache: dict[tuple[str, ...], object],
    property_tokens_text: Callable[[list[str]], object],
) -> object:
    prop_key = tuple(properties)
    cached = property_cell_cache.get(prop_key)
    if cached is None:
        cached = property_tokens_text(properties)
        property_cell_cache[prop_key] = cached
    if isinstance(cached, Text):
        return cached.copy()
    return cached


def _apply_date_styles(
    row_cells: dict[str, object],
    row: ProjectRow,
    *,
    view_mode: str,
    table_date_color_ranges: dict[str, dict[str, dict[str, object]]] | None,
    now_ts: int,
) -> None:
    sources = {
        "created": int(row.created_ts),
        "modified": int(row.last_ts),
        "active": int(row.opened_ts),
        "archived_at": int(row.archived_ts),
    }
    for cid, ts in sources.items():
        style = _date_color_for(
            cid,
            ts,
            view_mode=view_mode,
            table_date_color_ranges=table_date_color_ranges,
            now_ts=now_ts,
        )
        if not style or cid not in row_cells:
            continue
        row_cells[cid] = Text(str(row_cells[cid]), style=style)


_PACKED_DIM_SKIP = frozenset({"mark", "name", "git", "properties", "size"})


def _apply_packed_dim(row_cells: dict[str, object]) -> None:
    for cid, cell in list(row_cells.items()):
        if cid in _PACKED_DIM_SKIP:
            continue
        if isinstance(cell, Text):
            cell.stylize("dim")
        else:
            row_cells[cid] = Text(str(cell), style="dim")


def _apply_pending_tag_highlight(row_cells: dict[str, object]) -> None:
    tag_cell = row_cells.get("tags")
    if isinstance(tag_cell, Text):
        tag_cell.stylize(COLOR_PENDING_HEX)
    else:
        row_cells["tags"] = Text(str(tag_cell or ""), style=COLOR_PENDING_HEX)


def _build_row_cells(
    row: ProjectRow,
    app: Any,
    *,
    wip_index: dict[Path, int],
    width_by_id: dict[str, int],
    base_dir: Path,
    table_width: int,
    restore_width: int,
    fmt_ymd: Callable[[int], str],
    fmt_size_human: Callable[[int], str],
    property_tokens_text: Callable[[list[str]], object],
    property_cell_cache: dict[tuple[str, ...], object],
    color_error_hex: str,
    color_success_hex: str,
    color_archive_hex: str,
    color_accent_hex: str,
    color_warn_hex: str,
    color_interactive_hex: str,
    view_mode: str,
    table_date_color_ranges: dict[str, dict[str, dict[str, object]]] | None,
    now_ts: int,
) -> dict[str, object]:
    mark = _row_status_mark(
        row,
        multi_selected=app.multi_selected,
        cache_last_refresh_ts=app.cache_last_refresh_ts,
        cache_worker_running=app.cache_worker_running,
        open_pane_count_by_project=app.open_pane_count_by_project,
        open_pane_overflow_projects=app.open_pane_overflow_projects,
        color_error_hex=color_error_hex,
    )
    idx = wip_index.get(row.path)
    display_name = f"{row.name} [{idx}]" if idx else row.name
    name_style = _name_cell_style(
        row,
        color_success_hex=color_success_hex,
        color_archive_hex=color_archive_hex,
    )
    name_cell = (
        Text(display_name, style=name_style) if name_style else Text(display_name)
    )
    git_cell = _git_cell(
        row,
        app,
        color_accent_hex=color_accent_hex,
        color_success_hex=color_success_hex,
        color_warn_hex=color_warn_hex,
        color_interactive_hex=color_interactive_hex,
        color_error_hex=color_error_hex,
    )
    archived_at = fmt_ymd(row.archived_ts) if row.archived_ts > 0 else "-"
    row_cells: dict[str, object] = {
        "mark": mark,
        "name": name_cell,
        "git": git_cell,
        "modified": row.last,
        "created": row.created,
        "active": fmt_ymd(row.opened_ts) if row.opened_ts > 0 else "-",
        "properties": _property_cell(
            row.properties, property_cell_cache, property_tokens_text
        ),
        "tags": _tag_cell(row.tags, width_by_id.get("tags", 24), base_dir=base_dir),
        "description": Text(
            _trunc_ellipsis(str(row.description), max(12, int(table_width * 0.22)))
        ),
        "size": fmt_size_human(row.size_bytes),
        "archived_at": archived_at,
        "original_name": _restore_short(row, base_dir, restore_width),
    }
    _apply_date_styles(
        row_cells,
        row,
        view_mode=view_mode,
        table_date_color_ranges=table_date_color_ranges,
        now_ts=now_ts,
    )
    if row.packed and row.archived:
        _apply_packed_dim(row_cells)
    if row.path in app.pending_tag_updates:
        _apply_pending_tag_highlight(row_cells)
    return row_cells


def _row_values(
    row_cells: dict[str, object], visible_cols: list[dict[str, object]]
) -> list[object]:
    values: list[object] = []
    for col in visible_cols:
        cid = str(col.get("id", "")).strip()
        if cid in row_cells:
            values.append(row_cells[cid])
    if not values:
        values = [row_cells.get("name", "")]
    return values


def _row_keys_match(
    table: DataTable, table_rows: list[tuple[str, list[object]]]
) -> bool:
    for idx, (row_key, _vals) in enumerate(table_rows):
        try:
            existing_key, _ = table.coordinate_to_cell_key((idx, 0))
            existing_key_text = str(getattr(existing_key, "value", existing_key))
        except WIDGET_API_ERRORS:
            return False
        if existing_key_text != row_key:
            return False
    return True


def _patch_cells_in_place(
    table: DataTable, table_rows: list[tuple[str, list[object]]]
) -> bool:
    for idx, (_row_key, vals) in enumerate(table_rows):
        for col_idx, value in enumerate(vals):
            try:
                table.update_cell_at((idx, col_idx), value)
            except WIDGET_API_ERRORS:
                return False
    return True


def _try_in_place_patch(
    app: Any,
    table: DataTable,
    table_rows: list[tuple[str, list[object]]],
    rows: list[ProjectRow],
    desired_fixed_rows: int,
) -> bool:
    try:
        current_row_count = int(getattr(table, "row_count", 0) or 0)
    except (AttributeError, TypeError, ValueError):
        return False
    if current_row_count != len(table_rows):
        return False
    if not _row_keys_match(table, table_rows):
        return False
    if not _patch_cells_in_place(table, table_rows):
        return False
    row_paths = {row.path for row in rows}
    app.multi_selected = {path for path in app.multi_selected if path in row_paths}
    try:
        table.fixed_rows = max(0, min(desired_fixed_rows, len(table_rows)))
    except WIDGET_API_ERRORS:
        pass
    app.call_after_refresh(app._clear_project_row_highlight_suspend)
    return True


def _find_index(rows: list[ProjectRow], target: Path | None, same: Callable) -> int:
    if target is None:
        return -1
    return next((i for i, row in enumerate(rows) if same(row.path, target)), -1)


def _resolve_cursor_index(
    app: Any, rows: list[ProjectRow], prev_cursor_row: int
) -> int:
    selected_idx = _find_index(rows, app.selected_path, app._same_path)
    if selected_idx >= 0:
        return selected_idx
    target = app._restore_target_path.get(app.view_mode)
    target_idx = _find_index(rows, target, app._same_path)
    if target_idx >= 0:
        app.selected_path = rows[target_idx].path
        app._view_selected_path[app.view_mode] = app.selected_path
        app._restore_target_path[app.view_mode] = app.selected_path
        return target_idx
    if app._restore_pending.get(app.view_mode, False):
        return min(max(0, app._state_cursor_row), len(rows) - 1)
    idx = min(max(0, prev_cursor_row), len(rows) - 1)
    app.selected_path = rows[idx].path
    return idx


_SCROLL_ERRORS = (
    LookupError,
    KeyError,
    IndexError,
    AttributeError,
    RuntimeError,
    ValueError,
    TypeError,
)


def _apply_cursor_and_scroll(
    app: Any,
    table: DataTable,
    rows: list[ProjectRow],
    *,
    prev_scroll_x: int,
    prev_scroll_y: int,
    prev_row_count: int,
    prev_cursor_row: int,
) -> None:
    if not rows:
        app.selected_path = None
        return
    idx = _resolve_cursor_index(app, rows, prev_cursor_row)
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
    except _SCROLL_ERRORS:
        pass
    if apply_saved_scroll:
        app._restore_apply_scroll[app.view_mode] = False


def _should_skip_rebuild(app: Any, render_sig: tuple[object, ...]) -> bool:
    return (
        app._table_render_signature == render_sig
        and not app._restore_pending.get(app.view_mode, False)
        and not app._restore_apply_scroll.get(app.view_mode, False)
    )


def _reset_fixed_rows(table: DataTable) -> None:
    # Leaving a stale ``fixed_rows`` count crashes Textual on the next
    # resize: ``_data_table.get_row_height`` is called with a ``None``
    # row key when ``fixed_rows`` is greater than the actual row count.
    try:
        table.fixed_rows = 0
    except WIDGET_API_ERRORS:
        pass


def _ensure_property_cache(app: Any, property_defs_signature: int) -> dict[tuple[str, ...], object]:
    if getattr(app, "_property_cell_cache_sig", -1) != property_defs_signature:
        app._property_cell_cache = {}
        app._property_cell_cache_sig = property_defs_signature
    return app._property_cell_cache


def _build_table_rows(
    app: Any,
    rows: list[ProjectRow],
    visible_cols: list[dict[str, object]],
    *,
    wip_index: dict[Path, int],
    width_by_id: dict[str, int],
    base_dir: Path,
    table_width: int,
    restore_width: int,
    fmt_ymd: Callable[[int], str],
    fmt_size_human: Callable[[int], str],
    property_tokens_text: Callable[[list[str]], object],
    property_cell_cache: dict[tuple[str, ...], object],
    color_error_hex: str,
    color_success_hex: str,
    color_archive_hex: str,
    color_accent_hex: str,
    color_warn_hex: str,
    color_interactive_hex: str,
    table_date_color_ranges: dict[str, dict[str, dict[str, object]]] | None,
    now_ts: int,
) -> list[tuple[str, list[object]]]:
    out: list[tuple[str, list[object]]] = []
    for row in rows:
        row_cells = _build_row_cells(
            row,
            app,
            wip_index=wip_index,
            width_by_id=width_by_id,
            base_dir=base_dir,
            table_width=table_width,
            restore_width=restore_width,
            fmt_ymd=fmt_ymd,
            fmt_size_human=fmt_size_human,
            property_tokens_text=property_tokens_text,
            property_cell_cache=property_cell_cache,
            color_error_hex=color_error_hex,
            color_success_hex=color_success_hex,
            color_archive_hex=color_archive_hex,
            color_accent_hex=color_accent_hex,
            color_warn_hex=color_warn_hex,
            color_interactive_hex=color_interactive_hex,
            view_mode=app.view_mode,
            table_date_color_ranges=table_date_color_ranges,
            now_ts=now_ts,
        )
        out.append((str(row.path), _row_values(row_cells, visible_cols)))
    return out


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
    property_tokens_text: Callable[[list[str]], object],
    property_defs_signature: int = -1,
    table_date_color_ranges: dict[str, dict[str, dict[str, object]]] | None = None,
) -> None:
    table = app.query_one(widget_projects, DataTable)
    rows = app._current_rows()
    visible_cols = app._table_visible_columns_for_view(app.view_mode)
    if not visible_cols:
        visible_cols = [{"id": "name"}]

    render_sig = _compute_render_signature(app, visible_cols, rows)
    if _should_skip_rebuild(app, render_sig):
        return
    app._table_render_signature = render_sig

    prev_scroll_x, prev_scroll_y, prev_row_count, prev_cursor_row = _capture_prev_state(
        table
    )
    app._suspend_project_row_highlight = True

    desired_fixed_rows = 0
    if app.view_mode == mode_active and app._table_pin_wip_top_enabled():
        desired_fixed_rows = sum(1 for row in rows if row.wip)
    _reset_fixed_rows(table)

    effective_widths = dict(
        getattr(app, "_visible_column_effective_width_by_id", {}) or {}
    )
    width_by_id = _compute_width_by_id(visible_cols, effective_widths)
    wip_index: dict[Path, int] = {
        row.path: i for i, row in enumerate(app._wip_rows_sorted()[:9], start=1)
    }
    table_width = max(80, table.size.width)
    restore_width = max(14, int(table_width * 0.16))
    property_cell_cache = _ensure_property_cache(app, property_defs_signature)
    now_ts = int(time.time())

    table_rows = _build_table_rows(
        app,
        rows,
        visible_cols,
        wip_index=wip_index,
        width_by_id=width_by_id,
        base_dir=base_dir,
        table_width=table_width,
        restore_width=restore_width,
        fmt_ymd=fmt_ymd,
        fmt_size_human=fmt_size_human,
        property_tokens_text=property_tokens_text,
        property_cell_cache=property_cell_cache,
        color_error_hex=color_error_hex,
        color_success_hex=color_success_hex,
        color_archive_hex=color_archive_hex,
        color_accent_hex=color_accent_hex,
        color_warn_hex=color_warn_hex,
        color_interactive_hex=color_interactive_hex,
        table_date_color_ranges=table_date_color_ranges,
        now_ts=now_ts,
    )

    can_patch_in_place = not app._restore_pending.get(
        app.view_mode, False
    ) and not app._restore_apply_scroll.get(app.view_mode, False)
    if can_patch_in_place and _try_in_place_patch(
        app, table, table_rows, rows, desired_fixed_rows
    ):
        return

    table.clear(columns=False)
    for row_key, values in table_rows:
        table.add_row(*values, key=row_key)
    try:
        table.fixed_rows = max(0, min(desired_fixed_rows, len(table_rows)))
    except WIDGET_API_ERRORS:
        pass

    _apply_cursor_and_scroll(
        app,
        table,
        rows,
        prev_scroll_x=prev_scroll_x,
        prev_scroll_y=prev_scroll_y,
        prev_row_count=prev_row_count,
        prev_cursor_row=prev_cursor_row,
    )
    row_paths = {row.path for row in rows}
    app.multi_selected = {path for path in app.multi_selected if path in row_paths}
    app.call_after_refresh(app._clear_project_row_highlight_suspend)
