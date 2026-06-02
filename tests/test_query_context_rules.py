"""Tests for ``ui/query/context_rules.py`` — the WHEN-based style
rules applied to project rows in the table."""
from __future__ import annotations

from pathlib import Path

from homebase.core.models import ProjectRow
from homebase.ui.query import context_rules as cr


def _row(name: str, *, tags=None, **overrides) -> ProjectRow:
    tags = list(tags or [])
    haystack = " ".join([name, " ".join(tags)]).lower()
    defaults = dict(
        path=Path(f"/tmp/{name}"),
        name=name,
        branch="-",
        dirty="",
        last="",
        src="fs",
        created="",
        tags=tags,
        properties=[],
        description="",
        created_ts=0,
        last_ts=0,
        git_ts=0,
        opened_ts=0,
        is_fork=False,
        is_tmp=False,
        archived=False,
        packed=False,
        pack_format=None,
        restore_target=None,
        archived_ts=0,
        wip=False,
        suffix=None,
        size_bytes=0,
        size_refresh_count=0,
        worktree_of="",
        repo_dir="",
        haystack_lower=haystack,
        tags_lower=frozenset(t.lower() for t in tags),
    )
    defaults.update(overrides)
    return ProjectRow(**defaults)


def setup_function(_function) -> None:
    cr._MATCHER_CACHE.clear()


# ---- resolve_style_rules --------------------------------------------


def test_resolve_style_rules_empty_when_row_is_none() -> None:
    assert cr.resolve_style_rules([{"when": "wip", "bg_color": "red"}], row=None) == {}


def test_resolve_style_rules_empty_when_no_rules() -> None:
    assert cr.resolve_style_rules([], row=_row("a")) == {}


def test_resolve_style_rules_applies_matching_rule() -> None:
    """A rule whose ``when`` expression matches the row applies its
    style payload. We use a tag-based filter to keep the test focused
    on the rule resolver, not the filter parser."""
    rule = {"when": "myco", "bg_color": "#ff0000", "fg_color": "#ffffff"}
    out = cr.resolve_style_rules([rule], row=_row("alpha", tags=["myco"]))
    assert out == {"bg_color": "#ff0000", "fg_color": "#ffffff"}


def test_resolve_style_rules_skips_rule_without_when() -> None:
    rule = {"bg_color": "#ff0000"}
    assert cr.resolve_style_rules([rule], row=_row("a")) == {}


def test_resolve_style_rules_skips_rule_without_bg_color() -> None:
    """A rule needs ``bg_color`` to be considered — fg-only / bold-only
    rules require ``bg_color`` as the gate."""
    rule = {"when": "alpha", "fg_color": "#ffffff"}
    assert cr.resolve_style_rules([rule], row=_row("alpha")) == {}


def test_resolve_style_rules_skips_rule_with_invalid_expression() -> None:
    """An expression that ``compile_filter_expr`` rejects (returns
    an error) is skipped silently — bad rules shouldn't break rendering."""
    rule = {"when": ":bogus-key=true", "bg_color": "#ff0000"}
    out = cr.resolve_style_rules([rule], row=_row("a"))
    assert out == {}


def test_resolve_style_rules_collects_all_style_keys() -> None:
    rule = {
        "when": "myco",
        "bg_color": "#000",
        "fg_color": "#fff",
        "bold": "true",
        "underline": "true",
        "italic": "true",
    }
    out = cr.resolve_style_rules([rule], row=_row("alpha", tags=["myco"]))
    assert out == {
        "bg_color": "#000",
        "fg_color": "#fff",
        "bold": "true",
        "underline": "true",
        "italic": "true",
    }


def test_resolve_style_rules_ignores_blank_style_values() -> None:
    rule = {"when": "myco", "bg_color": "#000", "fg_color": "   "}
    out = cr.resolve_style_rules([rule], row=_row("alpha", tags=["myco"]))
    assert "bg_color" in out
    assert "fg_color" not in out


def test_resolve_style_rules_later_rule_overrides_earlier() -> None:
    """Rules apply in order — when two matching rules both set the
    same key, the last write wins."""
    rules = [
        {"when": "myco", "bg_color": "red"},
        {"when": "myco", "bg_color": "blue"},
    ]
    out = cr.resolve_style_rules(rules, row=_row("alpha", tags=["myco"]))
    assert out["bg_color"] == "blue"


def test_resolve_style_rules_non_matching_rule_does_not_apply() -> None:
    rule = {"when": "myco", "bg_color": "#ff0000"}
    out = cr.resolve_style_rules([rule], row=_row("alpha", tags=[]))
    assert out == {}


# ---- _compile_when caching ------------------------------------------


def test_compile_when_caches_repeated_expressions(monkeypatch) -> None:
    calls = {"n": 0}
    real_compile = cr.compile_filter_expr

    def counting(expr: str):
        calls["n"] += 1
        return real_compile(expr)

    monkeypatch.setattr(cr, "compile_filter_expr", counting)
    cr._compile_when("wip")
    cr._compile_when("wip")
    cr._compile_when("wip")
    assert calls["n"] == 1


def test_compile_when_strips_whitespace_for_cache_key(monkeypatch) -> None:
    """Equivalent expressions with surrounding whitespace share a
    single cache slot."""
    calls = {"n": 0}
    real_compile = cr.compile_filter_expr

    def counting(expr: str):
        calls["n"] += 1
        return real_compile(expr)

    monkeypatch.setattr(cr, "compile_filter_expr", counting)
    cr._compile_when("wip")
    cr._compile_when("  wip  ")
    cr._compile_when("\twip\n")
    assert calls["n"] == 1
