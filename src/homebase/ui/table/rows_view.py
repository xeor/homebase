from __future__ import annotations

from typing import Any

from textual.widgets import DataTable

from ...core.models import ProjectRow
from ...workspace.rows import sort_rows


def all_tags(app: Any) -> list[str]:
    rows = app.active_rows if app.view_mode == "active" else app.archived_rows
    tags: set[str] = set()
    for row in rows:
        tags.update(row.tags)
    return sorted(tags)


def current_rows(app: Any, *, mode_active: str) -> list[ProjectRow]:
    if (
        app._rows_cache_token == app._rows_state_token
        and app._rows_cache_view == app.view_mode
        and app._rows_cache_sort == app.sort_mode
        and app._rows_cache_query == app.query
    ):
        return app._rows_cache

    source_rows = app.active_rows if app.view_mode == mode_active else app.archived_rows
    sorted_rows = sort_rows(source_rows, app.sort_mode)

    out: list[ProjectRow] = []
    query_expr_mode, _resolved, _resolve_err, query_pred, _query_err = app._query_eval(
        app.query
    )
    if query_expr_mode:
        for row in sorted_rows:
            if query_pred(row):
                out.append(row)
    else:
        q_lower = app.query.strip().lower()
        if not q_lower:
            out = list(sorted_rows)
        else:
            for row in sorted_rows:
                if app._match_query_lower(row, q_lower):
                    out.append(row)

    if app.view_mode == mode_active and app._table_pin_wip_top_enabled():
        wip_rows = [row for row in out if row.wip]
        rest_rows = [row for row in out if not row.wip]
        out = wip_rows + rest_rows

    app._rows_cache = out
    app._rows_index_by_path = {row.path: i for i, row in enumerate(out)}
    app._rows_cache_token = app._rows_state_token
    app._rows_cache_view = app.view_mode
    app._rows_cache_sort = app.sort_mode
    app._rows_cache_query = app.query
    app.query_last_rows_count = len(out)
    return out


def selected_row(app: Any) -> ProjectRow | None:
    if not app.selected_path:
        return None
    rows = app._current_rows()
    idx = app._rows_index_by_path.get(app.selected_path)
    if idx is not None and 0 <= idx < len(rows):
        return rows[idx]
    for i, row in enumerate(rows):
        if app._same_path(row.path, app.selected_path):
            app._rows_index_by_path[row.path] = i
            return row
    return None


def move_selection(app: Any, delta: int, *, widget_projects: str) -> ProjectRow | None:
    rows = app._current_rows()
    if not rows:
        return None
    idx = 0
    if app.selected_path is not None:
        idx = next(
            (i for i, row in enumerate(rows) if app._same_path(row.path, app.selected_path)),
            0,
        )
    nxt = max(0, min(len(rows) - 1, idx + delta))
    app.selected_path = rows[nxt].path
    table = app.query_one(widget_projects, DataTable)
    table.cursor_coordinate = (nxt, 0)
    app._refresh_side()
    return rows[nxt]


def target_rows(app: Any) -> list[ProjectRow]:
    rows = app._current_rows()
    selected = [row for row in rows if row.path in app.multi_selected]
    if selected:
        return selected
    cur = app._selected_row()
    return [cur] if cur else []


def wip_rows_sorted(app: Any) -> list[ProjectRow]:
    return sorted([row for row in app.active_rows if row.wip], key=lambda row: row.name.lower())
