"""User-defined tag rules — styling **and** grouping.

A rule matches one or more tags (by regex or explicit list) and
attaches:

* Visual styling — color, bold/italic/underline, optional
  prefix/suffix wrapping the displayed name.
* Parent tags — zero or more group names that the matched tags are
  considered children of. Together these form a tag tree (a DAG,
  really — a tag can have multiple parents).

Rules live in ``.homebase/config.yaml`` under the ``tag_rules:``
key:

    tag_rules:
      - match: "^prio:"
        parents: ["priority"]
        color: "#ff5555"
        bold: true
        prefix: "⚡ "

      - tags: ["work", "office", "meeting"]
        parents: ["business"]
        color: "#88ccff"

      - match: "^wip$"
        suffix: " 🔥"

First match wins: the first rule whose pattern or explicit tag list
matches the tag contributes BOTH styling and parents. Tags with no
matching rule fall back to the hash-based pastel color and no
parents.

Tree queries (``direct_parents``, ``ancestors``, ``descendants``)
expose the relation the configured rules create. The filter language
will use these later for ``##parent`` searches; this module is the
foundation — purely data, no UI.

Both layers are cached:
* Rules are compiled once per :func:`config.store.load_global_config_dict`
  return value (``id(config_dict)`` keys the cache, so a fresh read
  produces a fresh compilation).
* All public queries are ``lru_cache``-ed keyed on the compiled
  rules tuple — when rules change, the new tuple is a new cache key
  and stale entries simply don't get hit.
"""

from __future__ import annotations

import colorsys
import functools
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .store import load_global_config_dict

_CONFIG_KEY = "tag_rules"


@dataclass(frozen=True)
class TagStyle:
    """Visual attributes a rule can attach. All optional — empty /
    false fields mean 'inherit / not set' when composing the final
    Rich style spec."""

    color: str | None = None
    bold: bool = False
    italic: bool = False
    underline: bool = False
    prefix: str = ""
    suffix: str = ""


@dataclass(frozen=True)
class TagRule:
    """One compiled config entry. ``pattern`` and ``explicit_tags``
    are alternative ways to match — a rule applies if EITHER
    matches. ``parents`` are the group names the matched tags belong
    to (may be empty). ``group_only`` marks the matched tag(s) as
    virtual grouping nodes: they don't show up as regular ``#tag``
    candidates or in rendered tag cells, but are still reachable
    through ``##tag`` filters."""

    pattern: re.Pattern[str] | None
    explicit_tags: frozenset[str]
    parents: tuple[str, ...]
    style: TagStyle
    group_only: bool = False
    raw_spec: str = ""  # short description for diagnostics

    def matches(self, tag: str) -> bool:
        if tag in self.explicit_tags:
            return True
        if self.pattern is not None and self.pattern.search(tag):
            return True
        return False


@dataclass(frozen=True)
class ResolvedTagStyle:
    """Everything a renderer needs: the displayed string (with any
    prefix/suffix wrapping) and a Rich-compatible style spec."""

    display: str
    style_spec: str
    matched_rule: str = field(default="")  # raw spec of the winning rule


# ---- Rule compilation ----------------------------------------------

_RULES_BY_CONFIG_ID: dict[int, tuple[TagRule, ...]] = {}


def _coerce_style(entry: dict[str, Any]) -> TagStyle:
    color = entry.get("color")
    return TagStyle(
        color=str(color) if isinstance(color, str) and color.strip() else None,
        bold=bool(entry.get("bold", False)),
        italic=bool(entry.get("italic", False)),
        underline=bool(entry.get("underline", False)),
        prefix=str(entry.get("prefix", "")) if entry.get("prefix") is not None else "",
        suffix=str(entry.get("suffix", "")) if entry.get("suffix") is not None else "",
    )


def _coerce_str_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                out.append(text)
    return tuple(out)


