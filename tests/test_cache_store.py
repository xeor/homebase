from __future__ import annotations

import sqlite3
from pathlib import Path

from homebase.cache import store as cache_store


def test_cache_connect_applies_performance_pragmas(tmp_path: Path) -> None:
    conn = cache_store.cache_connect(tmp_path)
    try:
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]
        temp_store = conn.execute("PRAGMA temp_store").fetchone()[0]
        cache_size = conn.execute("PRAGMA cache_size").fetchone()[0]
        mmap_size = conn.execute("PRAGMA mmap_size").fetchone()[0]
    finally:
        conn.close()

    assert str(journal).lower() == "wal"
    assert int(synchronous) == 1  # NORMAL
    assert int(temp_store) == 2  # MEMORY
    assert int(cache_size) == -65536
    assert int(mmap_size) >= 268435456


def test_cache_store_and_load_rows(tmp_path: Path) -> None:
    payload = [
        (
            str(tmp_path / "a"),
            0,
            0,
            None,
            "a",
            "main",
            "",
            "-",
            "src",
            "created",
            "[]",
            "[]",
            "",
            0,
            0,
            0,
            0,
            0,
            0,
            None,
            0,
            0,
            None,
            0,
            0,
            1,
            1,
            "",
            "",
        )
    ]
    _ = cache_store.cache_store_rows(
        tmp_path,
        cache_schema_version=6,
        payload_rows=payload,
    )

    def deserialize(rec: sqlite3.Row, _age: int, _stale: bool) -> object | None:
        return str(rec["name"])

    active, archived, _ = cache_store.cache_load_rows(
        tmp_path,
        cache_schema_version=6,
        max_age_s=120,
        deserialize_row=deserialize,
    )
    assert active == ["a"]
    assert archived == []


def test_cache_reconcile_usage_roundtrip(tmp_path: Path) -> None:
    score = {Path("/tmp/p1"): 12.3}
    hits = {Path("/tmp/p1"): 7}
    last_used = {Path("/tmp/p1"): 100}
    cache_store.cache_save_reconcile_usage(
        tmp_path,
        cache_schema_version=6,
        score=score,
        hits=hits,
        last_used=last_used,
        limit=100,
    )
    loaded_score, loaded_hits, loaded_last_used = cache_store.cache_load_reconcile_usage(
        tmp_path,
        cache_schema_version=6,
    )
    path = Path("/tmp/p1")
    assert loaded_score[path] > 0
    assert loaded_hits[path] == 7
    assert loaded_last_used[path] == 100


def test_cache_opened_ts_roundtrip_and_move(tmp_path: Path) -> None:
    src = tmp_path / "a"
    dst = tmp_path / "b"

    cache_store.cache_set_opened_ts(
        tmp_path,
        cache_schema_version=6,
        path=src,
        opened_ts=123,
    )
    loaded = cache_store.cache_load_opened_map(tmp_path, cache_schema_version=6)
    assert loaded[src] == 123

    cache_store.cache_move_opened_ts(
        tmp_path,
        cache_schema_version=6,
        src=src,
        dst=dst,
    )
    loaded = cache_store.cache_load_opened_map(tmp_path, cache_schema_version=6)
    assert src not in loaded
    assert loaded[dst] == 123

    cache_store.cache_delete_opened_ts(
        tmp_path,
        cache_schema_version=6,
        path=dst,
    )
    loaded = cache_store.cache_load_opened_map(tmp_path, cache_schema_version=6)
    assert dst not in loaded


def _payload(path: Path, cached_at: int, name: str) -> tuple[object, ...]:
    return (
        str(path), 0, 0, None, name, "main", "", "-", "src", "created", "[]", "[]", "",
        0, 0, 0, 0, 0, 0, None, 0, 0, None, 0, 0, cached_at, cached_at, "", "",
    )


def _names(base: Path) -> dict[str, str]:
    conn = cache_store.cache_connect(base)
    try:
        return {r["path"]: r["name"] for r in conn.execute("SELECT path, name FROM project_cache")}
    finally:
        conn.close()


def test_cache_store_rows_merged_keeps_rows_written_during_scan(tmp_path: Path) -> None:
    a, b, gone = tmp_path / "a", tmp_path / "b", tmp_path / "gone"
    cache_store.cache_store_rows(
        tmp_path,
        cache_schema_version=6,
        payload_rows=[_payload(a, 100, "a-old"), _payload(b, 100, "b-old"), _payload(gone, 100, "gone")],
    )
    # Another process updates "b" after the scan started at ts=200.
    cache_store.cache_upsert_rows(
        tmp_path, cache_schema_version=6, payload_rows=[_payload(b, 250, "b-client")], touch_refresh_ts=False
    )
    ts = cache_store.cache_store_rows_merged(
        tmp_path,
        cache_schema_version=6,
        payload_rows=[_payload(a, 300, "a-scan"), _payload(b, 300, "b-scan")],
        scan_started_ts=200,
    )
    assert _names(tmp_path) == {str(a): "a-scan", str(b): "b-client"}
    assert cache_store.cache_read_meta_int(tmp_path, "full_scan_ts") == ts
    assert cache_store.cache_read_meta_int(tmp_path, "last_refresh_ts") == ts


def test_cache_read_meta_int_without_db(tmp_path: Path) -> None:
    assert cache_store.cache_read_meta_int(tmp_path, "last_refresh_ts") == 0


def test_packed_meta_round_trip_and_replace(tmp_path: Path) -> None:
    assert cache_store.cache_load_packed_meta(tmp_path, cache_schema_version=6) == []
    entries = [
        ("/a.tgz", 1, 10, ".base.yaml", "tags: [x]\n"),
        ("/b.tgz", 2, 20, None, None),
    ]
    cache_store.cache_save_packed_meta(tmp_path, cache_schema_version=6, entries=entries)
    cache_store.cache_save_packed_meta(tmp_path, cache_schema_version=6, entries=[])
    assert sorted(cache_store.cache_load_packed_meta(tmp_path, cache_schema_version=6)) == entries
    # Same path, new stat key: replaced, not duplicated.
    cache_store.cache_save_packed_meta(
        tmp_path, cache_schema_version=6, entries=[("/a.tgz", 3, 11, "x/.base.yaml", "tags: []\n")]
    )
    loaded = dict((e[0], e) for e in cache_store.cache_load_packed_meta(tmp_path, cache_schema_version=6))
    assert loaded["/a.tgz"] == ("/a.tgz", 3, 11, "x/.base.yaml", "tags: []\n")
    assert len(loaded) == 2
