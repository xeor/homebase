from __future__ import annotations

from homebase.ui.table.layout import (
    DATATABLE_CELL_PADDING,
    DATATABLE_VSCROLL_RESERVED,
    solve_visible_column_widths,
)


def test_empty_returns_empty():
    assert solve_visible_column_widths(120, []) == []


def test_single_column_grows_to_fill():
    widths = solve_visible_column_widths(
        100, [10], cell_padding=1, vscroll_reserved=2
    )
    assert widths == [100 - 2 - 2]


def test_last_column_absorbs_leftover_others_unchanged():
    base = [12, 8, 20]
    widths = solve_visible_column_widths(
        80, base, cell_padding=1, vscroll_reserved=2
    )
    assert widths[:-1] == base[:-1]
    assert widths[-1] == 80 - 2 - (2 * 1 * 3) - (12 + 8)


def test_last_column_never_shrinks_below_base():
    base = [40, 40, 40]
    widths = solve_visible_column_widths(
        50, base, cell_padding=1, vscroll_reserved=2
    )
    assert widths[:-1] == [40, 40]
    assert widths[-1] == 40


def test_zero_viewport_returns_base_widths_for_last():
    base = [10, 12, 14]
    widths = solve_visible_column_widths(
        0, base, cell_padding=1, vscroll_reserved=2
    )
    assert widths[:-1] == [10, 12]
    assert widths[-1] == 14


def test_cell_padding_zero_yields_more_room():
    base = [10, 10]
    no_pad = solve_visible_column_widths(50, base, cell_padding=0, vscroll_reserved=0)
    one_pad = solve_visible_column_widths(50, base, cell_padding=1, vscroll_reserved=0)
    assert no_pad[-1] - one_pad[-1] == 2 * 1 * len(base)


def test_vscroll_reservation_costs_room():
    base = [10, 10]
    no_scroll = solve_visible_column_widths(
        50, base, cell_padding=1, vscroll_reserved=0
    )
    with_scroll = solve_visible_column_widths(
        50, base, cell_padding=1, vscroll_reserved=2
    )
    assert no_scroll[-1] - with_scroll[-1] == 2


def test_geometry_invariant_no_horizontal_overflow():
    """sum(widths) + 2*pad*n + vscroll should never exceed viewport when grown."""
    viewport = 120
    base = [10, 14, 22, 8]
    widths = solve_visible_column_widths(
        viewport, base, cell_padding=1, vscroll_reserved=2
    )
    chrome = 2 * 1 * len(base) + 2
    assert sum(widths) + chrome <= viewport


def test_geometry_invariant_when_base_exceeds_viewport():
    """When configured widths overflow viewport, last col stays at base."""
    base = [80, 80]
    viewport = 50
    widths = solve_visible_column_widths(
        viewport, base, cell_padding=1, vscroll_reserved=2
    )
    assert widths == base


def test_default_constants_match_textual_defaults():
    assert DATATABLE_CELL_PADDING == 1
    assert DATATABLE_VSCROLL_RESERVED == 2


def test_defaults_used_when_kwargs_omitted():
    base = [10, 10]
    explicit = solve_visible_column_widths(
        100, base,
        cell_padding=DATATABLE_CELL_PADDING,
        vscroll_reserved=DATATABLE_VSCROLL_RESERVED,
    )
    implicit = solve_visible_column_widths(100, base)
    assert explicit == implicit


def test_negative_inputs_clamped():
    widths = solve_visible_column_widths(
        -10, [10, 10], cell_padding=-5, vscroll_reserved=-5
    )
    assert widths[0] == 10
    assert widths[-1] == 10


def test_minimum_last_col_floor():
    """Last column floor is 4 when base is below the floor."""
    widths = solve_visible_column_widths(
        20, [10, 1], cell_padding=1, vscroll_reserved=2
    )
    assert widths[-1] == max(4, 20 - 2 - 4 - 10)
