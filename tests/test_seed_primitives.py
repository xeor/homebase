from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from homebase.workspace.seed import (
    make_active_project,
    make_archive_entry,
    make_temp_basefolder,
    pack_archive_entry,
    write_project_marker,
)


def _read_marker(path: Path) -> dict:
    return yaml.safe_load((path / ".base.yaml").read_text()) or {}


def test_write_project_marker_emits_only_provided_fields(tmp_path: Path) -> None:
    proj = tmp_path / "p"
    proj.mkdir()
    write_project_marker(
        proj,
        tags=["b", "a", "a"],
        description="hello",
        wip=True,
        repo_dir="repo",
    )
    data = _read_marker(proj)
    assert data == {
        "description": "hello",
        "tags": ["a", "b"],
        "wip": True,
        "repo_dir": "repo",
    }


def test_write_project_marker_empty_writes_blank_marker(tmp_path: Path) -> None:
    proj = tmp_path / "p"
    proj.mkdir()
    write_project_marker(proj)
    assert (proj / ".base.yaml").is_file()
    assert _read_marker(proj) == {}


def test_write_project_marker_filters_falsy_tags(tmp_path: Path) -> None:
    proj = tmp_path / "p"
    proj.mkdir()
    write_project_marker(proj, tags=["", "x", None, "y"])  # type: ignore[list-item]
    assert _read_marker(proj)["tags"] == ["x", "y"]


def test_write_project_marker_accepts_worktree_block(tmp_path: Path) -> None:
    proj = tmp_path / "p"
    proj.mkdir()
    block = {"of": "parent", "branch": "feat/x", "parent_path": "/abs"}
    write_project_marker(proj, repo_dir="repo", worktree=block)
    data = _read_marker(proj)
    assert data["repo_dir"] == "repo"
    assert data["worktree"] == block


def test_write_project_marker_accepts_log_events(tmp_path: Path) -> None:
    proj = tmp_path / "p"
    proj.mkdir()
    events = [{"_event": "seeded", "_ts": "2026-05-26T12:00:00+02:00"}]
    write_project_marker(proj, log={"events": events})
    assert _read_marker(proj)["log"] == {"events": events}


def test_make_active_project_returns_path_and_creates_marker(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    out = make_active_project(base, "demo", tags=["a"], wip=True)
    assert out == base / "demo"
    assert out.is_dir()
    assert _read_marker(out) == {"tags": ["a"], "wip": True}


def test_make_active_project_refuses_existing_dir(tmp_path: Path) -> None:
    base = tmp_path / "base"
    (base / "p").mkdir(parents=True)
    try:
        make_active_project(base, "p")
    except FileExistsError:
        return
    raise AssertionError("expected FileExistsError for existing target")


def test_make_archive_entry_uses_year_subdir(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    entry = make_archive_entry(
        base, date=date(2024, 3, 14), slug="abc",
        tags=["x"], description="d",
    )
    assert entry == base / "_archive" / "2024" / "2024-03-14_abc"
    assert entry.is_dir()
    assert _read_marker(entry) == {"description": "d", "tags": ["x"]}


def test_make_archive_entry_refuses_collision(tmp_path: Path) -> None:
    base = tmp_path / "base"
    make_archive_entry(base, date=date(2024, 3, 14), slug="abc")
    try:
        make_archive_entry(base, date=date(2024, 3, 14), slug="abc")
    except FileExistsError:
        return
    raise AssertionError("expected FileExistsError on duplicate archive entry")


def test_pack_archive_entry_produces_tgz_and_removes_source(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    entry = make_archive_entry(base, date=date(2020, 1, 5), slug="zip-me")
    (entry / "payload.txt").write_text("hi\n")
    packed = pack_archive_entry(base, entry)
    assert packed is not None
    assert packed.suffix == ".tgz"
    assert packed.is_file()
    assert not entry.exists()


def test_pack_archive_entry_returns_none_on_invalid_target(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    bogus = base / "not-in-archive"
    bogus.mkdir()
    assert pack_archive_entry(base, bogus) is None


def test_make_temp_basefolder_creates_unique_writable_dir(tmp_path: Path) -> None:
    a = make_temp_basefolder(tmp_path, "seed")
    b = make_temp_basefolder(tmp_path, "seed")
    try:
        assert a != b
        assert a.is_dir() and b.is_dir()
        (a / "marker").write_text("ok")
    finally:
        import shutil
        shutil.rmtree(a, ignore_errors=True)
        shutil.rmtree(b, ignore_errors=True)
