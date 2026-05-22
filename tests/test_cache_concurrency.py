from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from homebase.cache import concurrency as cache_concurrency
from homebase.cache import store as cache_store


@pytest.fixture(autouse=True)
def _reset_concurrency_state() -> None:
    cache_concurrency.reset()
    yield
    cache_concurrency.reset()


def _seed_v5_cache(tmp_path: Path) -> None:
    conn = cache_store.cache_connect(tmp_path)
    try:
        conn.execute(
            """
            CREATE TABLE cache_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE project_cache (
                path TEXT PRIMARY KEY,
                archived INTEGER NOT NULL,
                packed INTEGER NOT NULL,
                pack_format TEXT,
                name TEXT NOT NULL,
                branch TEXT NOT NULL,
                dirty TEXT NOT NULL,
                last TEXT NOT NULL,
                src TEXT NOT NULL,
                created TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                properties_json TEXT NOT NULL,
                description TEXT NOT NULL,
                created_ts INTEGER NOT NULL,
                last_ts INTEGER NOT NULL,
                git_ts INTEGER NOT NULL,
                opened_ts INTEGER NOT NULL,
                is_fork INTEGER NOT NULL,
                is_tmp INTEGER NOT NULL,
                restore_target TEXT,
                archived_ts INTEGER NOT NULL,
                wip INTEGER NOT NULL,
                suffix TEXT,
                size_bytes INTEGER NOT NULL,
                size_refresh_count INTEGER NOT NULL,
                cached_at INTEGER NOT NULL,
                reconciled_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO cache_meta(key, value) VALUES('schema_version', '5')"
        )
        conn.execute(
            """
            INSERT INTO project_cache(
                path, archived, packed, pack_format, name, branch, dirty,
                last, src, created, tags_json, properties_json, description,
                created_ts, last_ts, git_ts, opened_ts, is_fork, is_tmp,
                restore_target, archived_ts, wip, suffix, size_bytes,
                size_refresh_count, cached_at, reconciled_at
            ) VALUES(?, 0, 0, NULL, 'a', 'main', '', '-', 'src', 'created',
                '[]', '[]', '', 0, 0, 0, 0, 0, 0, NULL, 0, 0, NULL, 0, 0, 1, 1)
            """,
            (str(tmp_path / "a"),),
        )
        conn.commit()
    finally:
        conn.close()


def test_v5_to_v6_migration_preserves_rows(tmp_path: Path) -> None:
    _seed_v5_cache(tmp_path)

    conn = cache_store.cache_connect(tmp_path)
    try:
        cache_store.cache_init(conn, cache_schema_version=6)
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(project_cache)").fetchall()
        }
        version = conn.execute(
            "SELECT value FROM cache_meta WHERE key='schema_version'"
        ).fetchone()[0]
        rows = conn.execute("SELECT path, name FROM project_cache").fetchall()
    finally:
        conn.close()

    assert "worktree_of" in cols
    assert "repo_dir" in cols
    assert str(version) == "6"
    # Pre-existing rows must survive the migration.
    assert len(rows) == 1
    assert rows[0]["name"] == "a"


def test_init_never_drops_when_newer_owns_schema(tmp_path: Path) -> None:
    # Pretend a future b@v7 owns the schema and has rows we cannot lose.
    cache_store.cache_store_rows(
        tmp_path,
        cache_schema_version=6,
        payload_rows=[
            (
                str(tmp_path / "alpha"),
                0,
                0,
                None,
                "alpha",
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
        ],
    )
    conn = cache_store.cache_connect(tmp_path)
    try:
        conn.execute(
            "UPDATE cache_meta SET value='7' WHERE key='schema_version'"
        )
        conn.commit()
    finally:
        conn.close()

    # An older b@v6 starts up. Its cache_init must not drop the row
    # nor downgrade the schema_version.
    cache_concurrency.reset()
    cache_concurrency.record_set(6)
    conn = cache_store.cache_connect(tmp_path)
    try:
        cache_store.cache_init(conn, cache_schema_version=6)
        rows = conn.execute("SELECT path FROM project_cache").fetchall()
        version = conn.execute(
            "SELECT value FROM cache_meta WHERE key='schema_version'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert len(rows) == 1
    assert str(version) == "7"

    snap = cache_concurrency.snapshot()
    assert snap.drift_count == 1
    assert snap.last_event is not None
    assert snap.last_event.kind == "newer_present"
    assert snap.last_event.observed_version == 7
    assert snap.last_event.expected_version == 6


def test_init_records_drift_when_older_overwrites_schema(tmp_path: Path) -> None:
    # Simulate a v6 b that has set up the cache, then an older b@v5
    # process flips schema back to 5.
    conn = cache_store.cache_connect(tmp_path)
    try:
        cache_store.cache_init(conn, cache_schema_version=6)
    finally:
        conn.close()
    assert cache_concurrency.snapshot().drift_count == 0

    conn = cache_store.cache_connect(tmp_path)
    try:
        conn.execute(
            "UPDATE cache_meta SET value='5' WHERE key='schema_version'"
        )
        conn.commit()
    finally:
        conn.close()

    # Next cache_init call must observe the drift, re-apply migration,
    # and log an event.
    conn = cache_store.cache_connect(tmp_path)
    try:
        cache_store.cache_init(conn, cache_schema_version=6)
        version = conn.execute(
            "SELECT value FROM cache_meta WHERE key='schema_version'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert str(version) == "6"

    snap = cache_concurrency.snapshot()
    assert snap.drift_count == 1
    assert snap.last_event is not None
    assert snap.last_event.kind == "older_present"
    assert snap.last_event.observed_version == 5
    assert snap.last_event.expected_version == 6


def test_first_run_migration_is_not_flagged_as_drift(tmp_path: Path) -> None:
    # A pre-existing v5 cache being upgraded for the first time by v6
    # is legitimate, not drift. Drift requires that we (this process)
    # had previously written the expected version.
    _seed_v5_cache(tmp_path)

    conn = cache_store.cache_connect(tmp_path)
    try:
        cache_store.cache_init(conn, cache_schema_version=6)
    finally:
        conn.close()

    snap = cache_concurrency.snapshot()
    assert snap.drift_count == 0
    assert snap.last_event is None
    assert snap.last_set_version == 6


def test_unknown_migration_path_raises(tmp_path: Path) -> None:
    conn = cache_store.cache_connect(tmp_path)
    try:
        conn.execute(
            """
            CREATE TABLE cache_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE TABLE project_cache (path TEXT PRIMARY KEY)"
        )
        conn.execute(
            "INSERT INTO cache_meta(key, value) VALUES('schema_version', '3')"
        )
        conn.commit()
    finally:
        conn.close()

    conn = cache_store.cache_connect(tmp_path)
    try:
        with pytest.raises(sqlite3.Error):
            cache_store.cache_init(conn, cache_schema_version=6)
    finally:
        conn.close()