def _compile_rule(entry: Any) -> TagRule | None:
    if not isinstance(entry, dict):
        return None
    raw_match = entry.get("match")
    pattern: re.Pattern[str] | None = None
    if isinstance(raw_match, str) and raw_match:
        try:
            pattern = re.compile(raw_match)
        except re.error:
            pattern = None
    explicit = frozenset(_coerce_str_list(entry.get("tags")))
    if pattern is None and not explicit:
        # Rule must match SOMETHING.
        return None
    parents = _coerce_str_list(entry.get("parents"))
    style = _coerce_style(entry)
    group_only = bool(entry.get("group_only", False))
    raw_spec = (
        str(raw_match) if isinstance(raw_match, str) and raw_match
        else f"tags={sorted(explicit)}"
    )
    return TagRule(
        pattern=pattern,
        explicit_tags=explicit,
        parents=parents,
        style=style,
        group_only=group_only,
        raw_spec=raw_spec,
    )


def _load_rules(base_dir: Path) -> tuple[TagRule, ...]:
    cfg = load_global_config_dict(base_dir)
    key = id(cfg)
    cached = _RULES_BY_CONFIG_ID.get(key)
    if cached is not None:
        return cached
    raw = cfg.get(_CONFIG_KEY) if isinstance(cfg, dict) else None
    rules: list[TagRule] = []
    if isinstance(raw, list):
        for entry in raw:
            rule = _compile_rule(entry)
            if rule is not None:
                rules.append(rule)
    out = tuple(rules)
    _RULES_BY_CONFIG_ID[key] = out
    return out


def clear_tag_rules_cache() -> None:
    """Drop every cached rule + resolution. Pair with
    :func:`config.store.clear_global_config_cache` when you edit the
    YAML programmatically (e.g. in tests)."""
    _RULES_BY_CONFIG_ID.clear()
    hash_tag_color.cache_clear()
    _resolve_cached.cache_clear()
    _direct_parents_cached.cache_clear()
    _ancestors_cached.cache_clear()
    _is_group_only_cached.cache_clear()


# ---- Hash-based fallback color -------------------------------------


@functools.lru_cache(maxsize=4096)
def hash_tag_color(tag: str) -> str:
    digest = hashlib.sha1(tag.encode("utf-8", errors="ignore"), usedforsecurity=False).digest()
    hue = int.from_bytes(digest[:2], "big") / 65535.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.32, 0.95)
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


# ---- Style / display resolution ------------------------------------


@functools.lru_cache(maxsize=8192)
def _resolve_cached(rules: tuple[TagRule, ...], tag: str) -> ResolvedTagStyle:
    matched: TagRule | None = None
    for rule in rules:
        if rule.matches(tag):
            matched = rule
            break
    if matched is None:
        return ResolvedTagStyle(
            display=tag, style_spec=hash_tag_color(tag), matched_rule="",
        )
    style = matched.style
    color = style.color or hash_tag_color(tag)
    spec_parts: list[str] = []
    if style.bold:
        spec_parts.append("bold")
    if style.italic:
        spec_parts.append("italic")
    if style.underline:
        spec_parts.append("underline")
    spec_parts.append(color)
    display = f"{style.prefix}{tag}{style.suffix}"
    return ResolvedTagStyle(
        display=display,
        style_spec=" ".join(spec_parts),
        matched_rule=matched.raw_spec,
    )


def resolve_for_display(tag: str, base_dir: Path) -> ResolvedTagStyle:
    """One-shot resolution for renderers: display string + style
    spec. Always succeeds — falls back to the hash color when no
    rule matches."""
    return _resolve_cached(_load_rules(base_dir), tag)


def resolve_tag_style(tag: str, base_dir: Path) -> TagStyle | None:
    """The raw :class:`TagStyle` from the matching rule, or ``None``
    when nothing matches."""
    for rule in _load_rules(base_dir):
        if rule.matches(tag):
            return rule.style
    return None


# ---- Tree / grouping API -------------------------------------------


