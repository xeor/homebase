from __future__ import annotations

import fnmatch
import re
import time
from datetime import datetime
from typing import Any, Callable

from ..core.utils import normalize_filter_expression

StructuredTermBuilder = Callable[[str, str], tuple[str | None, Callable[[Any], bool] | None]]

STRUCTURED_TERM_RE = re.compile(
    r"^:([a-z][a-z0-9-]*)(!=|<=|>=|=|<|>|~)(.+)$"
)
STRUCTURED_OPS = frozenset({"=", "!=", "<", "<=", ">", ">=", "~"})

_DURATION_MULT = {
    "s": 1,
    "h": 3600,
    "d": 86400,
    "w": 604800,
    "m": 2592000,
    "y": 31536000,
}


def _has_glob(pattern: str) -> bool:
    return any(ch in pattern for ch in "*?[")


def _compare_int(lhs: int, op: str, rhs: int) -> bool:
    if op == "=":
        return lhs == rhs
    if op == "!=":
        return lhs != rhs
    if op == ">":
        return lhs > rhs
    if op == ">=":
        return lhs >= rhs
    if op == "<":
        return lhs < rhs
    if op == "<=":
        return lhs <= rhs
    return False


def _compare_key(lhs: tuple[int, ...], op: str, rhs: tuple[int, ...]) -> bool:
    if op == "=":
        return lhs == rhs
    if op == "!=":
        return lhs != rhs
    if op == "<":
        return lhs < rhs
    if op == "<=":
        return lhs <= rhs
    if op == ">":
        return lhs > rhs
    if op == ">=":
        return lhs >= rhs
    return False


def _parse_relative_span_to_seconds(spec: str) -> int | None:
    parts = re.findall(r"(\d+)([ymwdhs])", spec)
    if not parts:
        return None
    rebuilt = "".join(f"{n}{u}" for n, u in parts)
    if rebuilt != spec:
        return None
    return sum(int(n) * _DURATION_MULT.get(u, 1) for n, u in parts)


def _row_ts(row: Any, field: str) -> int:
    if field == "created":
        return int(getattr(row, "created_ts", 0))
    if field == "active":
        return int(getattr(row, "opened_ts", 0))
    return int(getattr(row, "last_ts", 0))


def _parse_date_literal(value: str) -> tuple[int, ...] | None:
    if re.fullmatch(r"\d{4}", value):
        return (int(value),)
    if re.fullmatch(r"\d{4}-\d{2}", value):
        year, month = value.split("-", 1)
        yy, mm = int(year), int(month)
        return (yy, mm) if 1 <= mm <= 12 else None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        year, month, day = value.split("-", 2)
        yy, mm, dd = int(year), int(month), int(day)
        try:
            datetime(yy, mm, dd)
        except (TypeError, ValueError):
            return None
        return (yy, mm, dd)
    return None


def _date_key(ts: int, precision: int) -> tuple[int, ...] | None:
    if ts <= 0:
        return None
    dt = datetime.fromtimestamp(ts).astimezone()
    if precision == 1:
        return (dt.year,)
    if precision == 2:
        return (dt.year, dt.month)
    return (dt.year, dt.month, dt.day)


def _make_time_builder(field: str, *, now_ts: int) -> StructuredTermBuilder:
    def build(op: str, value: str) -> tuple[str | None, Callable[[Any], bool] | None]:
        if value.startswith("@-"):
            seconds = _parse_relative_span_to_seconds(value[2:])
            if seconds is None:
                return f"invalid relative span: :{field}{op}{value}", None
            if op != "=":
                return (
                    f"operator {op} not implemented for :{field} with relative span",
                    None,
                )
            threshold = now_ts - seconds
            return None, (lambda row: _row_ts(row, field) >= threshold)
        rhs_key = _parse_date_literal(value)
        if rhs_key is None:
            return f"invalid value for :{field}: {value!r}", None
        precision = len(rhs_key)

        def pred(row: Any) -> bool:
            lhs_key = _date_key(_row_ts(row, field), precision)
            if lhs_key is None:
                return False
            return _compare_key(lhs_key, op, rhs_key)

        return None, pred

    return build


