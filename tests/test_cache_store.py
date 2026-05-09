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
        )
    ]
    _ = cache_store.cache_store_rows(
        tmp_path,
        cache_schema_version=5,
        payload_rows=payload,
    )

    def deserialize(rec: sqlite3.Row, _age: int, _stale: bool) -> object | None:
        return str(rec["name"])

    active, archived, _ = cache_store.cache_load_rows(
        tmp_path,
        cache_schema_version=5,
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
        cache_schema_version=5,
        score=score,
        hits=hits,
        last_used=last_used,
        limit=100,
    )
    loaded_score, loaded_hits, loaded_last_used = cache_store.cache_load_reconcile_usage(
        tmp_path,
        cache_schema_version=5,
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
        cache_schema_version=5,
        path=src,
        opened_ts=123,
    )
    loaded = cache_store.cache_load_opened_map(tmp_path, cache_schema_version=5)
    assert loaded[src] == 123

    cache_store.cache_move_opened_ts(
        tmp_path,
        cache_schema_version=5,
        src=src,
        dst=dst,
    )
    loaded = cache_store.cache_load_opened_map(tmp_path, cache_schema_version=5)
    assert src not in loaded
    assert loaded[dst] == 123

    cache_store.cache_delete_opened_ts(
        tmp_path,
        cache_schema_version=5,
        path=dst,
    )
    loaded = cache_store.cache_load_opened_map(tmp_path, cache_schema_version=5)
    assert dst not in loaded
