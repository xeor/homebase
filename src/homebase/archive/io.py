from __future__ import annotations

import tarfile
from pathlib import Path, PurePosixPath

from ..core.packed_meta import (
    invalidate_packed_cache_path,
    packed_read_base_data,
    packed_write_base_data,
)

__all__ = [
    "invalidate_packed_cache_path",
    "packed_read_base_data",
    "packed_write_base_data",
    "safe_extract_tar_to_dir",
    "tar_member_name_safe",
    "validate_tar_archive_members",
]


def tar_member_name_safe(name: str) -> bool:
    raw = str(name or "").strip()
    if not raw:
        return False
    posix_path = PurePosixPath(raw)
    if posix_path.is_absolute():
        return False
    parts = posix_path.parts
    if not parts:
        return False
    if any(part in {"", ".", ".."} for part in parts):
        return False
    return True


def validate_tar_archive_members(path: Path) -> list[tarfile.TarInfo]:
    safe: list[tarfile.TarInfo] = []
    with tarfile.open(path, "r:gz") as tf:
        for member in tf.getmembers():
            if not tar_member_name_safe(member.name):
                raise ValueError(f"unsafe archive member path: {member.name}")
            if member.isdev():
                raise ValueError(f"unsupported archive device entry: {member.name}")
            if (member.issym() or member.islnk()) and not tar_member_name_safe(member.linkname):
                raise ValueError(f"unsafe archive link target: {member.name} -> {member.linkname}")
            safe.append(member)
    return safe


def safe_extract_tar_to_dir(path: Path, target_dir: Path) -> None:
    members = validate_tar_archive_members(path)
    with tarfile.open(path, "r:gz") as tf:
        tf.extractall(
            target_dir,
            members=members,
            filter="data",
        )
