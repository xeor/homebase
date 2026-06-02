from __future__ import annotations

import asyncio

from homebase.ui import widgets


def test_token_bounds_blank_value() -> None:
    assert widgets.token_bounds("") == (0, 0, "")


def test_token_bounds_all_whitespace() -> None:
    assert widgets.token_bounds("   ") == (3, 3, "")


def test_token_bounds_trims_trailing_whitespace() -> None:
    start, end, token = widgets.token_bounds("hello world  ")
    assert token == "world"
    assert "hello world  "[start:end] == "world"


def test_token_bounds_single_token() -> None:
    start, end, token = widgets.token_bounds("alpha")
    assert token == "alpha"
    assert (start, end) == (0, 5)


def test_token_bounds_returns_last_token_only() -> None:
    start, end, token = widgets.token_bounds("foo bar baz")
    assert token == "baz"
    assert "foo bar baz"[start:end] == "baz"


def test_token_filter_suggester_returns_first_candidate() -> None:
    suggester = widgets.TokenFilterSuggester(get_candidates=lambda _t: ["alpha"])
    out = asyncio.new_event_loop().run_until_complete(
        suggester.get_suggestion("foo al")
    )
    assert out == "foo alpha"


def test_token_filter_suggester_handles_no_candidates() -> None:
    suggester = widgets.TokenFilterSuggester(get_candidates=lambda _t: [])
    out = asyncio.new_event_loop().run_until_complete(suggester.get_suggestion("xyz"))
    assert out is None


def test_token_filter_suggester_ignores_trailing_whitespace() -> None:
    suggester = widgets.TokenFilterSuggester(get_candidates=lambda _t: ["alpha"])
    out = asyncio.new_event_loop().run_until_complete(suggester.get_suggestion("foo "))
    assert out is None


def test_token_filter_suggester_handles_none_input() -> None:
    suggester = widgets.TokenFilterSuggester(get_candidates=lambda _t: ["x"])
    out = asyncio.new_event_loop().run_until_complete(suggester.get_suggestion(None))
    assert out is None


def test_safe_data_table_validate_fixed_rows_clamps() -> None:
    class FakeTable:
        row_count = 3

        validate_fixed_rows = widgets.SafeDataTable.validate_fixed_rows

    t = FakeTable()
    assert t.validate_fixed_rows(10) == 3
    assert t.validate_fixed_rows(-5) == 0
    assert t.validate_fixed_rows("bad") == 0
    assert t.validate_fixed_rows(None) == 0


def test_safe_data_table_get_row_height_returns_zero_for_none() -> None:
    class FakeTable:
        get_row_height = widgets.SafeDataTable.get_row_height

        def _super_get_row_height(self, key):  # pragma: no cover - helper
            raise KeyError(key)

    t = FakeTable()
    # None short circuits before the super() call
    assert t.get_row_height(None) == 0
