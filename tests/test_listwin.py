from __future__ import annotations

from dataclasses import dataclass

import pytest

from homebase.ui.screens.listwin import (
    FALLBACK_MAX_ROWS,
    compute_window,
    overflow_hint,
)


@dataclass
class _Size:
    height: int


class _Body:
    def __init__(self, height: int) -> None:
        self.size = _Size(height)


def test_first_paint_uses_fallback_when_widget_unsized() -> None:
    offset, max_rows = compute_window(
        total=50, cursor=0, current_offset=0, body_widget=_Body(0)
    )
    assert max_rows == FALLBACK_MAX_ROWS
    assert offset == 0


def test_first_paint_none_widget_uses_fallback() -> None:
    offset, max_rows = compute_window(
        total=50, cursor=0, current_offset=0, body_widget=None
    )
    assert max_rows == FALLBACK_MAX_ROWS
    assert offset == 0


def test_no_overflow_keeps_offset_zero() -> None:
    offset, max_rows = compute_window(
        total=5, cursor=4, current_offset=0, body_widget=_Body(20)
    )
    assert max_rows == 20  # full height (no bottom reserve requested)
    assert offset == 0


def test_cursor_scrolls_offset_down_to_keep_in_view() -> None:
    offset, max_rows = compute_window(
        total=100,
        cursor=30,
        current_offset=0,
        body_widget=_Body(10),
        reserve_bottom_rows=1,
    )
    assert max_rows == 9
    assert offset == 30 - 9 + 1  # cursor at last visible row


def test_cursor_above_offset_pulls_offset_up() -> None:
    offset, _ = compute_window(
        total=100,
        cursor=5,
        current_offset=20,
        body_widget=_Body(10),
        reserve_bottom_rows=1,
    )
    assert offset == 5


def test_cursor_in_view_preserves_offset() -> None:
    offset, max_rows = compute_window(
        total=100,
        cursor=12,
        current_offset=10,
        body_widget=_Body(10),
        reserve_bottom_rows=1,
    )
    assert max_rows == 9
    assert offset == 10


def test_offset_clamped_when_past_end() -> None:
    offset, max_rows = compute_window(
        total=20,
        cursor=0,
        current_offset=999,
        body_widget=_Body(8),
        reserve_bottom_rows=1,
    )
    assert max_rows == 7
    # cursor is 0, so offset should snap to 0
    assert offset == 0


def test_offset_clamped_at_tail_when_cursor_far_below() -> None:
    offset, max_rows = compute_window(
        total=20,
        cursor=19,
        current_offset=0,
        body_widget=_Body(8),
        reserve_bottom_rows=1,
    )
    assert max_rows == 7
    assert offset == 13  # 19 - 7 + 1
    assert offset + max_rows == 20


def test_cursor_beyond_total_is_clamped_to_last() -> None:
    offset, max_rows = compute_window(
        total=10,
        cursor=999,
        current_offset=0,
        body_widget=_Body(5),
        reserve_bottom_rows=1,
    )
    assert max_rows == 4
    assert offset == 6  # last 4 rows
    assert offset + max_rows == 10


def test_negative_cursor_clamped_to_zero() -> None:
    offset, _ = compute_window(
        total=10,
        cursor=-3,
        current_offset=5,
        body_widget=_Body(5),
        reserve_bottom_rows=1,
    )
    assert offset == 0


def test_empty_list_returns_zero_offset() -> None:
    offset, max_rows = compute_window(
        total=0, cursor=0, current_offset=0, body_widget=_Body(20)
    )
    assert offset == 0
    assert max_rows > 0


def test_min_usable_height_floor() -> None:
    # A widget reporting tiny height still produces a usable window
    offset, max_rows = compute_window(
        total=100,
        cursor=50,
        current_offset=0,
        body_widget=_Body(3),
        reserve_bottom_rows=1,
    )
    assert max_rows == 3
    assert offset <= 50 < offset + max_rows


@pytest.mark.parametrize(
    "cursor, prior_offset, expected_offset",
    [
        (0, 0, 0),
        (1, 0, 0),
        (8, 0, 0),
        (9, 0, 1),  # cursor must scroll one past
        (50, 0, 42),
        (50, 42, 42),
        (49, 42, 42),
        (41, 42, 41),  # cursor above offset
    ],
)
def test_cursor_movement_pattern(
    cursor: int, prior_offset: int, expected_offset: int
) -> None:
    offset, _ = compute_window(
        total=100,
        cursor=cursor,
        current_offset=prior_offset,
        body_widget=_Body(10),
        reserve_bottom_rows=1,
    )
    assert offset == expected_offset


def test_overflow_hint_when_overflowing() -> None:
    hint = overflow_hint(100, 10, 9)
    assert hint == "[dim]showing 11-19 of 100[/]"


def test_overflow_hint_none_when_fully_visible() -> None:
    assert overflow_hint(5, 0, 5) is None
    assert overflow_hint(0, 0, 0) is None


def test_overflow_hint_custom_label() -> None:
    hint = overflow_hint(50, 0, 10, label="rows")
    assert hint == "[dim]rows 1-10 of 50[/]"
