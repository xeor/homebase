from __future__ import annotations

from pathlib import Path

from homebase.workspace import discovery as discovery_utils


def test_discovery_prune_walk_dirnames_removes_hidden_and_pruned() -> None:
    names = [".git", "_cache", "node_modules", "proj", "alpha"]
    discovery_utils.discovery_prune_walk_dirnames(
        names,
        prune_names={".git", "node_modules"},
    )
    assert names == ["alpha", "proj"]


def test_discovery_should_skip_active_walk_path_for_archive(tmp_path: Path) -> None:
    base = tmp_path / "base"
    archive = base / "_archive"
    archive.mkdir(parents=True)
    cur = archive / "x"
    cur.mkdir()

    assert discovery_utils.discovery_should_skip_active_walk_path(
        base,
        archive,
        cur,
        is_under=lambda p, root: p.resolve().is_relative_to(root.resolve()),
    )


def test_collect_projects_discovers_top_level(tmp_path: Path) -> None:
    base = tmp_path / "base"
    project = base / "p1"
    project.mkdir(parents=True)

    class Row:
        def __init__(self, path: Path) -> None:
            self.path = path

    rows = discovery_utils.collect_projects(
        base,
        include_git_dirty=False,
        include_nested=False,
        size_cache=None,
        archive_dir_name="_archive",
        base_marker_file=".base.yaml",
        resolve_include_nested_fn=lambda _b, inc: bool(inc),
        skip_active_walk_path=lambda _b, _a, _c: False,
        prune_walk_dirnames=lambda _d: None,
        project_row=lambda path, **_kwargs: Row(path),
    )
    assert len(rows) == 1
    assert rows[0].path == project.resolve()
