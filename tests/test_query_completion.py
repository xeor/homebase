from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from homebase.config import tag_rules
from homebase.config.store import clear_global_config_cache
from homebase.core.constants import GLOBAL_CONFIG_FILE_NAME, HOMEBASE_DIR_NAME
from homebase.core.models import ProjectRow
from homebase.ui.query import edit as query_edit


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


@dataclass
class _FakeApp:
    base_dir: Path
    active_rows: list[ProjectRow]
    archived_rows: list[ProjectRow] = field(default_factory=list)
    _rows_state_token: int = 0
    completion_counts_token: int = -1
    completion_tag_counts: list = field(default_factory=list)
    completion_prop_counts: list = field(default_factory=list)


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


def test_double_hash_candidates_appear_for_declared_groups(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"]},
        {"tags": ["priority"], "parents": ["meta"]},
        {"tags": ["work"], "parents": ["business"]},
    ])
    app = _FakeApp(
        base_dir=base,
        active_rows=[_row("p", ["prio:p0", "work"])],
    )
    # Empty token returns the full pool — verify both ##X and #X
    # entries coexist.
    full = query_edit.query_completion_candidates(app, "")
    assert "##priority" in full
    assert "##meta" in full
    assert "##business" in full
    assert "#prio:p0" in full
    assert "#work" in full

    # Typing ``##`` narrows to just the group entries.
    just_groups = query_edit.query_completion_candidates(app, "##")
    assert "##priority" in just_groups
    assert "##meta" in just_groups
    assert "##business" in just_groups
    # Plain ``#X`` filtered out because they don't start with ``##``.
    assert not any(c == "#prio:p0" for c in just_groups)


def test_double_hash_filtered_by_prefix(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"]},
        {"tags": ["priority"], "parents": ["meta"]},
    ])
    app = _FakeApp(base_dir=base, active_rows=[_row("p", ["prio:p0"])])
    cands = query_edit.query_completion_candidates(app, "##p")
    assert "##priority" in cands
    assert "##meta" not in cands  # different prefix


def test_no_group_candidates_when_no_rules(tmp_path: Path) -> None:
    base = _setup_base(tmp_path)
    app = _FakeApp(base_dir=base, active_rows=[_row("p", ["work"])])
    cands = query_edit.query_completion_candidates(app, "")
    # No groups defined → no ## entries at all.
    assert not any(c.startswith("##") for c in cands)
    # Regular #X tags still available.
    assert "#work" in cands


def test_double_hash_works_when_base_dir_lookup_fails() -> None:
    """A weird app with no base_dir attribute must not crash the
    completion picker — it should fall back to no group candidates."""

    class Broken:
        active_rows = []
        archived_rows = []
        _rows_state_token = 0
        completion_counts_token = -1
        completion_tag_counts: list = []
        completion_prop_counts: list = []

    app = Broken()
    cands = query_edit.query_completion_candidates(app, "")
    assert not any(c.startswith("##") for c in cands)


def test_single_hash_token_excludes_double_hash_entries(tmp_path: Path) -> None:
    """Typing '#' (just one hash) must NOT cycle through the ##X
    group entries. They live behind explicit '##'."""
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"]},
    ])
    app = _FakeApp(base_dir=base, active_rows=[_row("p", ["prio:p0", "wip"])])
    cands = query_edit.query_completion_candidates(app, "#")
    assert any(c.startswith("##") for c in cands) is False
    # Regular #X entries still come through.
    assert "#prio:p0" in cands
    assert "#wip" in cands


def test_group_only_tag_excluded_from_single_hash(tmp_path: Path) -> None:
    """A group_only tag must not surface in the regular #X pool."""
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"]},
        {"tags": ["priority"], "group_only": True},
    ])
    # If a project somehow has 'priority' as a direct tag, it still
    # gets counted in workspace_tags. The completion pool must still
    # exclude it from #X suggestions.
    app = _FakeApp(
        base_dir=base,
        active_rows=[_row("p", ["prio:p0", "priority"])],
    )
    cands_hash = query_edit.query_completion_candidates(app, "#")
    assert "#priority" not in cands_hash
    # Still discoverable as a group via ##.
    cands_groups = query_edit.query_completion_candidates(app, "##")
    assert "##priority" in cands_groups


def test_existing_completion_pool_still_returned(tmp_path: Path) -> None:
    """Sanity: ``#``, ``!``, ``@``, ``.``, and the misc constants
    still populate the pool alongside the new ``##X`` entries."""
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"]},
    ])
    app = _FakeApp(base_dir=base, active_rows=[_row("p", ["wip"])])
    cands = query_edit.query_completion_candidates(app, "")
    assert "#wip" in cands
    assert "##priority" in cands
    assert "tags=0" in cands  # misc
