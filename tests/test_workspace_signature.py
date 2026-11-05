from __future__ import annotations

from pathlib import Path

from homebase.workspace.signature import workspace_quick_signature


def test_workspace_quick_signature_includes_active_and_archive(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base"
    base.mkdir()
    (base / "alpha").mkdir()
    (base / "beta").mkdir()
    (base / "_hidden").mkdir()  # excluded — leading underscore
    (base / "_archive" / "2026").mkdir(parents=True)
    (base / "_archive" / "2026-01-01_p.tgz").write_text("")

    out = workspace_quick_signature(
        base_dir=base,
        archive_dir_name="_archive",
        packed_archive_suffix=".tgz",
    )
    assert out.startswith("active:")
    assert "archive:" in out


def test_workspace_quick_signature_handles_missing_archive(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    out = workspace_quick_signature(
        base_dir=base,
        archive_dir_name="_archive",
        packed_archive_suffix=".tgz",
    )
    assert "archive:0" in out


def test_workspace_quick_signature_handles_missing_base(tmp_path: Path) -> None:
    out = workspace_quick_signature(
        base_dir=tmp_path / "nope",
        archive_dir_name="_archive",
        packed_archive_suffix=".tgz",
    )
    assert "active:err" in out
