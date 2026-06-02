from __future__ import annotations

from pathlib import Path

from homebase.archive import service as archive_service


def test_archive_move_internal_moves_directory(tmp_path: Path) -> None:
    base = tmp_path / "base"
    src = base / "p"
    dst = base / "_archive" / "2025" / "2025-01-15_p"
    src.mkdir(parents=True)

    out = archive_service.archive_move_internal(
        base,
        src,
        policy_reason_outside_base=lambda _p, _b: None,
        ensure_safe_cwd=lambda _b, _t: None,
        archive_destination=lambda _s, _b: dst,
        sync_tags_if_needed=lambda _b, _s: None,
        sync_tags=True,
    )
    assert out == dst
    assert dst.is_dir()
    assert not src.exists()


def test_delete_internal_removes_directory(tmp_path: Path) -> None:
    base = tmp_path / "base"
    target = base / "x"
    target.mkdir(parents=True)

    archive_service.delete_internal(
        base,
        target,
        ensure_safe_cwd=lambda _b, _t: None,
        is_packed_archive_path=lambda _p: False,
        sync_tags_if_needed=lambda _b, _s: None,
        sync_tags=True,
    )
    assert not target.exists()


def test_archive_move_internal_rejects_non_dir(tmp_path: Path) -> None:
    import pytest

    src = tmp_path / "ghost"
    with pytest.raises(ValueError, match="not a directory"):
        archive_service.archive_move_internal(
            tmp_path,
            src,
            policy_reason_outside_base=lambda _p, _b: None,
            ensure_safe_cwd=lambda _b, _t: None,
            archive_destination=lambda _s, _b: tmp_path,
            sync_tags_if_needed=lambda _b, _s: None,
            sync_tags=False,
        )


def test_archive_move_internal_rejects_outside_base(tmp_path: Path) -> None:
    import pytest

    base = tmp_path / "base"
    src = base / "p"
    src.mkdir(parents=True)
    with pytest.raises(ValueError, match="not under base"):
        archive_service.archive_move_internal(
            base,
            src,
            policy_reason_outside_base=lambda _p, _b: "outside",
            ensure_safe_cwd=lambda _b, _t: None,
            archive_destination=lambda _s, _b: tmp_path / "ignored",
            sync_tags_if_needed=lambda _b, _s: None,
            sync_tags=False,
        )


def test_archive_move_internal_writes_placeholder_when_cwd_is_src(
    tmp_path: Path, monkeypatch
) -> None:
    base = tmp_path / "base"
    src = base / "p"
    dst = base / "_archive" / "2025" / "2025-01-15_p"
    src.mkdir(parents=True)
    monkeypatch.chdir(src)

    out = archive_service.archive_move_internal(
        base,
        src.resolve(),
        policy_reason_outside_base=lambda _p, _b: None,
        ensure_safe_cwd=lambda _b, _t: None,
        archive_destination=lambda _s, _b: dst,
        sync_tags_if_needed=lambda _b, _s: None,
        sync_tags=True,
    )
    assert out == dst
    assert dst.is_dir()
    placeholder = src / ".archived-placeholder"
    assert placeholder.is_file()
    assert str(dst) in placeholder.read_text()


def test_archive_pack_internal_missing_marker(tmp_path: Path) -> None:
    import pytest

    src = tmp_path / "p"
    src.mkdir()
    with pytest.raises(ValueError, match="missing"):
        archive_service.archive_pack_internal(
            tmp_path,
            src,
            archive_require_dir=lambda _b, _s: None,
            base_marker_file=".base.yaml",
            packed_archive_name=lambda s: f"{s.name}.tgz",
            ensure_safe_cwd=lambda _b, _t: None,
            invalidate_packed_cache_path=lambda _p: None,
        )


def test_archive_pack_internal_rejects_existing_target(tmp_path: Path) -> None:
    import pytest

    src = tmp_path / "p"
    src.mkdir()
    (src / ".base.yaml").write_text("\n")
    existing = src.with_name(f"{src.name}.tgz")
    existing.write_text("collision\n")
    with pytest.raises(ValueError, match="target exists"):
        archive_service.archive_pack_internal(
            tmp_path,
            src,
            archive_require_dir=lambda _b, _s: None,
            base_marker_file=".base.yaml",
            packed_archive_name=lambda s: f"{s.name}.tgz",
            ensure_safe_cwd=lambda _b, _t: None,
            invalidate_packed_cache_path=lambda _p: None,
        )


def test_archive_unpack_internal_rejects_existing_target(tmp_path: Path) -> None:
    import pytest

    src = tmp_path / "p.tgz"
    src.write_bytes(b"")
    existing = tmp_path / "p"
    existing.mkdir()

    with pytest.raises(ValueError, match="target exists"):
        archive_service.archive_unpack_internal(
            tmp_path,
            src,
            archive_require_packed=lambda _b, _s: None,
            packed_archive_dir_name=lambda _p: "p",
            archive_extract_single_root=lambda *_a, **_k: (tmp_path, tmp_path),
            invalidate_packed_cache_path=lambda _p: None,
        )