def _make_count_builder(field: str) -> StructuredTermBuilder:
    def build(op: str, value: str) -> tuple[str | None, Callable[[Any], bool] | None]:
        if not re.fullmatch(r"\d+", value):
            return f"invalid value for :{field}: {value!r}", None
        rhs = int(value)

        def pred(row: Any) -> bool:
            lhs = len(getattr(row, field, []))
            return _compare_int(lhs, op, rhs)

        return None, pred

    return build


def _make_suffix_pred(pattern: str) -> Callable[[Any], bool]:
    if _has_glob(pattern):
        return lambda row: fnmatch.fnmatchcase(
            (getattr(row, "suffix", "") or "").lower(), pattern
        )
    return lambda row: (getattr(row, "suffix", "") or "").lower() == pattern


def _make_tag_match_pred(pattern: str) -> Callable[[Any], bool]:
    def pred(row: Any) -> bool:
        cached = getattr(row, "tags_lower", None)
        if cached is not None:
            return pattern in cached
        for tag in getattr(row, "tags", []):
            if str(tag).lower() == pattern:
                return True
        return False

    return pred


def _make_tag_glob_pred(pattern: str) -> Callable[[Any], bool]:
    def pred(row: Any) -> bool:
        cached = getattr(row, "tags_lower", None)
        iterable = cached if cached is not None else (
            str(t).lower() for t in getattr(row, "tags", [])
        )
        for tag_low in iterable:
            if fnmatch.fnmatchcase(tag_low, pattern):
                return True
        return False

    return pred


def _tag_self_match(row: Any, pattern: str, *, is_glob: bool) -> bool:
    tags = getattr(row, "tags", []) or []
    cached = getattr(row, "tags_lower", None)
    if is_glob:
        iterable = cached if cached is not None else (str(t).lower() for t in tags)
        return any(fnmatch.fnmatchcase(tag_low, pattern) for tag_low in iterable)
    if cached is not None:
        return pattern in cached
    return any(str(tag).lower() == pattern for tag in tags)


def _tag_ancestor_match(
    row: Any,
    pattern: str,
    *,
    is_glob: bool,
    tag_ancestors_fn: Callable[[str], frozenset[str]],
) -> bool:
    for tag in getattr(row, "tags", []) or []:
        for anc in tag_ancestors_fn(str(tag)):
            anc_low = anc.lower()
            if is_glob:
                if fnmatch.fnmatchcase(anc_low, pattern):
                    return True
            elif anc_low == pattern:
                return True
    return False


def _make_tag_tree_pred(
    pattern: str,
    *,
    tag_ancestors_fn: Callable[[str], frozenset[str]] | None,
) -> Callable[[Any], bool]:
    is_glob = _has_glob(pattern)

    def pred(row: Any) -> bool:
        if _tag_self_match(row, pattern, is_glob=is_glob):
            return True
        if tag_ancestors_fn is None:
            return False
        return _tag_ancestor_match(
            row, pattern, is_glob=is_glob, tag_ancestors_fn=tag_ancestors_fn,
        )

    return pred


def _make_property_pred(
    pattern: str,
    *,
    property_alias_set_fn: Callable[[str], set[str]],
) -> Callable[[Any], bool]:
    if _has_glob(pattern):
        return lambda row: any(
            any(fnmatch.fnmatchcase(alias, pattern) for alias in property_alias_set_fn(str(prop)))
            for prop in getattr(row, "properties", [])
        )
    return lambda row: any(
        pattern in property_alias_set_fn(str(prop))
        for prop in getattr(row, "properties", [])
    )


_TOKEN_KINDS = {"(": "LP", ")": "RP", "OR": "OR"}


def _classify(token: str) -> str:
    return _TOKEN_KINDS.get(token, "TERM")


def _needs_glue(prev_kind: str, kind: str) -> bool:
    return prev_kind in {"TERM", "RP"} and kind in {"TERM", "LP"}


def _glue_op(prev_kind: str, prev_term: str, kind: str, token: str) -> str:
    if (
        prev_kind == "TERM"
        and kind == "TERM"
        and prev_term.startswith("@")
        and token.startswith("@")
    ):
        return "OR"
    return "AND"


