from __future__ import annotations

from homebase.ui.query.runtime import _render_query_with_cursor


def _colors():
    return {
        "color_key": "#KEY",
        "color_op": "#OP",
        "color_value": "#VAL",
        "color_unknown": "#UNK",
    }


def test_known_structured_token_paints_three_colors() -> None:
    out = _render_query_with_cursor(":created=2025", cursor=99, **_colors())
    assert "[#KEY]:created[/]" in out
    assert "[#OP]=[/]" in out
    assert "[#VAL]2025[/]" in out


def test_unknown_key_renders_with_warn_color() -> None:
    out = _render_query_with_cursor(":nope=foo", cursor=99, **_colors())
    assert "[#UNK]:nope[/]" in out
    assert "[#OP]=[/]" in out


def test_plain_token_not_marked_up() -> None:
    out = _render_query_with_cursor("hello", cursor=99, **_colors())
    assert "[#KEY]" not in out
    assert "hello" in out


def test_cursor_inside_structured_value_is_highlighted() -> None:
    # ":created=" is 9 chars; cursor=10 lands on the '0' of '2025'.
    out = _render_query_with_cursor(":created=2025", cursor=10, **_colors())
    assert "[#VAL]2[/]" in out
    assert "[#VAL]25[/]" in out
    assert " on " in out  # cursor style present


def test_cursor_at_end_appends_blank() -> None:
    out = _render_query_with_cursor("abc", cursor=3, **_colors())
    assert out.endswith("][/]") or "] [/]" in out


def test_hash_tag_token_colorized() -> None:
    out = _render_query_with_cursor("#work", cursor=99, **_colors())
    assert "[#OP]#[/]" in out
    assert "[#VAL]work[/]" in out


def test_named_filter_token_colorized() -> None:
    out = _render_query_with_cursor("@recent", cursor=99, **_colors())
    assert "[#OP]@[/]" in out
    assert "[#KEY]recent[/]" in out


def test_suffix_token_colorized() -> None:
    out = _render_query_with_cursor(".tmp", cursor=99, **_colors())
    assert "[#OP].[/]" in out
    assert "[#UNK]tmp[/]" in out


def test_boolean_operator_token_colorized() -> None:
    out = _render_query_with_cursor("#a OR #b", cursor=99, **_colors())
    assert "[#OP]OR[/]" in out
