from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.css.query import NoMatches

from ...core.utils import WIDGET_API_ERRORS


def queue_dynamic_property_refresh(app: Any, paths: list[Path]) -> None:
    if not paths:
        return
    queued: set[Path] = set(app.dynamic_property_refresh_queue)
    for path in paths:
        if path in queued:
            continue
        app.dynamic_property_refresh_queue.append(path)
        queued.add(path)
    app.dynamic_indicator_cache = {}


def run_dynamic_property_refresh_tick(app: Any, *, batch_size: int = 24) -> None:
    if not app.dynamic_property_refresh_queue:
        return
    limit = max(1, int(batch_size))
    chunk = app.dynamic_property_refresh_queue[:limit]
    app.dynamic_property_refresh_queue = app.dynamic_property_refresh_queue[limit:]
    if not chunk:
        return

    touched = False
    chunk_set = set(chunk)
    app.dynamic_indicator_row_cache = {
        key: value
        for key, value in app.dynamic_indicator_row_cache.items()
        if key[1] not in chunk_set
    }
    for path in chunk:
        hit = app._find_row(path)
        if hit is None:
            continue
        rows, idx = hit
        app._apply_dynamic_properties_to_row(rows[idx])
        touched = True
    if not touched:
        return
    app._invalidate_current_rows_cache()
    try:
        app._refresh_table()
        app._refresh_side()
    except (*WIDGET_API_ERRORS, NoMatches):
        return
