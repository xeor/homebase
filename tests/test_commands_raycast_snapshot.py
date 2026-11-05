from __future__ import annotations

import json
import os
import time
from pathlib import Path

from homebase.cache.api import cache_store_rows
from homebase.commands import raycast_snapshot as snap
from homebase.core.constants import RAYCAST_SNAPSHOT_MAX_AGE_S, RAYCAST_SNAPSHOT_VERSION
from homebase.core.models import ProjectRow


def _row(path: Path) -> ProjectRow:
    return ProjectRow(
        path=path, name=path.name, branch="main", dirty="", last="-", src="fs",
        created="-", tags=["work"], properties=[], description="", created_ts=0,
        last_ts=0, git_ts=0, opened_ts=0, is_fork=False, is_tmp=False,
        archived=False, restore_target=None, archived_ts=0, wip=False,
        suffix=None, worktree_of="", repo_dir="",
    )


def _projects(base: Path) -> list[str]:
    data = json.loads(snap.snapshot_path(base).read_text())
    assert data["version"] == RAYCAST_SNAPSHOT_VERSION
    assert data["base_dir"] == str(base)
    return [p["project"] for p in data["projects"]]


def test_build_snapshot_lists_active_projects_with_paths(tmp_path: Path) -> None:
    cache_store_rows(tmp_path, [_row(tmp_path / "beta"), _row(tmp_path / "alpha")], [])
    data = snap.build_snapshot(tmp_path, now=123.0)
    assert data["generated_ts"] == 123.0
    projects = data["projects"]
    assert isinstance(projects, list)
    assert [(p["project"], p["path"]) for p in projects] == [
        ("alpha", str(tmp_path / "alpha")),
        ("beta", str(tmp_path / "beta")),
    ]


def test_refresh_snapshot_writes_only_on_change_or_age(tmp_path: Path) -> None:
    cache_store_rows(tmp_path, [_row(tmp_path / "alpha")], [])
    key = snap.refresh_snapshot(tmp_path, None)
    path = snap.snapshot_path(tmp_path)
    assert _projects(tmp_path) == ["alpha"]
    old = time.time() - 30
    os.utime(path, (old, old))
    assert snap.refresh_snapshot(tmp_path, key) == key
    assert path.stat().st_mtime == old  # unchanged and young: not rewritten

    cache_store_rows(tmp_path, [_row(tmp_path / "alpha"), _row(tmp_path / "beta")], [])
    key2 = snap.refresh_snapshot(tmp_path, key)
    assert key2 != key
    assert _projects(tmp_path) == ["alpha", "beta"]

    old = time.time() - RAYCAST_SNAPSHOT_MAX_AGE_S - 1
    os.utime(path, (old, old))
    assert snap.refresh_snapshot(tmp_path, key2) == key2
    assert path.stat().st_mtime > old  # same content but old: rewritten


def test_build_snapshot_rereads_changed_config(tmp_path: Path) -> None:
    cache_store_rows(tmp_path, [_row(tmp_path / "alpha")], [])
    config = tmp_path / ".homebase" / "config.yaml"
    config.write_text("raycast:\n  secondary_info: ['{{ tags_space }}']\n")
    [project] = snap.build_snapshot(tmp_path)["projects"]  # type: ignore[misc]
    assert project["subtitle"] == "work"
    config.write_text("raycast:\n  secondary_info: ['{{ name }}!']\n")
    later = time.time() + 5
    os.utime(config, (later, later))
    [project] = snap.build_snapshot(tmp_path)["projects"]  # type: ignore[misc]
    assert project["subtitle"] == "alpha!"
