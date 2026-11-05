from __future__ import annotations

import difflib

from homebase.core.fuzzy import FUZZY_MATCH_THRESHOLD, fuzzy_rank, fuzzy_score


def _reference_rank(
    query: str, options: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    """The original picker ranking, kept here as an oracle so the
    extracted helper can't silently drift from its source behavior."""
    q = query.strip().lower()
    if not q:
        return options
    ranked: list[tuple[float, tuple[str, str]]] = []
    for key, label in options:
        text = f"{key} {label}".lower()
        score = 0.0
        if q in text:
            score = max(score, 0.80 + min(0.15, len(q) / max(1, len(text))))
        score = max(score, difflib.SequenceMatcher(None, q, text).ratio())
        qi = 0
        for ch in text:
            if qi < len(q) and ch == q[qi]:
                qi += 1
        if qi == len(q):
            score = max(score, 0.72 + min(0.20, len(q) / max(1, len(text))))
        if score >= 0.45:
            ranked.append((score, (key, label)))
    ranked.sort(key=lambda pair: (-pair[0], pair[1][1]))
    return [item for _score, item in ranked]


_OPTIONS = [
    ("open", "Open in editor"),
    ("notes", "Open notes file"),
    ("archive", "Archive project"),
    ("delete", "Delete forever"),
    ("tags", "Set tags"),
    ("daisy", "Open in DaisyDisk"),
]


def _search_text(item: tuple[str, str]) -> str:
    return f"{item[0]} {item[1]}".lower()


def test_empty_query_preserves_order() -> None:
    assert (
        fuzzy_rank("", _OPTIONS, key=_search_text, tiebreak=lambda i: i[1])
        == _OPTIONS
    )


def test_ranking_matches_reference_oracle() -> None:
    for query in ["open", "op", "notes", "del", "tg", "disk", "xyz", "ar pr"]:
        got = fuzzy_rank(
            query, _OPTIONS, key=_search_text, tiebreak=lambda i: i[1]
        )
        assert got == _reference_rank(query, _OPTIONS), query


def test_substring_outscores_subsequence() -> None:
    assert fuzzy_score("open", "open in editor") > fuzzy_score(
        "open", "o-p-e-n random"
    )


def test_below_threshold_dropped() -> None:
    got = fuzzy_rank(
        "zzzqqq", _OPTIONS, key=_search_text, tiebreak=lambda i: i[1]
    )
    assert got == []
    assert fuzzy_score("zzzqqq", "open in editor") < FUZZY_MATCH_THRESHOLD
