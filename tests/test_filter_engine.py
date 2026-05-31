from __future__ import annotations

import re
from dataclasses import dataclass, field

from homebase.filter import engine as filter_engine


@dataclass
class Row:
    name: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    properties: list[str] = field(default_factory=list)
    branch: str = ""
    path: str = ""
    created_ts: int = 0
    opened_ts: int = 0
    last_ts: int = 0
    suffix: str | None = None


TOKEN_RE = re.compile(r"\(|\)|\bOR\b|\||[^\s()|]+", re.IGNORECASE)


def test_compile_filter_expr_matches_tag_and_suffix() -> None:
    pred, err = filter_engine.compile_filter_expr(
        "#api .tmp",
        token_re=TOKEN_RE,
        match_query_fn=lambda row, q: q in row.name.lower(),
        property_alias_set_fn=lambda key: {key.lower()},
        get_named_filter=lambda _name: "",
    )
    assert err is None
    assert pred(Row(name="x", tags=["api"], suffix="tmp")) is True
    assert pred(Row(name="x", tags=["api"], suffix="fork")) is False


def test_compile_filter_expr_supports_named_filter() -> None:
    pred, err = filter_engine.compile_filter_expr(
        "@recent OR #web",
        token_re=TOKEN_RE,
        match_query_fn=lambda row, q: q in row.name.lower(),
        property_alias_set_fn=lambda key: {key.lower()},
        get_named_filter=lambda name: "#api" if name == "recent" else "",
    )
    assert err is None
    assert pred(Row(name="x", tags=["api"])) is True
    assert pred(Row(name="x", tags=["web"])) is True


def test_compile_filter_expr_short_circuits_and() -> None:
    calls: list[str] = []

    def left(_row: Row) -> bool:
        calls.append("left")
        return False

    def right(_row: Row) -> bool:
        calls.append("right")
        return True

    def match_query(row: Row, q: str) -> bool:
        if q == "left":
            return left(row)
        if q == "right":
            return right(row)
        return False

    pred, err = filter_engine.compile_filter_expr(
        "left right",
        token_re=TOKEN_RE,
        match_query_fn=match_query,
        property_alias_set_fn=lambda key: {key.lower()},
        get_named_filter=lambda _name: "",
    )
    assert err is None
    assert pred(Row()) is False
    assert calls == ["left"]


def test_compile_filter_expr_short_circuits_or() -> None:
    calls: list[str] = []

    def left(_row: Row) -> bool:
        calls.append("left")
        return True

    def right(_row: Row) -> bool:
        calls.append("right")
        return True

    def match_query(row: Row, q: str) -> bool:
        if q == "left":
            return left(row)
        if q == "right":
            return right(row)
        return False

    pred, err = filter_engine.compile_filter_expr(
        "left OR right",
        token_re=TOKEN_RE,
        match_query_fn=match_query,
        property_alias_set_fn=lambda key: {key.lower()},
        get_named_filter=lambda _name: "",
    )
    assert err is None
    assert pred(Row()) is True
    assert calls == ["left"]


def test_double_hash_matches_descendants_via_ancestors_fn() -> None:
    """``##X`` matches any row whose tag has X in its ancestor chain
    (and the tag X itself)."""
    tree = {
        "prio:p0": frozenset({"priority", "meta"}),
        "prio:p1": frozenset({"priority", "meta"}),
        "priority": frozenset({"meta"}),
        "home": frozenset(),
    }

    def ancestors(tag: str) -> frozenset[str]:
        return tree.get(tag, frozenset())

    pred, err = filter_engine.compile_filter_expr(
        "##priority",
        token_re=TOKEN_RE,
        match_query_fn=lambda row, q: q in row.name.lower(),
        property_alias_set_fn=lambda key: {key.lower()},
        get_named_filter=lambda _name: "",
        tag_ancestors_fn=ancestors,
    )
    assert err is None
    # Direct hit.
    assert pred(Row(name="x", tags=["priority"])) is True
    # Descendant via single hop.
    assert pred(Row(name="x", tags=["prio:p0"])) is True
    # Unrelated tag.
    assert pred(Row(name="x", tags=["home"])) is False


def test_double_hash_walks_transitively() -> None:
    """``##meta`` should reach prio:* via priority."""
    tree = {
        "prio:p0": frozenset({"priority", "meta"}),
        "priority": frozenset({"meta"}),
    }
    pred, _err = filter_engine.compile_filter_expr(
        "##meta",
        token_re=TOKEN_RE,
        match_query_fn=lambda row, q: q in row.name.lower(),
        property_alias_set_fn=lambda key: {key.lower()},
        get_named_filter=lambda _name: "",
        tag_ancestors_fn=lambda t: tree.get(t, frozenset()),
    )
    assert pred(Row(name="x", tags=["prio:p0"])) is True
    assert pred(Row(name="x", tags=["priority"])) is True
    assert pred(Row(name="x", tags=["meta"])) is True
    assert pred(Row(name="x", tags=["home"])) is False


