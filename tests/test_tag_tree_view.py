from __future__ import annotations

from pathlib import Path

import yaml

from homebase.config import tag_rules
from homebase.config.store import clear_global_config_cache
from homebase.core.constants import GLOBAL_CONFIG_FILE_NAME, HOMEBASE_DIR_NAME
from homebase.ui.screens import tag_tree


def _setup_base(tmp_path: Path, rules: list[dict] | None = None) -> Path:
    base = tmp_path / "base"
    (base / HOMEBASE_DIR_NAME).mkdir(parents=True)
    cfg = base / HOMEBASE_DIR_NAME / GLOBAL_CONFIG_FILE_NAME
    if rules is None:
        cfg.write_text("")
    else:
        cfg.write_text(yaml.safe_dump({"tag_rules": rules}))
    clear_global_config_cache()
    tag_rules.clear_tag_rules_cache()
    return base


# ---- build_tag_tree -------------------------------------------------


def test_build_tag_tree_no_rules_returns_workspace_tags(tmp_path: Path) -> None:
    base = _setup_base(tmp_path)
    tree = tag_tree.build_tag_tree(["work", "home"], base)
    assert tree.nodes == frozenset({"work", "home"})
    assert tree.top_level == ("home", "work")
    assert tree.children_of == {}
    assert tree.group_only == frozenset()


def test_build_tag_tree_pulls_in_declared_parents(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"]},
        {"tags": ["priority"], "parents": ["meta"]},
    ])
    tree = tag_tree.build_tag_tree(["prio:p0"], base)
    assert "priority" in tree.nodes
    assert "meta" in tree.nodes
    assert tree.children_of["meta"] == ("priority",)
    assert tree.children_of["priority"] == ("prio:p0",)
    assert "meta" in tree.top_level


def test_build_tag_tree_includes_rule_explicit_tags(tmp_path: Path) -> None:
    """Tags spelled out in a ``tags:`` matcher appear even when no
    project uses them."""
    base = _setup_base(tmp_path, [
        {"tags": ["work", "office"], "parents": ["business"]},
    ])
    tree = tag_tree.build_tag_tree([], base)
    assert {"work", "office", "business"} <= tree.nodes


def test_build_tag_tree_flags_group_only(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"tags": ["priority"], "group_only": True},
        {"tags": ["work"]},
    ])
    tree = tag_tree.build_tag_tree(["work"], base)
    assert "priority" in tree.group_only
    assert "work" not in tree.group_only


def test_build_tag_tree_multi_parent_dag(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"tags": ["python"], "parents": ["programming", "compiled"]},
    ])
    tree = tag_tree.build_tag_tree(["python"], base)
    # python is a child of BOTH programming and compiled.
    assert tree.children_of["programming"] == ("python",)
    assert tree.children_of["compiled"] == ("python",)
    assert set(tree.top_level) == {"programming", "compiled"}


# ---- filter_visible -------------------------------------------------


def test_filter_visible_empty_query_returns_everything(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"]},
    ])
    tree = tag_tree.build_tag_tree(["prio:p0", "home"], base)
    visible, matched = tag_tree.filter_visible(tree, "", base)
    assert visible == tree.nodes
    assert matched == frozenset()


def test_filter_visible_leaf_match_keeps_ancestors(tmp_path: Path) -> None:
    """Search 'python' → visible contains python and BOTH parents
    (programming + compiled) so the path stays visible."""
    base = _setup_base(tmp_path, [
        {"tags": ["python"], "parents": ["programming", "compiled"]},
        {"tags": ["home"]},
    ])
    tree = tag_tree.build_tag_tree(["python", "home"], base)
    visible, matched = tag_tree.filter_visible(tree, "python", base)
    assert matched == frozenset({"python"})
    assert visible == frozenset({"python", "programming", "compiled"})
    # home is unrelated and must not leak in.
    assert "home" not in visible


def test_filter_visible_parent_match_keeps_descendants(tmp_path: Path) -> None:
    """Search 'programming' (a parent) must surface every child so
    the user can drill down."""
    base = _setup_base(tmp_path, [
        {"match": "^lang:", "parents": ["programming"]},
        {"tags": ["python"], "parents": ["programming"]},
        {"tags": ["home"]},
    ])
    tree = tag_tree.build_tag_tree(["lang:rust", "python", "home"], base)
    visible, matched = tag_tree.filter_visible(tree, "programming", base)
    assert matched == frozenset({"programming"})
    assert visible == frozenset({"programming", "lang:rust", "python"})


def test_filter_visible_transitive_ancestor_match(tmp_path: Path) -> None:
    """Search 'meta' → reaches priority and every prio:* via the
    descendants walk."""
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"]},
        {"tags": ["priority"], "parents": ["meta"]},
    ])
    tree = tag_tree.build_tag_tree(["prio:p0", "prio:p1"], base)
    visible, _ = tag_tree.filter_visible(tree, "meta", base)
    assert visible == frozenset({"meta", "priority", "prio:p0", "prio:p1"})


def test_filter_visible_no_match_returns_empty(tmp_path: Path) -> None:
    base = _setup_base(tmp_path)
    tree = tag_tree.build_tag_tree(["work"], base)
    visible, matched = tag_tree.filter_visible(tree, "xyz", base)
    assert visible == frozenset()
    assert matched == frozenset()


