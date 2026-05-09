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


def test_normalize_and_pretty_filter_expression() -> None:
    normalized = filter_engine.normalize_filter_expression("( OR #a | | #b )", token_re=TOKEN_RE)
    assert normalized == "( #a OR #b )"
    pretty = filter_engine.pretty_filter_expression("#a OR (#b #c)", token_re=TOKEN_RE)
    assert "OR" in pretty