@functools.lru_cache(maxsize=8192)
def _direct_parents_cached(
    rules: tuple[TagRule, ...], tag: str,
) -> tuple[str, ...]:
    for rule in rules:
        if rule.matches(tag):
            return rule.parents
    return ()


def direct_parents(tag: str, base_dir: Path) -> tuple[str, ...]:
    """Parent tag names contributed by the first matching rule. An
    empty tuple if nothing matches, or the matching rule has no
    ``parents:`` field. Order preserves the YAML list."""
    return _direct_parents_cached(_load_rules(base_dir), tag)


@functools.lru_cache(maxsize=8192)
def _ancestors_cached(
    rules: tuple[TagRule, ...], tag: str,
) -> frozenset[str]:
    """Transitive ancestors via direct_parents, with a visited-set
    cycle guard. Does NOT include ``tag`` itself."""
    seen: set[str] = set()
    stack: list[str] = list(_direct_parents_cached(rules, tag))
    while stack:
        node = stack.pop()
        if node in seen or node == tag:
            continue
        seen.add(node)
        for parent in _direct_parents_cached(rules, node):
            if parent not in seen and parent != tag:
                stack.append(parent)
    return frozenset(seen)


def ancestors(tag: str, base_dir: Path) -> frozenset[str]:
    """All transitive parents of ``tag``. Cycle-safe (a parent loop
    back to ``tag`` is silently broken)."""
    return _ancestors_cached(_load_rules(base_dir), tag)


def is_descendant_of(tag: str, ancestor: str, base_dir: Path) -> bool:
    """Convenience: would a ``##ancestor`` filter match a project
    that has this tag? True if ``tag == ancestor`` or ``ancestor``
    appears in :func:`ancestors`."""
    if tag == ancestor:
        return True
    return ancestor in ancestors(tag, base_dir)


def descendants(
    parent: str, candidate_tags: frozenset[str], base_dir: Path,
) -> frozenset[str]:
    """All tags in ``candidate_tags`` that have ``parent`` as a
    (transitive) ancestor. ``parent`` itself is included if it's in
    ``candidate_tags``. The candidate set is supplied by the caller
    because the universe of tags is workspace-dependent — typically
    you'd pass every tag currently used by any project."""
    out: set[str] = set()
    for tag in candidate_tags:
        if tag == parent or parent in ancestors(tag, base_dir):
            out.add(tag)
    return frozenset(out)


@functools.lru_cache(maxsize=8192)
def _is_group_only_cached(
    rules: tuple[TagRule, ...], tag: str,
) -> bool:
    for rule in rules:
        if rule.matches(tag):
            return rule.group_only
    return False


def is_group_only(tag: str, base_dir: Path) -> bool:
    """True iff the first matching rule has ``group_only: true``.
    Group-only tags are virtual grouping nodes — hidden from
    ``#tag`` completion and from rendered tag cells, but still
    reachable through ``##tag`` filters."""
    return _is_group_only_cached(_load_rules(base_dir), tag)


def roots(base_dir: Path) -> tuple[str, ...]:
    """All distinct parent tag names declared by any rule, sorted.
    Useful for showing 'top-level groups' in a UI."""
    seen: set[str] = set()
    for rule in _load_rules(base_dir):
        seen.update(rule.parents)
    return tuple(sorted(seen))


def iter_rules(base_dir: Path) -> tuple[TagRule, ...]:
    """All compiled rules in declaration order. Useful for listing
    UIs that want to enumerate explicit tag matchers."""
    return _load_rules(base_dir)


__all__ = [
    "ResolvedTagStyle",
    "TagRule",
    "TagStyle",
    "ancestors",
    "clear_tag_rules_cache",
    "descendants",
    "direct_parents",
    "hash_tag_color",
    "is_descendant_of",
    "is_group_only",
    "iter_rules",
    "resolve_for_display",
    "resolve_tag_style",
    "roots",
]
