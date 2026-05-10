from __future__ import annotations

from typing import Callable

from ...core.models import ProjectRow
from ...workspace.filter_compile import compile_filter_expr

_MATCHER_CACHE: dict[str, tuple[Callable[[ProjectRow], bool], str | None]] = {}


def _compile_when(expr: str) -> tuple[Callable[[ProjectRow], bool], str | None]:
    key = str(expr).strip()
    cached = _MATCHER_CACHE.get(key)
    if cached is not None:
        return cached
    pred, err = compile_filter_expr(key)
    _MATCHER_CACHE[key] = (pred, err)
    return pred, err


def resolve_style_rules(
    rules: list[dict[str, str]],
    *,
    row: ProjectRow | None,
) -> dict[str, str]:
    if row is None:
        return {}
    out: dict[str, str] = {}
    for rule in rules:
        when = str(rule.get("when", "")).strip()
        bg_color = str(rule.get("bg_color", "")).strip()
        if not when or not bg_color:
            continue
        pred, err = _compile_when(when)
        if err is not None:
            continue
        try:
            if pred(row):
                for key in ("bg_color", "fg_color", "bold", "underline", "italic"):
                    value = str(rule.get(key, "")).strip()
                    if value:
                        out[key] = value
        except (TypeError, ValueError):
            continue
    return out
