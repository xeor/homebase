from __future__ import annotations

DATATABLE_CELL_PADDING = 1
DATATABLE_VSCROLL_RESERVED = 2
COLUMN_MIN_WIDTH = 4


def solve_visible_column_widths(
    viewport_width: int,
    base_widths: list[int],
    *,
    cell_padding: int = DATATABLE_CELL_PADDING,
    vscroll_reserved: int = DATATABLE_VSCROLL_RESERVED,
) -> list[int]:
    """Resolve column widths so the last column fills remaining viewport.

    Geometry assumed:
        viewport_width = sum(widths) + 2 * cell_padding * n + vscroll_reserved

    Each column adds ``2 * cell_padding`` cells of chrome (Textual DataTable
    pads each cell on both sides). ``vscroll_reserved`` accounts for the
    vertical scrollbar gutter; pass 2 when the gutter is stable (always
    reserved), 0 when no scrollbar is ever shown.

    The last column absorbs leftover space and never shrinks below its
    configured base. All other columns are returned unchanged.
    """
    if not base_widths:
        return []
    cell_pad = max(0, int(cell_padding))
    vscroll = max(0, int(vscroll_reserved))
    n = len(base_widths)
    columns_chrome = 2 * cell_pad * n
    available = max(0, int(viewport_width) - vscroll - columns_chrome)
    fixed_sum = sum(int(w) for w in base_widths[:-1])
    last_base = max(COLUMN_MIN_WIDTH, int(base_widths[-1]))
    last_grown = max(last_base, available - fixed_sum)
    out: list[int] = [int(w) for w in base_widths[:-1]]
    out.append(int(last_grown))
    return out