def test_double_hash_falls_back_to_direct_match_without_ancestors_fn() -> None:
    """Without a tag_ancestors_fn the matcher still finds the tag
    itself — no tree walk, but a direct hit on the parent tag works."""
    pred, _err = filter_engine.compile_filter_expr(
        "##priority",
        token_re=TOKEN_RE,
        match_query_fn=lambda row, q: q in row.name.lower(),
        property_alias_set_fn=lambda key: {key.lower()},
        get_named_filter=lambda _name: "",
    )
    assert pred(Row(name="x", tags=["priority"])) is True
    assert pred(Row(name="x", tags=["prio:p0"])) is False


def test_double_hash_in_named_filter() -> None:
    """A named filter that uses ``##X`` must also get the
    ancestors function so the inner predicate works."""
    tree = {"prio:p0": frozenset({"priority"})}
    pred, _err = filter_engine.compile_filter_expr(
        "@grouped",
        token_re=TOKEN_RE,
        match_query_fn=lambda row, q: q in row.name.lower(),
        property_alias_set_fn=lambda key: {key.lower()},
        get_named_filter=lambda name: "##priority" if name == "grouped" else "",
        tag_ancestors_fn=lambda t: tree.get(t, frozenset()),
    )
    assert pred(Row(name="x", tags=["prio:p0"])) is True


def test_normalize_and_pretty_filter_expression() -> None:
    normalized = filter_engine.normalize_filter_expression("( OR #a | | #b )", token_re=TOKEN_RE)
    assert normalized == "( #a OR #b )"
    pretty = filter_engine.pretty_filter_expression("#a OR (#b #c)", token_re=TOKEN_RE)
    assert "OR" in pretty


def _compile(expr: str, *, extra=None):
    return filter_engine.compile_filter_expr(
        expr,
        token_re=TOKEN_RE,
        match_query_fn=lambda row, q: q in (row.name.lower() if row.name else ""),
        property_alias_set_fn=lambda key: {key.lower()},
        get_named_filter=lambda _name: "",
        extra_term_builders=extra,
    )


def test_structured_relative_time_filter_matches_within_window() -> None:
    import time as _time

    now = int(_time.time())
    pred, err = _compile(":created=@-7d")
    assert err is None
    assert pred(Row(name="x", created_ts=now - 3 * 86400)) is True
    assert pred(Row(name="x", created_ts=now - 30 * 86400)) is False


def test_structured_absolute_date_supports_full_operators() -> None:
    from datetime import datetime

    ts_2025_06 = int(datetime(2025, 6, 1).timestamp())
    pred_eq, err_eq = _compile(":created=2025")
    pred_le, err_le = _compile(":active<=2025-06")
    pred_gt, err_gt = _compile(":modified>2024")
    assert err_eq is None and err_le is None and err_gt is None
    assert pred_eq(Row(created_ts=ts_2025_06)) is True
    assert pred_eq(Row(created_ts=int(datetime(2024, 1, 1).timestamp()))) is False
    assert pred_le(Row(opened_ts=ts_2025_06)) is True
    assert pred_le(Row(opened_ts=int(datetime(2025, 7, 1).timestamp()))) is False
    assert pred_gt(Row(last_ts=ts_2025_06)) is True


def test_structured_relative_with_non_equal_op_emits_hint_and_matches_nothing() -> None:
    pred, err = _compile(":created!=@-7d")
    assert err is not None
    assert "not implemented" in err
    assert pred(Row(created_ts=999)) is False


def test_structured_unknown_key_emits_hint_and_matches_nothing() -> None:
    pred, err = _compile(":nope=foo")
    assert err is not None
    assert "unknown filter key" in err
    assert pred(Row(name="anything")) is False


def test_structured_extra_term_builder_is_consulted() -> None:
    def repo_build(op, value):
        if op != "=":
            return f"operator {op} not implemented for :repo", None
        return None, (lambda row: row.name == value)

    pred, err = _compile(":repo=foo", extra={"repo": repo_build})
    assert err is None
    assert pred(Row(name="foo")) is True
    assert pred(Row(name="bar")) is False


def test_query_uses_filter_syntax_detects_colon_keys() -> None:
    assert filter_engine.query_uses_filter_syntax(":created=2025") is True
    assert filter_engine.query_uses_filter_syntax("foo :modified=@-1d bar") is True
    assert filter_engine.query_uses_filter_syntax("just text") is False


def test_normalize_filter_preserves_colon_tokens() -> None:
    normalized = filter_engine.normalize_filter_expression(
        ":modified=@-7d :created>=2025", token_re=TOKEN_RE
    )
    assert ":modified=@-7d" in normalized
    assert ":created>=2025" in normalized
