from __future__ import annotations

import time
import webbrowser
from typing import Callable

from textual.suggester import Suggester
from textual.widgets import DataTable, MarkdownViewer


class SafeDataTable(DataTable):
    """DataTable that tolerates a stale ``fixed_rows`` count.

    Textual's ``DataTable.render_line`` builds ``fixed_row_keys`` as
    ``[self._row_locations.get_key(i) for i in range(self.fixed_rows)]``
    and then calls ``self.get_row_height(row_key)`` on each. When
    ``fixed_rows`` exceeds the current row count, ``get_key`` returns
    ``None`` for the out-of-range indices, and ``get_row_height(None)``
    crashes with ``KeyError(None)``. Every terminal resize triggers
    ``render_line``, so the crash surfaces as an apparent
    "resize-crashes-the-app" bug.

    Belt and suspenders: validate ``fixed_rows`` on assignment so it
    can never exceed ``row_count``, AND short-circuit
    ``get_row_height`` for missing keys so a single transiently stale
    render is survivable.
    """

    def validate_fixed_rows(self, value: int) -> int:  # noqa: D401 — Textual hook
        try:
            count = int(value or 0)
        except (TypeError, ValueError):
            count = 0
        return max(0, min(count, self.row_count))

    def get_row_height(self, row_key):  # type: ignore[override]
        if row_key is None:
            return 0
        try:
            return super().get_row_height(row_key)
        except KeyError:
            return 0


def token_bounds(value: str) -> tuple[int, int, str]:
    if not value:
        return 0, 0, ""
    end = len(value)
    i = end - 1
    while i >= 0 and value[i].isspace():
        i -= 1
    if i < 0:
        return end, end, ""
    end = i + 1
    start = i
    while start >= 0 and not value[start].isspace():
        start -= 1
    start += 1
    return start, end, value[start:end]


class TokenFilterSuggester(Suggester):
    def __init__(self, get_candidates: Callable[[str], list[str]]) -> None:
        super().__init__(use_cache=False, case_sensitive=False)
        self.get_candidates = get_candidates

    async def get_suggestion(self, value: str) -> str | None:
        if value is None:
            return None
        start, end, token = token_bounds(value)
        if end != len(value):
            return None
        candidates = self.get_candidates(token)
        if not candidates:
            return None
        cand = candidates[0]
        return value[:start] + cand + value[end:]


class ReadmeMarkdownViewer(MarkdownViewer):
    _last_link_href = ""
    _last_link_ts = 0.0

    async def go(self, location) -> None:
        href = str(location or "").strip()
        if not href:
            return

        now = time.time()
        if href == self._last_link_href and (now - float(self._last_link_ts)) < 0.75:
            return
        self._last_link_href = href
        self._last_link_ts = now

        app = getattr(self, "app", None)
        handler = getattr(app, "_handle_side_markdown_link", None)
        if callable(handler):
            try:
                handler(href)
            except (OSError, ValueError, RuntimeError, webbrowser.Error) as exc:
                show_error = getattr(app, "_show_runtime_error", None)
                if callable(show_error):
                    show_error(f"open markdown link ({href})", exc)
