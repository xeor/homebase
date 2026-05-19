from __future__ import annotations

from pathlib import Path

import yaml

from homebase.commands import basic as commands_basic
from homebase.config import tag_rules
from homebase.config.store import clear_global_config_cache
from homebase.core.constants import GLOBAL_CONFIG_FILE_NAME, HOMEBASE_DIR_NAME
from homebase.core.models import ProjectRow


def _row(name: str, tags: list[str]) -> ProjectRow:
    return ProjectRow(
        path=Path(f"/tmp/{name}"),
        name=name,
        branch="main",
        dirty="",
        last="-",
        src="fs",
        created="-",
        tags=list(tags),
        properties=[],
        description="",
        created_ts=0,
        last_ts=0,
        git_ts=0,
        opened_ts=0,
        is_fork=False,
        is_tmp=False,
        archived=False,
        restore_target=None,
        archived_ts=0,
        wip=False,
        suffix=None,
    )


def _setup_base(tmp_path: Path, rules: list[dict] | None = None) -> Path:
    base = tmp_path / "base"
    (base / HOMEBASE_DIR_NAME).mkdir(parents=True)
    cfg_path = base / HOMEBASE_DIR_NAME / GLOBAL_CONFIG_FILE_NAME
    if rules is None:
        cfg_path.write_text("")
    else:
        cfg_path.write_text(yaml.safe_dump({"tag_rules": rules}))
    clear_global_config_cache()
    tag_rules.clear_tag_rules_cache()
    return base


def _run(base: Path, active: list[ProjectRow], archived: list[ProjectRow] | None = None) -> int:
    archived = archived or []
    return commands_basic.cmd_tags_ls(
        base,
        load_rows=lambda _bd: (active, archived),
    )


def test_empty_workspace_no_rules(tmp_path: Path, capsys) -> None:
    base = _setup_base(tmp_path)
    rc = _run(base, [])
    assert rc == 0
    assert "no tags configured" in capsys.readouterr().out


def test_lists_workspace_tags_without_rules(tmp_path: Path, capsys) -> None:
    base = _setup_base(tmp_path)
    rows = [_row("a", ["work", "home"])]
    rc = _run(base, rows)
    assert rc == 0
    out = capsys.readouterr().out
    assert "work" in out
    assert "home" in out
    # No rule → "(no rule)" label and × count.
    assert "no rule" in out
    assert "× 1" in out


def test_hierarchy_appears_in_output(tmp_path: Path, capsys) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"], "color": "#ff5555"},
        {"tags": ["priority"], "parents": ["meta"]},
    ])
    rows = [
        _row("p1", ["prio:p0", "prio:p1"]),
        _row("p2", ["prio:p0"]),
    ]
    rc = _run(base, rows)
    assert rc == 0
    out = capsys.readouterr().out
    # Root is meta (no parents). priority is its child. prio:p0/p1 nest
    # one level deeper.
    assert "meta" in out
    assert "priority" in out
    assert "prio:p0" in out
    assert "prio:p1" in out
    # The order in the output reflects DFS — meta should appear
    # before priority before the prio tags.
    assert out.index("meta") < out.index("priority") < out.index("prio:p0")


def test_multi_parent_appears_under_each(tmp_path: Path, capsys) -> None:
    base = _setup_base(tmp_path, [
        {"tags": ["python"], "parents": ["programming", "compiled"]},
    ])
    rows = [_row("p1", ["python"])]
    rc = _run(base, rows)
    assert rc == 0
    out = capsys.readouterr().out
    # python should appear twice — once under each parent.
    assert out.count("python") >= 2


def test_project_counts_include_archived(tmp_path: Path, capsys) -> None:
    base = _setup_base(tmp_path)
    active = [_row("a", ["work"]), _row("b", ["work"])]
    archived = [_row("c", ["work"])]
    rc = _run(base, active, archived)
    assert rc == 0
    out = capsys.readouterr().out
    assert "× 3" in out


def test_orphan_tags_appear_at_top_level(tmp_path: Path, capsys) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^wip$", "suffix": " 🔥"},  # no parent
    ])
    rows = [_row("p", ["wip", "stray"])]
    rc = _run(base, rows)
    assert rc == 0
    out = capsys.readouterr().out
    # Both wip (matched, no parent) and stray (no rule) appear.
    assert "wip" in out
    assert "stray" in out


def test_cycle_does_not_hang(tmp_path: Path, capsys) -> None:
    base = _setup_base(tmp_path, [
        {"tags": ["a"], "parents": ["b"]},
        {"tags": ["b"], "parents": ["a"]},
    ])
    rows = [_row("p", ["a", "b"])]
    rc = _run(base, rows)
    assert rc == 0
    out = capsys.readouterr().out
    # Either listed under "cyclic" group or with the inline cycle note.
    assert "cyclic" in out or "cycle" in out
    # Both nodes must still be visible.
    assert "a" in out and "b" in out


def test_rule_spec_appears_in_listing(tmp_path: Path, capsys) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "color": "#ff5555"},
        {"tags": ["work"], "color": "#88ccff"},
    ])
    rows = [_row("p", ["prio:p0", "work"])]
    rc = _run(base, rows)
    assert rc == 0
    out = capsys.readouterr().out
    assert "^prio:" in out
    # tags=[work] is the synthesised raw_spec for explicit lists.
    assert "tags=['work']" in out or "tags=[\"work\"]" in out


def test_explicit_tag_in_rule_appears_even_if_unused(
    tmp_path: Path, capsys,
) -> None:
    """A name spelled out in a rule's ``tags:`` matcher must show up
    even when no project uses it yet — the user configured it."""
    base = _setup_base(tmp_path, [
        {"tags": ["work", "office"], "parents": ["business"], "color": "#88ccff"},
    ])
    rows = [_row("p", ["work"])]  # only work in use; office is not
    rc = _run(base, rows)
    assert rc == 0
    out = capsys.readouterr().out
    assert "work" in out
    assert "office" in out
    assert "business" in out


def test_group_only_marked_in_listing(tmp_path: Path, capsys) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"]},
        {"tags": ["priority"], "group_only": True},
    ])
    rows = [_row("p", ["prio:p0"])]
    rc = _run(base, rows)
    assert rc == 0
    out = capsys.readouterr().out
    assert "priority" in out
    assert "(group-only)" in out


def test_parent_only_node_with_no_workspace_use(tmp_path: Path, capsys) -> None:
    """A group name that's declared in `parents:` but no project
    actually uses it must still show up."""
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"]},
    ])
    rows = [_row("p", ["prio:p0"])]  # only the child is in use
    rc = _run(base, rows)
    assert rc == 0
    out = capsys.readouterr().out
    assert "priority" in out
    # priority has × 0 (not used directly).
    assert "× 0" in out
