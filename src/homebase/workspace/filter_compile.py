from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable

from ..core.constants import ENV_BASE_DIR, NAMED_FILTERS
from ..core.models import ProjectRow
from ..filter import engine as filter_engine
from ..metadata import property as property_utils
from ..metadata.api import all_property_defs
from .projects import build_row_haystack_lower

_FILTER_TOKEN_RE = re.compile(r"\(|\)|\bOR\b|\||[^\s()|]+", re.IGNORECASE)


def match_query(row: ProjectRow, query: str) -> bool:
    q = query.strip().lower()
    if not q:
        return True
    hay = row.haystack_lower or build_row_haystack_lower(
        name=row.name,
        description=row.description,
        tags=row.tags,
        properties=row.properties,
        branch=row.branch,
        path=row.path,
    )
    return q in hay


def _property_alias_set(key: str) -> set[str]:
    return property_utils.property_alias_set(key, all_defs=all_property_defs())


def _resolve_base_dir() -> Path | None:
    env = os.environ.get(ENV_BASE_DIR, "")
    if not env:
        return None
    try:
        return Path(env).resolve()
    except (OSError, ValueError):
        return None


def _build_tag_ancestors_fn() -> Callable[[str], frozenset[str]] | None:
    """Resolve the ancestors callback used by ``##X`` filters. Lazy
    import keeps ``filter_compile`` import-cheap when no filter ever
    needs the tag tree."""
    base_dir = _resolve_base_dir()
    if base_dir is None:
        return None
    from ..config.tag_rules import ancestors

    return lambda tag: ancestors(tag, base_dir)


def compile_filter_expr(expr: str) -> tuple[Callable[[ProjectRow], bool], str | None]:
    return filter_engine.compile_filter_expr(
        expr,
        token_re=_FILTER_TOKEN_RE,
        match_query_fn=match_query,
        property_alias_set_fn=_property_alias_set,
        get_named_filter=lambda name: NAMED_FILTERS.get(name, ""),
        tag_ancestors_fn=_build_tag_ancestors_fn(),
    )


def query_uses_filter_syntax(text: str) -> bool:
    return filter_engine.query_uses_filter_syntax(text)


def normalize_filter_expression(expr: str) -> str:
    return filter_engine.normalize_filter_expression(expr, token_re=_FILTER_TOKEN_RE)


def pretty_filter_expression(expr: str) -> str:
    return filter_engine.pretty_filter_expression(expr, token_re=_FILTER_TOKEN_RE)
