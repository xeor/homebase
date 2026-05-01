from __future__ import annotations

import tarfile
from io import BytesIO
from pathlib import Path

import yaml

from homebase.archive import io as archive_io


def _write_packed(path: Path, data: dict[str, object]) -> None:
    payload = yaml.safe_dump(data, sort_keys=False, default_flow_style=False).encode("utf-8")
    with tarfile.open(path, "w:gz") as tf:
        info = tarfile.TarInfo(name=".base.yml")
        info.size = len(payload)
        tf.addfile(info, fileobj=BytesIO(payload))


def test_packed_read_write_roundtrip(tmp_path: Path) -> None:
    archive_path = tmp_path / "project.base-pkg.tgz"
    _write_packed(archive_path, {"tags": ["a"]})

    loaded = archive_io.packed_read_base_data(archive_path, base_marker_file=".base.yml")
    assert loaded.get("tags") == ["a"]

    archive_io.packed_write_base_data(
        archive_path,
        {"tags": ["b"], "wip": True},
        base_marker_file=".base.yml",
    )
    loaded2 = archive_io.packed_read_base_data(archive_path, base_marker_file=".base.yml")
    assert loaded2.get("tags") == ["b"]
    assert loaded2.get("wip") is True


def test_tar_member_name_safe_rejects_parent_segments() -> None:
    assert archive_io.tar_member_name_safe("ok/path.txt") is True
    assert archive_io.tar_member_name_safe("../bad") is False