def _insert_implicit_ops(tokens: list[str]) -> list[str]:
    normalized = [
        "OR" if (token.upper() == "OR" or token == "|") else token
        for token in tokens
    ]
    out: list[str] = []
    prev_kind = ""
    prev_term = ""
    for token in normalized:
        kind = _classify(token)
        if out and _needs_glue(prev_kind, kind):
            out.append(_glue_op(prev_kind, prev_term, kind, token))
        out.append(token)
        prev_kind = kind
        prev_term = token if kind == "TERM" else ""
    return out


_RPN_PREC = {"OR": 1, "AND": 2}


def _rpn_consume_operator(token: str, out: list[str], ops: list[str]) -> None:
    while ops and ops[-1] in _RPN_PREC and _RPN_PREC[ops[-1]] >= _RPN_PREC[token]:
        out.append(ops.pop())
    ops.append(token)


def _rpn_consume_rparen(out: list[str], ops: list[str]) -> str | None:
    while ops and ops[-1] != "(":
        out.append(ops.pop())
    if not ops or ops[-1] != "(":
        return "filter parse error: unmatched ')'"
    ops.pop()
    return None


def _to_rpn(tokens: list[str]) -> tuple[list[str], str | None]:
    out: list[str] = []
    ops: list[str] = []
    for token in tokens:
        if token in _RPN_PREC:
            _rpn_consume_operator(token, out, ops)
        elif token == "(":
            ops.append(token)
        elif token == ")":
            err = _rpn_consume_rparen(out, ops)
            if err is not None:
                return [], err
        else:
            out.append(token)
    while ops:
        op = ops.pop()
        if op in {"(", ")"}:
            return [], "filter parse error: unmatched '('"
        out.append(op)
    return out, None


def _and_pred(a: Callable[[Any], bool], b: Callable[[Any], bool]) -> Callable[[Any], bool]:
    return lambda row: a(row) and b(row)


def _or_pred(a: Callable[[Any], bool], b: Callable[[Any], bool]) -> Callable[[Any], bool]:
    return lambda row: a(row) or b(row)


def _evaluate_rpn(
    rpn: list[str],
    term_pred: Callable[[str], Callable[[Any], bool]],
) -> Callable[[Any], bool] | None:
    stack: list[Callable[[Any], bool]] = []
    for token in rpn:
        if token == "AND" or token == "OR":
            if len(stack) < 2:
                return None
            b = stack.pop()
            a = stack.pop()
            stack.append(_and_pred(a, b) if token == "AND" else _or_pred(a, b))
        else:
            stack.append(term_pred(token))
    if len(stack) != 1:
        return None
    return stack[0]