def test_archive_unpack_internal_renames_root_to_target(tmp_path: Path) -> None:
    src = tmp_path / "p.tgz"
    src.write_bytes(b"")
    inner = tmp_path / "tmp_extract"
    inner.mkdir()
    root = inner / "root"
    root.mkdir()
    (root / "data.txt").write_text("hi\n")

    def fake_extract(_src: Path, _prefix: str, _parent: Path) -> tuple[Path, Path]:
        return inner, root

    out = archive_service.archive_unpack_internal(
        tmp_path,
        src,
        archive_require_packed=lambda _b, _s: None,
        packed_archive_dir_name=lambda _p: "p",
        archive_extract_single_root=fake_extract,
        invalidate_packed_cache_path=lambda _p: None,
    )
    assert out == tmp_path / "p"
    assert (out / "data.txt").read_text() == "hi\n"
    assert not src.exists()


def test_archive_restore_internal_renames_directory(tmp_path: Path) -> None:
    base = tmp_path / "base"
    arc_year = base / "_archive" / "2026"
    arc_year.mkdir(parents=True)
    src_dir = arc_year / "2026-01-01_p"
    src_dir.mkdir()
    (src_dir / "data.txt").write_text("x")
    target = base / "p"

    out = archive_service.archive_restore_internal(
        base,
        src_dir,
        archive_require_entry=lambda _b, _s: None,
        archived_restore_target=lambda _b, _s: target,
        normalize_restore_target=lambda _b, t, _allow: t,
        ensure_safe_cwd=lambda _b, _t: None,
        remove_placeholder_target=lambda _t: False,
        restore_target_exists_error_factory=lambda _s, _t: ValueError("conflict"),
        archive_extract_single_root=lambda *_a, **_k: (tmp_path, tmp_path),
        invalidate_packed_cache_path=lambda _p: None,
        sync_tags_if_needed=lambda _b, _s: None,
        target_override=None,
        sync_tags=False,
        allow_outside_base=False,
    )
    assert out == target
    assert (target / "data.txt").read_text() == "x"


def test_archive_restore_internal_raises_when_target_exists(tmp_path: Path) -> None:
    import pytest

    base = tmp_path / "base"
    base.mkdir()
    src_dir = base / "_archive" / "2026" / "2026-01-01_p"
    src_dir.mkdir(parents=True)
    target = base / "p"
    target.mkdir()
    (target / "blocker").write_text("collision")

    with pytest.raises(ValueError, match="conflict"):
        archive_service.archive_restore_internal(
            base,
            src_dir,
            archive_require_entry=lambda _b, _s: None,
            archived_restore_target=lambda _b, _s: target,
            normalize_restore_target=lambda _b, t, _allow: t,
            ensure_safe_cwd=lambda _b, _t: None,
            remove_placeholder_target=lambda _t: False,
            restore_target_exists_error_factory=lambda _s, _t: ValueError("conflict"),
            archive_extract_single_root=lambda *_a, **_k: (tmp_path, tmp_path),
            invalidate_packed_cache_path=lambda _p: None,
            sync_tags_if_needed=lambda _b, _s: None,
            target_override=None,
            sync_tags=False,
            allow_outside_base=False,
        )


def test_archive_restore_internal_extracts_packed_source(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    src = base / "_archive" / "2026" / "2026-01-01_p.tgz"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"placeholder")
    inner = tmp_path / "extracted"
    inner.mkdir()
    root = inner / "root"
    root.mkdir()
    (root / "f.txt").write_text("data")

    target = base / "p"

    def fake_extract(_src: Path, _prefix: str, _parent: Path) -> tuple[Path, Path]:
        return inner, root

    out = archive_service.archive_restore_internal(
        base,
        src,
        archive_require_entry=lambda _b, _s: None,
        archived_restore_target=lambda _b, _s: target,
        normalize_restore_target=lambda _b, t, _allow: t,
        ensure_safe_cwd=lambda _b, _t: None,
        remove_placeholder_target=lambda _t: False,
        restore_target_exists_error_factory=lambda _s, _t: ValueError("conflict"),
        archive_extract_single_root=fake_extract,
        invalidate_packed_cache_path=lambda _p: None,
        sync_tags_if_needed=lambda _b, _s: None,
        target_override=None,
        sync_tags=False,
        allow_outside_base=False,
    )
    assert out == target
    assert (target / "f.txt").read_text() == "data"
    assert not src.exists()


def test_delete_internal_unlinks_packed_file(tmp_path: Path) -> None:
    packed = tmp_path / "x.tgz"
    packed.write_bytes(b"")

    archive_service.delete_internal(
        tmp_path,
        packed,
        ensure_safe_cwd=lambda _b, _t: None,
        is_packed_archive_path=lambda _p: True,
        sync_tags_if_needed=lambda _b, _s: None,
        sync_tags=False,
    )
    assert not packed.exists()


def test_delete_internal_missing_path_raises(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError, match="not found"):
        archive_service.delete_internal(
            tmp_path,
            tmp_path / "ghost",
            ensure_safe_cwd=lambda _b, _t: None,
            is_packed_archive_path=lambda _p: False,
            sync_tags_if_needed=lambda _b, _s: None,
            sync_tags=False,
        )


def test_delete_internal_unsupported_target_raises(tmp_path: Path) -> None:
    import pytest

    other = tmp_path / "file.txt"
    other.write_text("hi")

    with pytest.raises(ValueError, match="unsupported"):
        archive_service.delete_internal(
            tmp_path,
            other,
            ensure_safe_cwd=lambda _b, _t: None,
            is_packed_archive_path=lambda _p: False,
            sync_tags_if_needed=lambda _b, _s: None,
            sync_tags=False,
        )
