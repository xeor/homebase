from __future__ import annotations

from pathlib import Path

from homebase.archive import service as archive_service


def test_archive_move_internal_moves_directory(tmp_path: Path) -> None:
    base = tmp_path / "base"
    src = base / "p"
    dst = base / "_archive" / "p.2025"
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
