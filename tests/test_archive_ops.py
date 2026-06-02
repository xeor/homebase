from __future__ import annotations

from pathlib import Path

from homebase.archive import ops as archive_ops


def test_archive_destination_uses_year_subdir(tmp_path: Path) -> None:
    base = tmp_path / "base"
    src = base / "proj"
    src.mkdir(parents=True)

    out = archive_ops.archive_destination(
        src,
        base,
        archive_dir_name="_archive",
        split_archive_name=lambda name: (name, 0),
        archive_iso_from_ts=lambda _ts: "ignored",
        archive_now_iso=lambda: "2025-01-15T00:00:00+00:00",
    )
    assert out == base / "_archive" / "2025" / "2025-01-15_proj"


def test_archive_destination_uses_parsed_year(tmp_path: Path) -> None:
    base = tmp_path / "base"
    src = base / "2020-03-04_proj"
    src.mkdir(parents=True)

    out = archive_ops.archive_destination(
        src,
        base,
        archive_dir_name="_archive",
        split_archive_name=lambda name: ("proj", 1583280000),
        archive_iso_from_ts=lambda _ts: "2020-03-04T00:00:00+00:00",
        archive_now_iso=lambda: "2099-01-01T00:00:00+00:00",
    )
    assert out == base / "_archive" / "2020" / "2020-03-04_proj"


def test_remove_placeholder_target(tmp_path: Path) -> None:
    target = tmp_path / "x"
    target.mkdir()
    (target / ".archived-placeholder").write_text("ok\n")
    assert archive_ops.remove_placeholder_target(target) is True
    assert not target.exists()


def test_remove_placeholder_target_missing_returns_false(tmp_path: Path) -> None:
    assert archive_ops.remove_placeholder_target(tmp_path / "missing") is False


def test_remove_placeholder_target_skips_if_extra_files(tmp_path: Path) -> None:
    target = tmp_path / "x"
    target.mkdir()
    (target / ".archived-placeholder").write_text("ok\n")
    (target / "other.txt").write_text("data\n")
    assert archive_ops.remove_placeholder_target(target) is False
    assert target.exists()


def test_remove_placeholder_target_returns_false_when_marker_missing(tmp_path: Path) -> None:
    target = tmp_path / "x"
    target.mkdir()
    assert archive_ops.remove_placeholder_target(target) is False


def test_ensure_safe_cwd_changes_dir_when_under_target(
    tmp_path: Path, monkeypatch
) -> None:
    base = tmp_path / "base"
    target = tmp_path / "base" / "proj"
    target.mkdir(parents=True)

    sub = target / "deep"
    sub.mkdir()
    monkeypatch.chdir(sub)

    archive_ops.ensure_safe_cwd(base, target, is_under=lambda a, b: True)
    assert Path.cwd() == base.resolve()


def test_ensure_safe_cwd_noop_when_outside_target(
    tmp_path: Path, monkeypatch
) -> None:
    base = tmp_path / "base"
    base.mkdir()
    target = tmp_path / "elsewhere"
    target.mkdir()
    monkeypatch.chdir(base)

    archive_ops.ensure_safe_cwd(base, target, is_under=lambda a, b: False)
    assert Path.cwd() == base.resolve()


def test_archive_extract_single_root_extracts_root(tmp_path: Path) -> None:
    import tarfile
    from io import BytesIO

    src = tmp_path / "p.tgz"
    payload = b"hello\n"
    with tarfile.open(src, "w:gz") as tf:
        info = tarfile.TarInfo("root/data.txt")
        info.size = len(payload)
        tf.addfile(info, fileobj=BytesIO(payload))

    def validate(_p: Path) -> list[tarfile.TarInfo]:
        return []

    def safe_extract(p: Path, dst: Path) -> None:
        with tarfile.open(p, "r:gz") as tf:
            tf.extractall(dst)

    tmp_dir, root = archive_ops.archive_extract_single_root(
        src,
        "test-",
        tmp_path,
        validate_tar_archive_members=validate,
        safe_extract_tar_to_dir=safe_extract,
    )
    assert root.is_dir()
    assert (root / "data.txt").read_bytes() == payload
    import shutil

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_archive_extract_single_root_rejects_multi_root(tmp_path: Path) -> None:
    import tarfile
    from io import BytesIO

    import pytest

    src = tmp_path / "multi.tgz"
    with tarfile.open(src, "w:gz") as tf:
        for name in ("a/f.txt", "b/f.txt"):
            info = tarfile.TarInfo(name)
            payload = b"x"
            info.size = len(payload)
            tf.addfile(info, fileobj=BytesIO(payload))

    def safe_extract(p: Path, dst: Path) -> None:
        with tarfile.open(p, "r:gz") as tf:
            tf.extractall(dst)

    with pytest.raises(ValueError, match="exactly one top-level root"):
        archive_ops.archive_extract_single_root(
            src,
            "test-",
            tmp_path,
            validate_tar_archive_members=lambda _p: [],
            safe_extract_tar_to_dir=safe_extract,
        )
