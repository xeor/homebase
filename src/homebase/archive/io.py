from __future__ import annotations

import io
import os
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath

import yaml

_PACKED_META_MEMBER_CACHE: dict[tuple[str, int, int], str | None] = {}
_PACKED_META_MEMBER_CACHE_ORDER: list[tuple[str, int, int]] = []
_PACKED_BASE_DATA_CACHE: dict[tuple[str, int, int], dict[str, object]] = {}
_PACKED_BASE_DATA_CACHE_ORDER: list[tuple[str, int, int]] = []
_PACKED_CACHE_LIMIT = 1024


def _packed_cache_key(path: Path) -> tuple[str, int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (str(path.resolve()), int(st.st_mtime_ns), int(st.st_size))


def invalidate_packed_cache_path(path: Path) -> None:
    target = str(path.resolve())
    for key in list(_PACKED_META_MEMBER_CACHE.keys()):
        if key[0] == target:
            _PACKED_META_MEMBER_CACHE.pop(key, None)
    for key in list(_PACKED_BASE_DATA_CACHE.keys()):
        if key[0] == target:
            _PACKED_BASE_DATA_CACHE.pop(key, None)


def _packed_cache_put_member(key: tuple[str, int, int], member: str | None) -> None:
    _PACKED_META_MEMBER_CACHE[key] = member
    _PACKED_META_MEMBER_CACHE_ORDER.append(key)
    if len(_PACKED_META_MEMBER_CACHE_ORDER) > _PACKED_CACHE_LIMIT:
        old = _PACKED_META_MEMBER_CACHE_ORDER.pop(0)
        _PACKED_META_MEMBER_CACHE.pop(old, None)


def _packed_cache_put_data(key: tuple[str, int, int], data: dict[str, object]) -> None:
    _PACKED_BASE_DATA_CACHE[key] = dict(data)
    _PACKED_BASE_DATA_CACHE_ORDER.append(key)
    if len(_PACKED_BASE_DATA_CACHE_ORDER) > _PACKED_CACHE_LIMIT:
        old = _PACKED_BASE_DATA_CACHE_ORDER.pop(0)
        _PACKED_BASE_DATA_CACHE.pop(old, None)


def _packed_member_for_meta(path: Path, *, base_marker_file: str) -> str | None:
    key = _packed_cache_key(path)
    if key is not None and key in _PACKED_META_MEMBER_CACHE:
        return _PACKED_META_MEMBER_CACHE.get(key)

    found: str | None = None
    try:
        with tarfile.open(path, "r:gz") as tf:
            fallback: str | None = None
            for member in tf:
                if not member.isfile():
                    continue
                name = member.name
                if name == base_marker_file:
                    found = name
                    break
                if name.endswith(f"/{base_marker_file}") and fallback is None:
                    fallback = name
            if found is None:
                found = fallback
    except (OSError, tarfile.TarError):
        found = None

    if key is not None:
        _packed_cache_put_member(key, found)
    return found


def packed_read_base_data(path: Path, *, base_marker_file: str) -> dict[str, object]:
    key = _packed_cache_key(path)
    if key is not None and key in _PACKED_BASE_DATA_CACHE:
        return dict(_PACKED_BASE_DATA_CACHE[key])

    member = _packed_member_for_meta(path, base_marker_file=base_marker_file)
    if not member:
        if key is not None:
            _packed_cache_put_data(key, {})
        return {}
    try:
        with tarfile.open(path, "r:gz") as tf:
            file_obj = tf.extractfile(member)
            if file_obj is None:
                if key is not None:
                    _packed_cache_put_data(key, {})
                return {}
            raw = file_obj.read().decode("utf-8", errors="replace")
            data = yaml.safe_load(raw)
            out = data if isinstance(data, dict) else {}
            if key is not None:
                _packed_cache_put_data(key, out)
            return dict(out)
    except (OSError, tarfile.TarError, UnicodeDecodeError, yaml.YAMLError):
        if key is not None:
            _packed_cache_put_data(key, {})
        return {}


def packed_write_base_data(
    path: Path,
    data: dict[str, object],
    *,
    base_marker_file: str,
) -> None:
    invalidate_packed_cache_path(path)
    member = _packed_member_for_meta(path, base_marker_file=base_marker_file)
    if not member:
        raise ValueError(f"missing {base_marker_file} in packed archive")
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=".pkg-meta-", suffix=".tgz", dir=str(path.parent))
    os.close(tmp_fd)
    tmp_path = Path(tmp_name)
    try:
        payload = yaml.safe_dump(data, sort_keys=False, default_flow_style=False).encode("utf-8")
        with tarfile.open(path, "r:gz") as src, tarfile.open(tmp_path, "w:gz") as dst:
            for member_info in src.getmembers():
                if member_info.name == member:
                    info = tarfile.TarInfo(name=member_info.name)
                    info.size = len(payload)
                    info.mtime = int(time.time())
                    info.mode = member_info.mode
                    info.type = tarfile.REGTYPE
                    dst.addfile(info, io.BytesIO(payload))
                    continue
                if not member_info.isfile():
                    dst.addfile(member_info)
                    continue
                file_obj = src.extractfile(member_info)
                if file_obj is None:
                    dst.addfile(member_info)
                else:
                    dst.addfile(member_info, file_obj)
        tmp_path.replace(path)
        invalidate_packed_cache_path(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


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
        tf.extractall(target_dir, members=members)
