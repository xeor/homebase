from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from homebase.core import packed_meta


@pytest.fixture(autouse=True)
def _clean_memo() -> None:
    for store in (
        packed_meta._PACKED_META_MEMBER_CACHE,
        packed_meta._PACKED_BASE_DATA_CACHE,
        packed_meta._PACKED_SEED,
        packed_meta._PACKED_NEW,
    ):
        store.clear()


def _tgz(path: Path, members: dict[str, str]) -> Path:
    with tarfile.open(path, "w:gz") as tf:
        for name, text in members.items():
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return path


def _forget_process_cache() -> None:
    packed_meta._PACKED_META_MEMBER_CACHE.clear()
    packed_meta._PACKED_BASE_DATA_CACHE.clear()


def test_read_records_new_entry_and_seed_avoids_unpacking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _tgz(tmp_path / "p.tgz", {"p/readme": "x", "p/.base.yaml": "tags: [a]\n"})
    assert packed_meta.packed_read_base_data(archive, base_marker_file=".base.yaml") == {"tags": ["a"]}
    entries = packed_meta.packed_meta_take_new()
    assert len(entries) == 1
    path, _mtime, size, member, raw = entries[0]
    assert (path, size, member, raw) == (str(archive.resolve()), archive.stat().st_size, "p/.base.yaml", "tags: [a]\n")
    assert packed_meta.packed_meta_take_new() == []

    # A new process: seeded from the persisted entry, no archive read.
    _forget_process_cache()
    packed_meta.packed_meta_seed(entries)

    def no_open(*_a: object, **_k: object) -> None:
        raise AssertionError("archive opened despite seed")

    monkeypatch.setattr(packed_meta.tarfile, "open", no_open)
    assert packed_meta.packed_read_base_data(archive, base_marker_file=".base.yaml") == {"tags": ["a"]}
    assert packed_meta.packed_meta_take_new() == []


def test_archive_without_marker_is_remembered_as_empty(tmp_path: Path) -> None:
    archive = _tgz(tmp_path / "q.tgz", {"q/readme": "x"})
    assert packed_meta.packed_read_base_data(archive, base_marker_file=".base.yaml") == {}
    entries = packed_meta.packed_meta_take_new()
    assert [(e[3], e[4]) for e in entries] == [(None, None)]
    _forget_process_cache()
    packed_meta.packed_meta_seed(entries)
    assert packed_meta.packed_read_base_data(archive, base_marker_file=".base.yaml") == {}


def test_seed_with_stale_stat_key_is_ignored(tmp_path: Path) -> None:
    archive = _tgz(tmp_path / "r.tgz", {"r/.base.yaml": "tags: [new]\n"})
    packed_meta.packed_meta_seed([(str(archive.resolve()), 1, 1, "r/.base.yaml", "tags: [old]\n")])
    assert packed_meta.packed_read_base_data(archive, base_marker_file=".base.yaml") == {"tags": ["new"]}


def test_invalid_seeded_yaml_reads_as_empty(tmp_path: Path) -> None:
    archive = _tgz(tmp_path / "s.tgz", {"s/.base.yaml": "tags: [a]\n"})
    st = archive.stat()
    packed_meta.packed_meta_seed([(str(archive.resolve()), st.st_mtime_ns, st.st_size, "s/.base.yaml", "a: [")])
    assert packed_meta.packed_read_base_data(archive, base_marker_file=".base.yaml") == {}


def test_write_invalidates_seed(tmp_path: Path) -> None:
    archive = _tgz(tmp_path / "t.tgz", {"t/.base.yaml": "tags: [a]\n"})
    st = archive.stat()
    packed_meta.packed_meta_seed([(str(archive.resolve()), st.st_mtime_ns, st.st_size, "t/.base.yaml", "tags: [a]\n")])
    packed_meta.packed_write_base_data(archive, {"tags": ["b"]}, base_marker_file=".base.yaml")
    assert packed_meta._PACKED_SEED == {}
    assert packed_meta.packed_read_base_data(archive, base_marker_file=".base.yaml") == {"tags": ["b"]}
