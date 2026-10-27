"""Read/write the ``.base.yaml`` member of a packed (``.tgz``) archive.

Sits in ``core`` so both ``archive`` and ``metadata`` can use it
without violating the layering rules. Stdlib + PyYAML only."""
from __future__ import annotations

import io
import os
import tarfile
import tempfile
import threading
import time
from pathlib import Path

import yaml

from .yaml_io import yaml_safe_load

_PACKED_META_MEMBER_CACHE: dict[tuple[str, int, int], str | None] = {}
_PACKED_META_MEMBER_CACHE_ORDER: list[tuple[str, int, int]] = []
_PACKED_BASE_DATA_CACHE: dict[tuple[str, int, int], dict[str, object]] = {}
_PACKED_BASE_DATA_CACHE_ORDER: list[tuple[str, int, int]] = []
_PACKED_CACHE_LIMIT = 1024

# Persistent memo (stored by the cache layer, seeded per process): finding
# the metadata member means reading most of the archive, which for a few
# hundred archives costs many seconds per new process.
PackedMetaEntry = tuple[str, int, int, str | None, str | None]
_PACKED_SEED: dict[tuple[str, int, int], tuple[str | None, str | None]] = {}
_PACKED_NEW: dict[tuple[str, int, int], tuple[str | None, str | None]] = {}
_PACKED_MEMO_LOCK = threading.Lock()


def packed_meta_seed(entries: list[PackedMetaEntry]) -> None:
    """Load (path, mtime_ns, size, member, raw yaml) entries read earlier."""
    with _PACKED_MEMO_LOCK:
        for path, mtime_ns, size, member, raw in entries:
            _PACKED_SEED[(str(path), int(mtime_ns), int(size))] = (member, raw)


def packed_meta_take_new() -> list[PackedMetaEntry]:
    """Entries read from archives since the last call, for persisting."""
    with _PACKED_MEMO_LOCK:
        out = [(k[0], k[1], k[2], m, r) for k, (m, r) in _PACKED_NEW.items()]
        _PACKED_NEW.clear()
    return out


def _packed_memo_record(
    key: tuple[str, int, int] | None, member: str | None, raw: str | None
) -> None:
    if key is None:
        return
    with _PACKED_MEMO_LOCK:
        _PACKED_NEW[key] = (member, raw)


def _parse_packed_raw(raw: str | None) -> dict[str, object]:
    if raw is None:
        return {}
    try:
        data = yaml_safe_load(raw)
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _packed_cache_key(path: Path) -> tuple[str, int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (str(path.resolve()), int(st.st_mtime_ns), int(st.st_size))


def invalidate_packed_cache_path(path: Path) -> None:
    target = str(path.resolve())
    with _PACKED_MEMO_LOCK:
        for key in [k for k in _PACKED_SEED if k[0] == target]:
            _PACKED_SEED.pop(key, None)
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


def _remember_empty(key: tuple[str, int, int] | None) -> None:
    if key is not None:
        _packed_cache_put_data(key, {})
        _packed_memo_record(key, None, None)


def _seeded_base_data(key: tuple[str, int, int] | None) -> dict[str, object] | None:
    seeded = _PACKED_SEED.get(key) if key is not None else None
    if key is None or seeded is None:
        return None
    _packed_cache_put_member(key, seeded[0])
    data = _parse_packed_raw(seeded[1])
    _packed_cache_put_data(key, data)
    return dict(data)


def packed_read_base_data(path: Path, *, base_marker_file: str) -> dict[str, object]:
    key = _packed_cache_key(path)
    if key is not None and key in _PACKED_BASE_DATA_CACHE:
        return dict(_PACKED_BASE_DATA_CACHE[key])
    seeded_data = _seeded_base_data(key)
    if seeded_data is not None:
        return seeded_data

    member = _packed_member_for_meta(path, base_marker_file=base_marker_file)
    if not member:
        _remember_empty(key)
        return {}
    try:
        with tarfile.open(path, "r:gz") as tf:
            file_obj = tf.extractfile(member)
            if file_obj is None:
                if key is not None:
                    _packed_cache_put_data(key, {})
                return {}
            raw = file_obj.read().decode("utf-8", errors="replace")
            data = yaml_safe_load(raw)
            out = data if isinstance(data, dict) else {}
            if key is not None:
                _packed_cache_put_data(key, out)
                _packed_memo_record(key, member, raw)
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
