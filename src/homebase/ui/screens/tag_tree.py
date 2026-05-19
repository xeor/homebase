"""Pure tree-shape helpers for the tag picker.

The picker UI needs a hierarchical view of the configured tag tree
that's still searchable. This module owns the three primitives:

* :func:`build_tag_tree` — collect the full node set (workspace tags
  + declared parents + transitive ancestors + explicit tag matchers
  in rules) and derive a children-of map.
* :func:`filter_visible` — given a search query, return the set of
  nodes that should remain visible. Matches are kept together with
  their ancestors (so the path stays intact) and their descendants
  (so the user can drill down from a parent match).
* :func:`flatten_for_render` — DFS the tree and emit one ``TreeRow``
  per visible occurrence. Multi-parent tags appear once under each
  parent (the configured tag relation is a DAG, not strictly a
  tree); a visited-path guard breaks any misconfigured cycle.

The module is intentionally widget-free so it can be unit-tested
without the Textual app.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ...config import tag_rules


@dataclass(frozen=True)
class TreeRow:
    """One row to render. ``parent_path`` records the ancestor chain
    that led to this row, so DAG duplicates can be distinguished."""

    name: str
    depth: int
    parent_path: tuple[str, ...]
    group_only: bool
    matched: bool


@dataclass(frozen=True)
class TagTreeView:
    nodes: frozenset[str]
    children_of: dict[str, tuple[str, ...]]
    top_level: tuple[str, ...]
    group_only: frozenset[str]


def build_tag_tree(
    known_tags: Iterable[str], base_dir: Path,
) -> TagTreeView:
    """Collect every name that should be visible in the tree picker.

    Sources of nodes:
      * ``known_tags`` — usually every tag currently in use across
        the workspace plus whatever the caller wants surfaced.
      * Declared parents from ``tag_rules.roots``.
      * Explicit ``tags:`` matchers from any rule (so configured
        groups appear even when no project uses them yet).
      * Transitive ancestors of all of the above.
    """
    names: set[str] = set(known_tags)
    names.update(tag_rules.roots(base_dir))
    for rule in tag_rules.iter_rules(base_dir):
        names.update(rule.explicit_tags)
    queue = list(names)
    while queue:
        node = queue.pop()
        for parent in tag_rules.direct_parents(node, base_dir):
            if parent not in names:
                names.add(parent)
                queue.append(parent)

    children_of: dict[str, list[str]] = {}
    for n in names:
        for parent in tag_rules.direct_parents(n, base_dir):
            children_of.setdefault(parent, []).append(n)
    children_tup: dict[str, tuple[str, ...]] = {
        p: tuple(sorted(set(c))) for p, c in children_of.items()
    }

    top = tuple(
        sorted(n for n in names if not tag_rules.direct_parents(n, base_dir))
    )
    group_only = frozenset(
        n for n in names if tag_rules.is_group_only(n, base_dir)
    )
    return TagTreeView(
        nodes=frozenset(names),
        children_of=children_tup,
        top_level=top,
        group_only=group_only,
    )


def _descendants_in_tree(parent: str, tree: TagTreeView) -> set[str]:
    """Cycle-safe descendant enumeration limited to nodes that
    actually appear in ``tree.children_of``."""
    out: set[str] = set()
    stack: list[str] = list(tree.children_of.get(parent, ()))
    while stack:
        node = stack.pop()
        if node in out:
            continue
        out.add(node)
        for child in tree.children_of.get(node, ()):
            if child not in out:
                stack.append(child)
    return out


def filter_visible(
    tree: TagTreeView, query: str, base_dir: Path,
) -> tuple[frozenset[str], frozenset[str]]:
    """Return ``(visible, matched)`` sets for ``query``.

    * ``matched`` — every node whose lowercased name contains the
      lowercased query.
    * ``visible`` — ``matched`` plus ancestors (so the path to each
      match stays intact) and descendants (so a parent match
      surfaces its children for drill-down).

    With an empty query the entire node set is visible and the
    matched set is empty.
    """
    q = query.strip().lower()
    if not q:
        return tree.nodes, frozenset()
    matched: set[str] = {
        name for name in tree.nodes if q in name.lower()
    }
    if not matched:
        return frozenset(), frozenset()
    visible: set[str] = set(matched)
    for name in matched:
        visible.update(tag_rules.ancestors(name, base_dir))
        visible.update(_descendants_in_tree(name, tree))
    # Intersect against tree.nodes so we never return a phantom
    # ancestor that isn't in the picker scope.
    return frozenset(visible & tree.nodes), frozenset(matched)


def flatten_for_render(
    tree: TagTreeView, visible: frozenset[str], matched: frozenset[str],
) -> list[TreeRow]:
    """DFS from every top-level root and emit a :class:`TreeRow`
    for every visible occurrence. Multi-parent tags appear once
    per parent. Stranded nodes (reachable only via a cycle) are
    emitted at the end with ``depth=0``."""
    out: list[TreeRow] = []
    seen_pairs: set[tuple[str, tuple[str, ...]]] = set()

    def _visit(name: str, depth: int, path: tuple[str, ...]) -> None:
        if name in path:
            return  # cycle guard
        if name not in visible:
            return
        key = (name, path)
        if key in seen_pairs:
            return
        seen_pairs.add(key)
        out.append(TreeRow(
            name=name,
            depth=depth,
            parent_path=path,
            group_only=name in tree.group_only,
            matched=name in matched,
        ))
        for child in tree.children_of.get(name, ()):
            _visit(child, depth + 1, path + (name,))

    for root in tree.top_level:
        _visit(root, 0, ())

    rendered = {row.name for row in out}
    stranded = sorted(visible - rendered)
    for name in stranded:
        out.append(TreeRow(
            name=name,
            depth=0,
            parent_path=(),
            group_only=name in tree.group_only,
            matched=name in matched,
        ))
    return out


def first_selectable_index(rows: list[TreeRow]) -> int:
    """Index of the first row that's not ``group_only``. Returns
    -1 when nothing is selectable."""
    for idx, row in enumerate(rows):
        if not row.group_only:
            return idx
    return -1


def first_matched_selectable_index(rows: list[TreeRow]) -> int:
    """Index of the first row that's both a search hit and
    selectable. Used after a filter edit so the user can press space
    on the result immediately instead of arrowing through every
    ancestor. Returns -1 when no row qualifies (typical when the
    only match is a group-only ancestor)."""
    for idx, row in enumerate(rows):
        if row.matched and not row.group_only:
            return idx
    return -1


def next_selectable_index(
    rows: list[TreeRow], current: int, *, forward: bool,
) -> int:
    """Walk forward / backward from ``current`` to the next non-
    group_only row, wrapping around. Returns ``current`` unchanged
    when there is no selectable row."""
    if not rows or first_selectable_index(rows) < 0:
        return current
    n = len(rows)
    step = 1 if forward else -1
    idx = (current + step) % n
    while rows[idx].group_only and idx != current:
        idx = (idx + step) % n
    return idx


__all__ = [
    "TagTreeView",
    "TreeRow",
    "build_tag_tree",
    "filter_visible",
    "first_matched_selectable_index",
    "first_selectable_index",
    "flatten_for_render",
    "next_selectable_index",
]
