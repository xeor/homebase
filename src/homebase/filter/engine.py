from __future__ import annotations

import fnmatch
import re
import time
from datetime import datetime
from typing import Any, Callable

StructuredTermBuilder = Callable[[str, str], tuple[str | None, Callable[[Any], bool] | None]]

STRUCTURED_TERM_RE = re.compile(
    r"^:([a-z][a-z0-9-]*)(!=|<=|>=|=|<|>|~)(.+)$"
)
STRUCTURED_OPS = frozenset({"=", "!=", "<", "<=", ">", ">=", "~"})


def _has_glob(pattern: str) -> bool:
    return any(ch in pattern for ch in "*?[")


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
    normalized = ["OR" if (token.upper() == "OR" or token == "|") else token for token in tokens]

    with_and: list[str] = []
    prev_kind = ""
    prev_term = ""
    for token in normalized:
        kind = "TERM"
        if token == "(":
            kind = "LP"
        elif token == ")":
            kind = "RP"
        elif token == "OR":
            kind = "OR"
        if with_and and prev_kind in {"TERM", "RP"} and kind in {"TERM", "LP"}:
            if prev_kind == "TERM" and kind == "TERM" and prev_term.startswith("@") and token.startswith("@"):
                with_and.append("OR")
            else:
                with_and.append("AND")
        with_and.append(token)
        prev_kind = kind
        prev_term = token if kind == "TERM" else ""

    prec = {"OR": 1, "AND": 2}
    out: list[str] = []
    ops: list[str] = []
    for token in with_and:
        if token in {"AND", "OR"}:
            while ops and ops[-1] in prec and prec[ops[-1]] >= prec[token]:
                out.append(ops.pop())
            ops.append(token)
            continue
        if token == "(":
            ops.append(token)
            continue
        if token == ")":
            while ops and ops[-1] != "(":
                out.append(ops.pop())
            if not ops or ops[-1] != "(":
                return (lambda _row: True), "filter parse error: unmatched ')'"
            ops.pop()
            continue
        out.append(token)
    while ops:
        op = ops.pop()
        if op in {"(", ")"}:
            return (lambda _row: True), "filter parse error: unmatched '('"
        out.append(op)

    now_ts = int(time.time())
    compiled_named: dict[str, Callable[[Any], bool]] = {}
    compiling_named: set[str] = set()
    hints: list[str] = []

    def compare_int(lhs: int, op: str, rhs: int) -> bool:
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

    def duration_to_seconds(n: int, unit: str) -> int:
        mult = {"s": 1, "h": 3600, "d": 86400, "w": 604800, "m": 2592000, "y": 31536000}
        return n * mult.get(unit, 1)

    def parse_relative_span_to_seconds(spec: str) -> int | None:
        parts = re.findall(r"(\d+)([ymwdhs])", spec)
        if not parts:
            return None
        rebuilt = "".join(f"{n}{u}" for n, u in parts)
        if rebuilt != spec:
            return None
        total = 0
        for n, u in parts:
            total += duration_to_seconds(int(n), u)
        return total

    def row_ts(row: Any, field: str) -> int:
        if field == "created":
            return int(getattr(row, "created_ts", 0))
        if field == "active":
            return int(getattr(row, "opened_ts", 0))
        return int(getattr(row, "last_ts", 0))

    def parse_date_literal(value: str) -> tuple[int, ...] | None:
        if re.fullmatch(r"\d{4}", value):
            return (int(value),)
        if re.fullmatch(r"\d{4}-\d{2}", value):
            year, month = value.split("-", 1)
            yy = int(year)
            mm = int(month)
            return (yy, mm) if 1 <= mm <= 12 else None
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            year, month, day = value.split("-", 2)
            yy = int(year)
            mm = int(month)
            dd = int(day)
            try:
                datetime(yy, mm, dd)
            except (TypeError, ValueError):
                return None
            return (yy, mm, dd)
        return None

    def date_key(ts: int, precision: int) -> tuple[int, ...] | None:
        if ts <= 0:
            return None
        dt = datetime.fromtimestamp(ts).astimezone()
        if precision == 1:
            return (dt.year,)
        if precision == 2:
            return (dt.year, dt.month)
        return (dt.year, dt.month, dt.day)

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

    def _make_time_builder(field: str) -> StructuredTermBuilder:
        def build(op: str, value: str) -> tuple[str | None, Callable[[Any], bool] | None]:
            if value.startswith("@-"):
                seconds = parse_relative_span_to_seconds(value[2:])
                if seconds is None:
                    return f"invalid relative span: :{field}{op}{value}", None
                if op != "=":
                    return (
                        f"operator {op} not implemented for :{field} with relative span",
                        None,
                    )
                threshold = now_ts - seconds
                return None, (lambda row: row_ts(row, field) >= threshold)
            rhs_key = parse_date_literal(value)
            if rhs_key is None:
                return f"invalid value for :{field}: {value!r}", None
            precision = len(rhs_key)

            def pred(row: Any) -> bool:
                lhs_key = date_key(row_ts(row, field), precision)
                if lhs_key is None:
                    return False
                if op == "=":
                    return lhs_key == rhs_key
                if op == "!=":
                    return lhs_key != rhs_key
                if op == "<":
                    return lhs_key < rhs_key
                if op == "<=":
                    return lhs_key <= rhs_key
                if op == ">":
                    return lhs_key > rhs_key
                if op == ">=":
                    return lhs_key >= rhs_key
                return False

            return None, pred

        return build

    def _make_count_builder(field: str) -> StructuredTermBuilder:
        def build(op: str, value: str) -> tuple[str | None, Callable[[Any], bool] | None]:
            if not re.fullmatch(r"\d+", value):
                return f"invalid value for :{field}: {value!r}", None
            rhs = int(value)

            def lhs(row: Any) -> int:
                return len(getattr(row, field, []))

            return None, (lambda row: compare_int(lhs(row), op, rhs))

        return build

    structured_builders: dict[str, StructuredTermBuilder] = {
        "created": _make_time_builder("created"),
        "modified": _make_time_builder("modified"),
        "active": _make_time_builder("active"),
        "tags": _make_count_builder("tags"),
        "properties": _make_count_builder("properties"),
    }
    if extra_term_builders:
        structured_builders.update(extra_term_builders)

    def term_pred(token: str) -> Callable[[Any], bool]:
        if token.startswith("-") and len(token) > 1:
            inner = term_pred(token[1:])
            return lambda row: not inner(row)

        low = token.lower()

        m_struct = STRUCTURED_TERM_RE.match(low)
        if m_struct:
            key = m_struct.group(1)
            op = m_struct.group(2)
            value = m_struct.group(3)
            builder = structured_builders.get(key)
            if builder is None:
                hints.append(f"unknown filter key: :{key}")
                return lambda _row: False
            hint, struct_pred = builder(op, value)
            if hint is not None:
                hints.append(hint)
                return lambda _row: False
            assert struct_pred is not None
            return struct_pred

        if token.startswith("@") and len(token) > 1:
            return named_pred(token[1:].strip())
        if token.startswith(".") and len(token) > 1:
            pattern = token[1:].strip().lower()
            if _has_glob(pattern):
                return lambda row: fnmatch.fnmatchcase(
                    (getattr(row, "suffix", "") or "").lower(), pattern
                )
            return lambda row: (getattr(row, "suffix", "") or "").lower() == pattern
        if token.startswith("##") and len(token) > 2:
            pattern = token[2:].lower()
            is_glob = _has_glob(pattern)

            def _tree_tag_match(row: Any) -> bool:
                tags = getattr(row, "tags", []) or []
                cached = getattr(row, "tags_lower", None)
                if is_glob:
                    iterable = cached if cached is not None else (str(t).lower() for t in tags)
                    for tag_low in iterable:
                        if fnmatch.fnmatchcase(tag_low, pattern):
                            return True
                else:
                    if cached is not None and pattern in cached:
                        return True
                    if cached is None:
                        for tag in tags:
                            if str(tag).lower() == pattern:
                                return True
                if tag_ancestors_fn is None:
                    return False
                for tag in tags:
                    for anc in tag_ancestors_fn(str(tag)):
                        anc_low = anc.lower()
                        if is_glob:
                            if fnmatch.fnmatchcase(anc_low, pattern):
                                return True
                        elif anc_low == pattern:
                            return True
                return False

            return _tree_tag_match
        if token.startswith("#") and len(token) > 1:
            pattern = token[1:].lower()
            if _has_glob(pattern):
                def _tag_glob(row: Any) -> bool:
                    cached = getattr(row, "tags_lower", None)
                    iterable = cached if cached is not None else (
                        str(t).lower() for t in getattr(row, "tags", [])
                    )
                    for tag_low in iterable:
                        if fnmatch.fnmatchcase(tag_low, pattern):
                            return True
                    return False

                return _tag_glob

            def _tag_match(row: Any) -> bool:
                cached = getattr(row, "tags_lower", None)
                if cached is not None:
                    return pattern in cached
                for tag in getattr(row, "tags", []):
                    if str(tag).lower() == pattern:
                        return True
                return False

            return _tag_match
        if token.startswith("!") and len(token) > 1:
            pattern = token[1:].lower()
            if _has_glob(pattern):
                return lambda row: any(
                    any(fnmatch.fnmatchcase(alias, pattern) for alias in property_alias_set_fn(str(prop)))
                    for prop in getattr(row, "properties", [])
                )
            return lambda row: any(
                pattern in property_alias_set_fn(str(prop))
                for prop in getattr(row, "properties", [])
            )
        return lambda row: match_query_fn(row, low)

    def _and_pred(a: Callable[[Any], bool], b: Callable[[Any], bool]) -> Callable[[Any], bool]:
        return lambda row: a(row) and b(row)

    def _or_pred(a: Callable[[Any], bool], b: Callable[[Any], bool]) -> Callable[[Any], bool]:
        return lambda row: a(row) or b(row)

    pred_stack: list[Callable[[Any], bool]] = []
    malformed = False
    for token in out:
        if token == "AND":
            if len(pred_stack) < 2:
                malformed = True
                break
            b = pred_stack.pop()
            a = pred_stack.pop()
            pred_stack.append(_and_pred(a, b))
        elif token == "OR":
            if len(pred_stack) < 2:
                malformed = True
                break
            b = pred_stack.pop()
            a = pred_stack.pop()
            pred_stack.append(_or_pred(a, b))
        else:
            pred_stack.append(term_pred(token))

    if malformed or len(pred_stack) != 1:
        return (lambda _row: False), None

    predicate = pred_stack[0]
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


def normalize_filter_expression(expr: str, *, token_re: re.Pattern[str]) -> str:
    tokens = token_re.findall(expr.strip())
    if not tokens:
        return ""

    norm = ["OR" if (token == "|" or token.upper() == "OR") else token for token in tokens]
    changed = True
    while changed:
        changed = False
        while norm and norm[0] in {"OR", ")"}:
            norm.pop(0)
            changed = True
        while norm and norm[-1] in {"OR", "("}:
            norm.pop()
            changed = True

        i = 0
        out: list[str] = []
        while i < len(norm):
            cur = norm[i]
            nxt = norm[i + 1] if i + 1 < len(norm) else ""
            if cur == "OR" and nxt == "OR":
                out.append("OR")
                i += 2
                changed = True
                continue
            if cur == "(" and nxt == ")":
                i += 2
                changed = True
                continue
            if cur == "(" and nxt == "OR":
                out.append("(")
                i += 2
                changed = True
                continue
            if cur == "OR" and nxt == ")":
                out.append(")")
                i += 2
                changed = True
                continue
            out.append(cur)
            i += 1
        norm = out
    return " ".join(norm)


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
