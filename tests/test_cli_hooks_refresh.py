from __future__ import annotations

import os
from pathlib import Path

import pytest

from homebase.commands.hooks_cmd import cmd_hooks_refresh
from homebase.core.models import HookSpec
from homebase.metadata.api import append_base_log, ensure_base_marker


def _spec(name: str = "tag_files_sync") -> HookSpec:
    return HookSpec(
        timing="post",
        event="tag_change",
        name=name,
        source="bundled",
        enabled=True,
        views=(),
        config={},
        slow_warn_s=30.0,
        refresh_enabled=False,
        refresh_min_interval_s=60.0,
    )


def _setup_project_with_tag(tmp_path: Path, *, tag: str = "py", project_name: str = "p1") -> tuple[Path, Path]:
    src_root = tmp_path / ".homebase" / "tag-files" / tag
    src_root.mkdir(parents=True)
    project = tmp_path / project_name
    project.mkdir()
    ensure_base_marker(project)
    return project, src_root


def test_hooks_refresh_requires_a_selector(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = cmd_hooks_refresh(
        tmp_path,
        hook_specs={("post", "tag_change"): [_spec()]},
        project_filters=[],
        tag_filters=[],
        filter_expr="",
        hook_filter=[],
        event_filter=[],
        select_all=False,
        show_archived=False,
        dry_run=False,
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "no selectors" in err


def test_hooks_refresh_no_matching_specs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = cmd_hooks_refresh(
        tmp_path,
        hook_specs={("post", "tag_change"): [_spec()]},
        project_filters=[],
        tag_filters=[],
        filter_expr="",
        hook_filter=["does_not_exist"],
        event_filter=[],
        select_all=True,
        show_archived=False,
        dry_run=False,
    )
    assert rc == 1
    assert "no matching hook specs" in capsys.readouterr().err


def test_hooks_refresh_links_new_source_files_via_cli(tmp_path: Path) -> None:
    if not getattr(os, "symlink", None):
        pytest.skip("symlinks not supported")

    project, src_root = _setup_project_with_tag(tmp_path, tag="py")
    base_yaml = project / ".base.yaml"
    base_yaml.write_text("tags:\n  - py\n", encoding="utf-8")
    (src_root / "linted.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    rc = cmd_hooks_refresh(
        tmp_path,
        hook_specs={("post", "tag_change"): [_spec()]},
        project_filters=[str(project)],
        tag_filters=[],
        filter_expr="",
        hook_filter=["tag_files_sync"],
        event_filter=[],
        select_all=False,
        show_archived=False,
        dry_run=False,
    )
    assert rc == 0
    assert (project / "linted.sh").is_symlink()
    assert os.readlink(project / "linted.sh") == str((src_root / "linted.sh").resolve())


def test_hooks_refresh_dry_run_does_not_link(tmp_path: Path) -> None:
    if not getattr(os, "symlink", None):
        pytest.skip("symlinks not supported")

    project, src_root = _setup_project_with_tag(tmp_path, tag="py")
    (project / ".base.yaml").write_text("tags:\n  - py\n", encoding="utf-8")
    (src_root / "linted.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    rc = cmd_hooks_refresh(
        tmp_path,
        hook_specs={("post", "tag_change"): [_spec()]},
        project_filters=[str(project)],
        tag_filters=[],
        filter_expr="",
        hook_filter=["tag_files_sync"],
        event_filter=[],
        select_all=False,
        show_archived=False,
        dry_run=True,
    )
    assert rc == 0
    assert not (project / "linted.sh").exists()


def test_hooks_refresh_prunes_orphan_via_cli(tmp_path: Path) -> None:
    if not getattr(os, "symlink", None):
        pytest.skip("symlinks not supported")

    project, src_root = _setup_project_with_tag(tmp_path, tag="py")
    (project / ".base.yaml").write_text("tags:\n  - py\n", encoding="utf-8")
    src_file = src_root / "extra.sh"
    src_file.write_text("x", encoding="utf-8")
    os.symlink(src_file.resolve(), project / "extra.sh")
    append_base_log(
        project,
        "tag_files_linked",
        {"tag": "py", "rel": "extra.sh", "target": str(src_file.resolve())},
    )
    src_file.unlink()

    rc = cmd_hooks_refresh(
        tmp_path,
        hook_specs={("post", "tag_change"): [_spec()]},
        project_filters=[str(project)],
        tag_filters=[],
        filter_expr="",
        hook_filter=["tag_files_sync"],
        event_filter=[],
        select_all=False,
        show_archived=False,
        dry_run=False,
    )
    assert rc == 0
    assert not (project / "extra.sh").exists()
