from __future__ import annotations

import difflib
from typing import Callable, TypeVar

_T = TypeVar("_T")

# Minimum score for an item to be considered a match. Below this the
# item is dropped from the ranked result entirely.
FUZZY_MATCH_THRESHOLD = 0.45


def fuzzy_score(query: str, text: str) -> float:
    """Score how well ``query`` matches ``text`` (0.0 .. ~1.0).

    Combines three signals, taking the best:
    - substring containment (strongest),
    - difflib sequence ratio (handles transpositions / typos),
    - in-order subsequence match (loose "abc" matches "a_b_c").

    The exact weights mirror the original picker ranking so the search
    behaves identically everywhere it's reused.
    """
    q = query.strip().lower()
    t = text.lower()
    if not q:
        return 1.0
    score = 0.0
    if q in t:
        score = max(score, 0.80 + min(0.15, len(q) / max(1, len(t))))
    score = max(score, difflib.SequenceMatcher(None, q, t).ratio())
    qi = 0
    for ch in t:
        if qi < len(q) and ch == q[qi]:
            qi += 1
    if qi == len(q):
        score = max(score, 0.72 + min(0.20, len(q) / max(1, len(t))))
    return score


def fuzzy_rank(
    query: str,
    items: list[_T],
    *,
    key: Callable[[_T], str],
    tiebreak: Callable[[_T], object] | None = None,
) -> list[_T]:
    """Rank ``items`` by fuzzy match against ``query``.

    ``key`` maps an item to its search text. ``tiebreak`` breaks equal
    scores (defaults to the search text). An empty query returns the
    items unchanged (preserving input order).
    """
    q = query.strip()
    if not q:
        return list(items)
    ranked: list[tuple[float, _T]] = []
    for item in items:
        score = fuzzy_score(q, key(item))
        if score >= FUZZY_MATCH_THRESHOLD:
            ranked.append((score, item))
    tb = tiebreak if tiebreak is not None else key
    ranked.sort(key=lambda pair: (-pair[0], tb(pair[1])))
    return [item for _score, item in ranked]


__all__ = ["FUZZY_MATCH_THRESHOLD", "fuzzy_rank", "fuzzy_score"]