def test_filter_visible_is_case_insensitive(tmp_path: Path) -> None:
    base = _setup_base(tmp_path)
    tree = tag_tree.build_tag_tree(["Work", "HOME"], base)
    visible, matched = tag_tree.filter_visible(tree, "wor", base)
    assert matched == frozenset({"Work"})
    assert "Work" in visible


# ---- flatten_for_render --------------------------------------------


def test_flatten_for_render_depth_and_path(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"]},
        {"tags": ["priority"], "parents": ["meta"]},
    ])
    tree = tag_tree.build_tag_tree(["prio:p0", "prio:p1"], base)
    visible, matched = tag_tree.filter_visible(tree, "", base)
    rows = tag_tree.flatten_for_render(tree, visible, matched)
    names = [r.name for r in rows]
    assert names == ["meta", "priority", "prio:p0", "prio:p1"]
    depths = [r.depth for r in rows]
    assert depths == [0, 1, 2, 2]
    assert rows[2].parent_path == ("meta", "priority")


def test_flatten_for_render_dag_duplicates_under_each_parent(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"tags": ["python"], "parents": ["programming", "compiled"]},
    ])
    tree = tag_tree.build_tag_tree(["python"], base)
    visible, matched = tag_tree.filter_visible(tree, "", base)
    rows = tag_tree.flatten_for_render(tree, visible, matched)
    pythons = [r for r in rows if r.name == "python"]
    # python appears once under each parent.
    assert len(pythons) == 2
    paths = sorted(r.parent_path for r in pythons)
    assert paths == [("compiled",), ("programming",)]


def test_flatten_for_render_carries_flags(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"]},
        {"tags": ["priority"], "group_only": True},
    ])
    tree = tag_tree.build_tag_tree(["prio:p0"], base)
    visible, matched = tag_tree.filter_visible(tree, "prio:p0", base)
    rows = tag_tree.flatten_for_render(tree, visible, matched)
    by_name = {r.name: r for r in rows}
    assert by_name["priority"].group_only is True
    assert by_name["prio:p0"].group_only is False
    assert by_name["prio:p0"].matched is True
    assert by_name["priority"].matched is False


def test_flatten_for_render_handles_cycle(tmp_path: Path) -> None:
    """A misconfigured a→b→a cycle must not recurse forever; both
    nodes still surface somewhere (top-level or stranded)."""
    base = _setup_base(tmp_path, [
        {"tags": ["a"], "parents": ["b"]},
        {"tags": ["b"], "parents": ["a"]},
    ])
    tree = tag_tree.build_tag_tree(["a", "b"], base)
    visible, matched = tag_tree.filter_visible(tree, "", base)
    rows = tag_tree.flatten_for_render(tree, visible, matched)
    names = {r.name for r in rows}
    assert names == {"a", "b"}


# ---- selectability helpers -----------------------------------------


def test_selectable_helpers_skip_group_only(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"]},
        {"tags": ["priority"], "group_only": True},
    ])
    tree = tag_tree.build_tag_tree(["prio:p0", "prio:p1"], base)
    visible, matched = tag_tree.filter_visible(tree, "", base)
    rows = tag_tree.flatten_for_render(tree, visible, matched)
    first = tag_tree.first_selectable_index(rows)
    # rows[0]=priority(group), rows[1]=prio:p0(selectable)
    assert rows[first].name == "prio:p0"
    nxt = tag_tree.next_selectable_index(rows, first, forward=True)
    assert rows[nxt].name == "prio:p1"
    # Wrapping past the last selectable returns to the first one,
    # skipping group_only entries.
    wrap = tag_tree.next_selectable_index(rows, nxt, forward=True)
    assert rows[wrap].name == "prio:p0"


def test_first_matched_selectable_skips_groups_and_unmatched(
    tmp_path: Path,
) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"]},
        {"tags": ["priority"], "group_only": True},
    ])
    tree = tag_tree.build_tag_tree(["prio:p0", "prio:p1"], base)
    visible, matched = tag_tree.filter_visible(tree, "prio:p1", base)
    rows = tag_tree.flatten_for_render(tree, visible, matched)
    idx = tag_tree.first_matched_selectable_index(rows)
    assert idx >= 0
    assert rows[idx].name == "prio:p1"


def test_first_matched_selectable_returns_minus_one_for_group_only_match(
    tmp_path: Path,
) -> None:
    """Searching for a group_only ancestor → the match is the group
    itself, which is not selectable. The helper returns -1 so the
    caller can fall back to first selectable."""
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"]},
        {"tags": ["priority"], "group_only": True},
    ])
    tree = tag_tree.build_tag_tree(["prio:p0"], base)
    visible, matched = tag_tree.filter_visible(tree, "priority", base)
    rows = tag_tree.flatten_for_render(tree, visible, matched)
    assert tag_tree.first_matched_selectable_index(rows) == -1
    # But the first selectable still exists (prio:p0 as a descendant).
    assert tag_tree.first_selectable_index(rows) >= 0


def test_first_selectable_returns_minus_one_when_none(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"tags": ["only"], "group_only": True},
    ])
    tree = tag_tree.build_tag_tree(["only"], base)
    visible, matched = tag_tree.filter_visible(tree, "", base)
    rows = tag_tree.flatten_for_render(tree, visible, matched)
    assert tag_tree.first_selectable_index(rows) == -1
