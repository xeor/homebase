from __future__ import annotations

from pathlib import Path

from homebase.filter import tag_index as tag_index


def test_safe_tag_and_link_component() -> None:
    assert tag_index.safe_tag_component(" api/core ") == "api_core"
    assert tag_index.safe_link_name("x/y") == "x_y"


def test_project_tag_link_name_nested(tmp_path: Path) -> None:
    base = tmp_path / "base"
    proj = base / "team" / "app"
    proj.mkdir(parents=True)
    assert tag_index.project_tag_link_name(base, proj) == "team__app"


def test_cleanup_tag_symlinks_pointing_at_removes_only_matching(
    tmp_path: Path,
) -> None:
    """The cheap cleanup used by ``b rm`` / ``b archive`` must remove
    every _tags/ symlink that pointed at the deleted path (including
    sub-paths) but leave symlinks for other projects untouched, and
    prune emptied tag dirs."""
    base = tmp_path
    proj_deleted = base / "myproj"
    proj_other = base / "other"
    proj_deleted.mkdir()
    proj_other.mkdir()
    tags_root = base / "_tags"
    (tags_root / "work").mkdir(parents=True)
    (tags_root / "scratch").mkdir(parents=True)
    (tags_root / "shared").mkdir(parents=True)
    # Two stale symlinks (both target the to-be-deleted project), one
    # nested under it. They must all be removed.
    (tags_root / "work" / "myproj").symlink_to(proj_deleted.resolve())
    (tags_root / "scratch" / "myproj").symlink_to(
        (proj_deleted / "sub").resolve(),
    )
    # One symlink for an unrelated project. It must stay.
    (tags_root / "shared" / "other").symlink_to(proj_other.resolve())

    removed = tag_index.cleanup_tag_symlinks_pointing_at(base, proj_deleted.resolve())
    assert removed == 2
    assert not (tags_root / "work" / "myproj").exists()
    assert not (tags_root / "scratch" / "myproj").exists()
    assert (tags_root / "shared" / "other").is_symlink()
    # The two tag dirs that lost their only symlinks should be gone.
    assert not (tags_root / "work").exists()
    assert not (tags_root / "scratch").exists()
    assert (tags_root / "shared").is_dir()


def test_cleanup_tag_symlinks_no_tags_dir_is_noop(tmp_path: Path) -> None:
    """When _tags/ doesn't exist (fresh base, no tagged projects yet),
    cleanup must return 0 and never raise."""
    base = tmp_path
    proj = base / "x"
    proj.mkdir()
    assert tag_index.cleanup_tag_symlinks_pointing_at(base, proj.resolve()) == 0


def test_cleanup_tag_symlinks_does_not_walk_projects(
    monkeypatch, tmp_path: Path,
) -> None:
    """Regression: the cleanup must NOT call into ``collect_projects``
    / the slow full-sync path. We make the slow path explode if
    invoked to prove the helper doesn't drag in the full sync."""
    from homebase.filter import tag_index as ti

    def boom(*_a, **_kw):
        raise RuntimeError("full sync must not run from targeted cleanup")
    monkeypatch.setattr(ti, "sync_tag_symlinks_detailed", boom)

    base = tmp_path
    (base / "_tags" / "t").mkdir(parents=True)
    proj = base / "p"
    proj.mkdir()
    (base / "_tags" / "t" / "p").symlink_to(proj.resolve())
    assert ti.cleanup_tag_symlinks_pointing_at(base, proj.resolve()) == 1
