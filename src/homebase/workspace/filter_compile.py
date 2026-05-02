from __future__ import annotations

import re
from typing import Callable

from ..core.constants import NAMED_FILTERS
from ..core.models import ProjectRow
from ..filter import engine as filter_engine
from ..metadata import property as property_utils
from ..metadata.api import all_property_defs, property_tokens

_FILTER_TOKEN_RE = re.compile(r"\(|\)|\bOR\b|\||[^\s()|]+", re.IGNORECASE)


def match_query(row: ProjectRow, query: str) -> bool:
    q = query.strip().lower()
    if not q:
        return True
    hay = " ".join(
        [
            row.name,
            row.description,
            " ".join(row.tags),
            " ".join(row.properties),
            property_tokens(row.properties),
            row.branch,
            row.path.as_posix(),
        ]
    ).lower()
    return q in hay


def _property_alias_set(key: str) -> set[str]:
    return property_utils.property_alias_set(key, all_defs=all_property_defs())


def compile_filter_expr(expr: str) -> tuple[Callable[[ProjectRow], bool], str | None]:
    return filter_engine.compile_filter_expr(
        expr,
        token_re=_FILTER_TOKEN_RE,
        match_query_fn=match_query,
        property_alias_set_fn=_property_alias_set,
        get_named_filter=lambda name: NAMED_FILTERS.get(name, ""),
    )


def query_uses_filter_syntax(text: str) -> bool:
    return filter_engine.query_uses_filter_syntax(text)


def normalize_filter_expression(expr: str) -> str:
    return filter_engine.normalize_filter_expression(expr, token_re=_FILTER_TOKEN_RE)


def pretty_filter_expression(expr: str) -> str:
    return filter_engine.pretty_filter_expression(expr, token_re=_FILTER_TOKEN_RE)
