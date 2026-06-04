from __future__ import annotations

from typing import Any

from ...config.tag_rules import is_group_only as tag_is_group_only
from ...config.tag_rules import roots as tag_roots
from ...core.constants import NAMED_FILTERS, SAVED_FILTER_QUERIES, SUFFIXES


def normalize_query_cursor(app: Any) -> None:
    if app.query_cursor < 0:
        app.query_cursor = 0
    if app.query_cursor > len(app.query):
        app.query_cursor = len(app.query)


def reset_query_completion(app: Any) -> None:
    app.query_complete_index = -1
    app.query_complete_candidates = []
    app.query_complete_head = ""
    app.query_complete_tail = ""


def query_token_bounds(app: Any, value: str) -> tuple[int, int, str]:
    if not value:
        return 0, 0, ""
    normalize_query_cursor(app)
    end = min(len(value), app.query_cursor)
    i = end - 1
    while i >= 0 and value[i].isspace():
        i -= 1
    if i < 0:
        return end, end, ""
    end = i + 1
    start = i
    while start >= 0 and not value[start].isspace():
        start -= 1
    start += 1
    return start, end, value[start:end]


def completion_counts(app: Any) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    if app.completion_counts_token == app._rows_state_token:
        return app.completion_tag_counts, app.completion_prop_counts
    all_rows = app.active_rows + app.archived_rows
    tag_counts: dict[str, int] = {}
    prop_counts: dict[str, int] = {}
    for row in all_rows:
        for tag in row.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        for prop in row.properties:
            prop_counts[prop] = prop_counts.get(prop, 0) + 1
    app.completion_tag_counts = sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    app.completion_prop_counts = sorted(prop_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    app.completion_counts_token = app._rows_state_token
    return app.completion_tag_counts, app.completion_prop_counts


def query_completion_candidates(app: Any, token: str) -> list[str]:
    t = token.strip()
    neg = ""
    if t.startswith("-"):
        neg = "-"
        t = t[1:]
    tag_rank, prop_rank = completion_counts(app)
    base_dir = getattr(app, "base_dir", None)
    # Hide group-only tags from the regular ``#X`` pool: those exist
    # purely as ``##group`` filter targets, never as plain project
    # tags. ``base_dir`` may be missing in some test stubs — degrade
    # gracefully.
    if base_dir is not None:
        def _is_group_only(name: str) -> bool:
            try:
                return tag_is_group_only(name, base_dir)
            except (OSError, ValueError):
                return False
    else:
        def _is_group_only(name: str) -> bool:
            del name
            return False
    tags = [f"#{x}" for x, _ in tag_rank if not _is_group_only(x)]
    # ``##X`` completions: only group/parent names. A ``##X`` filter
    # matches the tag X itself plus every descendant via the
    # configured tag_rules tree — offering ``##`` for every plain
    # tag would just clutter the picker since ``#X`` already covers
    # the leaf case.
    try:
        group_names = tag_roots(app.base_dir)
    except (AttributeError, OSError):
        group_names = ()
    parent_tags = [f"##{x}" for x in group_names]
    props = [f"!{x}" for x, _ in prop_rank]
    names = [f"@{n}" for n in sorted(NAMED_FILTERS.keys())]
    suffixes = [f".{s}" for s in SUFFIXES]
    misc = [
        ":tags=0",
        ":tags>4",
        ":properties=0",
        ":properties>0",
        ":created=@-3y",
        ":created=@-2y100d",
        ":created=@-2y20m",
        ":modified=@-7d",
        ":active=@-30d",
        ":created=2025",
        ":created=2025-01",
        ":created=2025-01-05",
        ":created<=2025",
        ":created=@-1w",
        "OR",
        "(",
        ")",
    ]
    pool = (
        names + tags + parent_tags + props + suffixes
        + misc + SAVED_FILTER_QUERIES[:30]
    )
    # Typing a single ``#`` (not ``##``) means "regular tag" — keep
    # the ``##X`` group entries out of the cycled list. Without this
    # guard ``#<tab>`` jumps straight into the group picker because
    # those entries also start with ``#``.
    if t.startswith("#") and not t.startswith("##"):
        pool = [c for c in pool if not c.startswith("##")]
    if not t:
        return [f"{neg}{x}" for x in pool[:120]]
    return [f"{neg}{x}" for x in pool if x.lower().startswith(t.lower())][:120]


def apply_query_completion(app: Any, forward: bool) -> None:
    if app.select_mode:
        return
    if app.query_complete_index < 0 or not app.query_complete_candidates:
        start, end, token = query_token_bounds(app, app.query)
        cands = query_completion_candidates(app, token)
        if not cands:
            return
        app.query_complete_candidates = cands
        app.query_complete_head = app.query[:start]
        app.query_complete_tail = app.query[end:]
        app.query_complete_index = 0 if forward else len(cands) - 1
    else:
        cands = app.query_complete_candidates
        if forward:
            app.query_complete_index = (app.query_complete_index + 1) % len(cands)
        else:
            app.query_complete_index = (app.query_complete_index - 1) % len(cands)
    replacement = cands[app.query_complete_index]
    app.query = app.query_complete_head + replacement + app.query_complete_tail
    app.query_cursor = len(app.query_complete_head + replacement)
    app.filter_expr = app.query
    app._mark_state_dirty()
    app._queue_query_apply()