def compile_filter_expr(
    expr: str,
    *,
    token_re: re.Pattern[str],
    match_query_fn: Callable[[Any, str], bool],
    property_alias_set_fn: Callable[[str], set[str]],
    get_named_filter: Callable[[str], str],
    tag_ancestors_fn: Callable[[str], frozenset[str]] | None = None,
    extra_term_builders: dict[str, StructuredTermBuilder] | None = None,
) -> tuple[Callable[[Any], bool], str | None]:
    raw = expr.strip()
    if not raw:
        return (lambda _row: True), None

    tokens = [m.group(0) for m in token_re.finditer(raw)]
    with_ops = _insert_implicit_ops(tokens)
    rpn, parse_err = _to_rpn(with_ops)
    if parse_err is not None:
        return (lambda _row: True), parse_err

    now_ts = int(time.time())
    structured_builders: dict[str, StructuredTermBuilder] = {
        "created": _make_time_builder("created", now_ts=now_ts),
        "modified": _make_time_builder("modified", now_ts=now_ts),
        "active": _make_time_builder("active", now_ts=now_ts),
        "tags": _make_count_builder("tags"),
        "properties": _make_count_builder("properties"),
    }
    if extra_term_builders:
        structured_builders.update(extra_term_builders)

    hints: list[str] = []
    compiled_named: dict[str, Callable[[Any], bool]] = {}
    compiling_named: set[str] = set()

    def named_pred(name: str) -> Callable[[Any], bool]:
        if name in compiled_named:
            return compiled_named[name]
        if name in compiling_named:
            return lambda _row: False
        expr_text = get_named_filter(name).strip()
        if not expr_text:
            return lambda _row: False
        compiling_named.add(name)
        pred, err = compile_filter_expr(
            expr_text,
            token_re=token_re,
            match_query_fn=match_query_fn,
            property_alias_set_fn=property_alias_set_fn,
            get_named_filter=get_named_filter,
            tag_ancestors_fn=tag_ancestors_fn,
        )
        compiling_named.discard(name)
        if err:
            return lambda _row: False
        compiled_named[name] = pred
        return pred

    def structured_pred(match: re.Match[str]) -> Callable[[Any], bool]:
        key, op, value = match.group(1), match.group(2), match.group(3)
        builder = structured_builders.get(key)
        if builder is None:
            hints.append(f"unknown filter key: :{key}")
            return lambda _row: False
        hint, pred = builder(op, value)
        if hint is not None or pred is None:
            if hint is not None:
                hints.append(hint)
            return lambda _row: False
        return pred

    def term_pred(token: str) -> Callable[[Any], bool]:
        if token.startswith("-") and len(token) > 1:
            inner = term_pred(token[1:])
            return lambda row: not inner(row)

        low = token.lower()
        m_struct = STRUCTURED_TERM_RE.match(low)
        if m_struct is not None:
            return structured_pred(m_struct)
        if token.startswith("@") and len(token) > 1:
            return named_pred(token[1:].strip())
        if token.startswith(".") and len(token) > 1:
            return _make_suffix_pred(token[1:].strip().lower())
        if token.startswith("##") and len(token) > 2:
            return _make_tag_tree_pred(
                token[2:].lower(), tag_ancestors_fn=tag_ancestors_fn,
            )
        if token.startswith("#") and len(token) > 1:
            pattern = token[1:].lower()
            return _make_tag_glob_pred(pattern) if _has_glob(pattern) else _make_tag_match_pred(pattern)
        if token.startswith("!") and len(token) > 1:
            return _make_property_pred(
                token[1:].lower(), property_alias_set_fn=property_alias_set_fn,
            )
        return lambda row: match_query_fn(row, low)

    predicate = _evaluate_rpn(rpn, term_pred)
    if predicate is None:
        return (lambda _row: False), None
    hint_msg = "; ".join(hints) if hints else None
    return predicate, hint_msg


def query_uses_filter_syntax(text: str) -> bool:
    q = text.strip()
    if not q:
        return False
    if q.startswith("@") or q.startswith(":"):
        return True
    if any(ch in q for ch in "#!()|"):
        return True
    ql = q.lower()
    if re.search(r"(^|\s):[a-z][a-z0-9-]*(=|!=|<=|>=|<|>|~)", ql):
        return True
    if re.search(r"\bOR\b", q, flags=re.IGNORECASE):
        return True
    if re.search(r"(^|\s)-?\.[A-Za-z0-9_*?\[]", q):
        return True
    if re.search(r"(^|\s)-[@:]", q):
        return True
    return False


def pretty_filter_expression(expr: str, *, token_re: re.Pattern[str]) -> str:
    text = normalize_filter_expression(expr, token_re=token_re)
    if not text:
        return "-"
    tokens = token_re.findall(text)
    if not tokens:
        return "-"

    lines: list[str] = []
    current: list[str] = []
    level = 0
    line_level = 0

    def indent(n: int) -> str:
        return " " * (2 + max(0, n) * 2)

    def flush_current() -> None:
        if not current:
            return
        lines.append(f"{indent(line_level)}{' '.join(current)}")
        current.clear()

    for token in tokens:
        if token == "(":
            flush_current()
            lines.append(f"{indent(level)}(")
            level += 1
            continue
        if token == ")":
            flush_current()
            level = max(0, level - 1)
            lines.append(f"{indent(level)})")
            continue
        if token == "OR":
            flush_current()
            lines.append(f"{indent(level)}OR")
            continue
        if not current:
            line_level = level
        current.append(token)
    flush_current()
    return "\n".join(lines) if lines else "-"
