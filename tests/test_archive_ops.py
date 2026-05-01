from __future__ import annotations

from pathlib import Path

from homebase.archive import ops as archive_ops


def test_archive_destination_uses_prefix(tmp_path: Path) -> None:
    base = tmp_path / "base"
    src = base / "team" / "proj"
    src.mkdir(parents=True)
    (src / ".archive_prefix").write_text("alpha")

    out = archive_ops.archive_destination(
        src,
        base,
        archive_dir_name="_archive",
        split_archive_name=lambda name: (name, 0),
        archive_iso_from_ts=lambda _ts: "ignored",
        archive_now_iso=lambda: "2025-01-01T00:00:00+00:00",
    )
    assert out == base / "_archive" / "team" / "alpha" / "proj.2025-01-01T00:00:00+00:00"


def test_remove_placeholder_target(tmp_path: Path) -> None:
    target = tmp_path / "x"
    target.mkdir()
    (target / ".archived-placeholder").write_text("ok\n")
    assert archive_ops.remove_placeholder_target(target) is True
    assert not target.exists()
