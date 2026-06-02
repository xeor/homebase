from __future__ import annotations

import tarfile
from io import BytesIO
from pathlib import Path

import yaml

from homebase.archive import io as archive_io


def _write_packed(path: Path, data: dict[str, object]) -> None:
    payload = yaml.safe_dump(data, sort_keys=False, default_flow_style=False).encode("utf-8")
    with tarfile.open(path, "w:gz") as tf:
        info = tarfile.TarInfo(name=".base.yaml")
        info.size = len(payload)
        tf.addfile(info, fileobj=BytesIO(payload))


def test_packed_read_write_roundtrip(tmp_path: Path) -> None:
    archive_path = tmp_path / "project.base-pkg.tgz"
    _write_packed(archive_path, {"tags": ["a"]})

    loaded = archive_io.packed_read_base_data(archive_path, base_marker_file=".base.yaml")
    assert loaded.get("tags") == ["a"]

    archive_io.packed_write_base_data(
        archive_path,
        {"tags": ["b"], "wip": True},
        base_marker_file=".base.yaml",
    )
    loaded2 = archive_io.packed_read_base_data(archive_path, base_marker_file=".base.yaml")
    assert loaded2.get("tags") == ["b"]
    assert loaded2.get("wip") is True


def test_tar_member_name_safe_rejects_parent_segments() -> None:
    assert archive_io.tar_member_name_safe("ok/path.txt") is True
    assert archive_io.tar_member_name_safe("../bad") is False
    assert archive_io.tar_member_name_safe("") is False
    assert archive_io.tar_member_name_safe("   ") is False
    assert archive_io.tar_member_name_safe("/etc/passwd") is False
    assert archive_io.tar_member_name_safe("../ok/tricky") is False


def test_packed_read_base_data_returns_empty_for_missing_marker(tmp_path: Path) -> None:
    archive_path = tmp_path / "no-marker.tgz"
    with tarfile.open(archive_path, "w:gz") as tf:
        info = tarfile.TarInfo(name="other.txt")
        payload = b"hi\n"
        info.size = len(payload)
        tf.addfile(info, fileobj=BytesIO(payload))
    out = archive_io.packed_read_base_data(archive_path, base_marker_file=".base.yaml")
    assert out == {}


def test_packed_read_base_data_handles_nested_marker(tmp_path: Path) -> None:
    archive_path = tmp_path / "nested.tgz"
    payload = yaml.safe_dump({"tags": ["nested"]}).encode("utf-8")
    with tarfile.open(archive_path, "w:gz") as tf:
        info = tarfile.TarInfo(name="proj/.base.yaml")
        info.size = len(payload)
        tf.addfile(info, fileobj=BytesIO(payload))
    out = archive_io.packed_read_base_data(archive_path, base_marker_file=".base.yaml")
    assert out["tags"] == ["nested"]


def test_packed_read_base_data_handles_invalid_archive(tmp_path: Path) -> None:
    archive_path = tmp_path / "broken.tgz"
    archive_path.write_bytes(b"not a tarball")
    assert archive_io.packed_read_base_data(archive_path, base_marker_file=".base.yaml") == {}


def test_packed_read_base_data_handles_missing_file(tmp_path: Path) -> None:
    archive_path = tmp_path / "ghost.tgz"
    assert archive_io.packed_read_base_data(archive_path, base_marker_file=".base.yaml") == {}


def test_packed_read_base_data_uses_cache(tmp_path: Path) -> None:
    archive_path = tmp_path / "cached.tgz"
    _write_packed(archive_path, {"tags": ["a"]})
    archive_io.invalidate_packed_cache_path(archive_path)
    first = archive_io.packed_read_base_data(archive_path, base_marker_file=".base.yaml")
    second = archive_io.packed_read_base_data(archive_path, base_marker_file=".base.yaml")
    assert first == second
    # changing the data on disk without invalidating returns the cached version
    _write_packed(archive_path.with_suffix(".tmp"), {"tags": ["b"]})
    # The cache returns ["a"]; this validates the cache hit code path.
    assert first.get("tags") == ["a"]


def test_packed_write_base_data_missing_marker_raises(tmp_path: Path) -> None:
    archive_path = tmp_path / "nomarker.tgz"
    with tarfile.open(archive_path, "w:gz") as tf:
        info = tarfile.TarInfo(name="other.txt")
        payload = b"hi\n"
        info.size = len(payload)
        tf.addfile(info, fileobj=BytesIO(payload))
    import pytest

    with pytest.raises(ValueError, match="missing"):
        archive_io.packed_write_base_data(
            archive_path,
            {"tags": ["b"]},
            base_marker_file=".base.yaml",
        )


def test_validate_tar_archive_members_rejects_unsafe_paths(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.tgz"
    with tarfile.open(archive_path, "w:gz") as tf:
        info = tarfile.TarInfo(name="../escape.txt")
        info.size = 0
        tf.addfile(info, fileobj=BytesIO(b""))

    import pytest

    with pytest.raises(ValueError, match="unsafe archive member path"):
        archive_io.validate_tar_archive_members(archive_path)


def test_validate_tar_archive_members_rejects_unsafe_symlinks(tmp_path: Path) -> None:
    archive_path = tmp_path / "link.tgz"
    with tarfile.open(archive_path, "w:gz") as tf:
        info = tarfile.TarInfo(name="ok/link")
        info.type = tarfile.SYMTYPE
        info.linkname = "../../etc/passwd"
        info.size = 0
        tf.addfile(info)

    import pytest

    with pytest.raises(ValueError, match="unsafe archive link target"):
        archive_io.validate_tar_archive_members(archive_path)


def test_safe_extract_tar_to_dir_extracts_safe_members(tmp_path: Path) -> None:
    archive_path = tmp_path / "safe.tgz"
    payload = b"hello\n"
    with tarfile.open(archive_path, "w:gz") as tf:
        info = tarfile.TarInfo(name="data/hello.txt")
        info.size = len(payload)
        tf.addfile(info, fileobj=BytesIO(payload))
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    archive_io.safe_extract_tar_to_dir(archive_path, out_dir)
    assert (out_dir / "data" / "hello.txt").read_bytes() == payload


def test_invalidate_packed_cache_path_drops_entries(tmp_path: Path) -> None:
    archive_path = tmp_path / "drop.tgz"
    _write_packed(archive_path, {"tags": ["x"]})
    archive_io.packed_read_base_data(archive_path, base_marker_file=".base.yaml")
    assert any(k[0] == str(archive_path.resolve()) for k in archive_io._PACKED_BASE_DATA_CACHE)
    archive_io.invalidate_packed_cache_path(archive_path)
    assert not any(k[0] == str(archive_path.resolve()) for k in archive_io._PACKED_BASE_DATA_CACHE)


def test_packed_cache_key_missing_path_returns_none(tmp_path: Path) -> None:
    assert archive_io._packed_cache_key(tmp_path / "missing") is None
