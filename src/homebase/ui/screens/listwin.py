from __future__ import annotations

from textual.widget import Widget

FALLBACK_MAX_ROWS = 14
MIN_USABLE_HEIGHT = 3


def _measured_height(body_widget: Widget | None) -> int:
    if body_widget is None:
        return 0
    try:
        return int(body_widget.size.height)
    except (TypeError, ValueError, AttributeError):
        return 0


def compute_window(
    total: int,
    cursor: int,
    current_offset: int,
    body_widget: Widget | None,
    *,
    reserve_bottom_rows: int = 0,
    fallback_max_rows: int = FALLBACK_MAX_ROWS,
) -> tuple[int, int]:
    """Return ``(scroll_offset, max_rows)`` that keeps the cursor row
    inside the rendered window.

    - ``total``: number of rows in the model.
    - ``cursor``: currently selected row index (0-based).
    - ``current_offset``: the previous scroll offset; carried forward
      when the cursor is already in view.
    - ``body_widget``: widget that will hold the rendered rows; its
      measured height is used as the viewport size.
    - ``reserve_bottom_rows``: rows to leave free at the bottom of the
      viewport (e.g. the "showing N-M of K" overflow hint).
    - ``fallback_max_rows``: viewport size to assume when the body
      widget has not been sized yet (the first-paint case).

    The function does not mutate any inputs. Callers must persist the
    returned offset themselves.
    """
    if total < 0:
        total = 0
    if cursor < 0:
        cursor = 0
    elif cursor >= total and total > 0:
        cursor = total - 1
    height = _measured_height(body_widget)
    if height < MIN_USABLE_HEIGHT:
        max_rows = fallback_max_rows
    else:
        max_rows = max(MIN_USABLE_HEIGHT, height - reserve_bottom_rows)
    if total <= max_rows:
        return 0, max_rows
    max_offset = max(0, total - max_rows)
    offset = current_offset
    if offset > max_offset:
        offset = max_offset
    if offset < 0:
        offset = 0
    if cursor < offset:
        offset = cursor
    elif cursor >= offset + max_rows:
        offset = cursor - max_rows + 1
    return offset, max_rows


def overflow_hint(
    total: int, offset: int, window_len: int, *, label: str = "showing"
) -> str | None:
    """Return a "showing X-Y of Z" hint when the list overflows, else
    ``None``. ``window_len`` is the count of rows currently rendered."""
    if window_len >= total:
        return None
    start = offset + 1
    end = offset + window_len
    return f"[dim]{label} {start}-{end} of {total}[/]"


__all__ = ["FALLBACK_MAX_ROWS", "compute_window", "overflow_hint"]
