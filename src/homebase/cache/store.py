from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

from ..core.constants import CACHE_DB_FILE_NAME, HOMEBASE_DIR_NAME

PROJECT_CACHE_INSERT_SQL = (
    "INSERT OR REPLACE INTO project_cache("
    "path, archived, packed, pack_format, name, branch, dirty, last, src, created, tags_json, properties_json, "
    "description, created_ts, last_ts, git_ts, opened_ts, is_fork, is_tmp, restore_target, archived_ts, wip, suffix, size_bytes, size_refresh_count, cached_at, reconciled_at"
    ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def _path_candidates(path: Path) -> tuple[str, ...]:
    raw = str(path)
    try:
        resolved = str(path.resolve())
    except (OSError, RuntimeError, ValueError):
        resolved = raw
    if resolved == raw:
        return (raw,)
    return (raw, resolved)


def cache_db_path(base_dir: Path) -> Path:
    return base_dir / HOMEBASE_DIR_NAME / CACHE_DB_FILE_NAME


def cache_connect(base_dir: Path) -> sqlite3.Connection:
    db = cache_db_path(base_dir)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=2500")
    return conn


def cache_init(conn: sqlite3.Connection, *, cache_schema_version: int) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cache_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    ver_row = conn.execute("SELECT value FROM cache_meta WHERE key='schema_version'").fetchone()
    cur_ver = int(str(ver_row[0])) if ver_row and str(ver_row[0]).isdigit() else 0
    if cur_ver != cache_schema_version:
        conn.execute("DROP TABLE IF EXISTS project_cache")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_cache (
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_cache_archived ON project_cache(archived)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_cache_last_ts ON project_cache(last_ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_cache_wip ON project_cache(wip)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_opened (
            path TEXT PRIMARY KEY,
            opened_ts INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO cache_meta(key, value) VALUES('schema_version', ?)",
        (str(cache_schema_version),),
    )
    conn.commit()


def cache_load_opened_map(
    base_dir: Path,
    *,
    cache_schema_version: int,
) -> dict[Path, int]:
    db = cache_db_path(base_dir)
    if not db.is_file():
        return {}
    try:
        conn = cache_connect(base_dir)
        cache_init(conn, cache_schema_version=cache_schema_version)
        rows = conn.execute("SELECT path, opened_ts FROM project_opened").fetchall()
        conn.close()
    except sqlite3.Error:
        return {}
    out: dict[Path, int] = {}
    for rec in rows:
        try:
            ts = max(0, int(rec["opened_ts"]))
            out[Path(str(rec["path"]))] = ts
        except (TypeError, ValueError, KeyError):
            continue
    return out


def cache_set_opened_ts(
    base_dir: Path,
    *,
    cache_schema_version: int,
    path: Path,
    opened_ts: int,
) -> None:
    conn = cache_connect(base_dir)
    cache_init(conn, cache_schema_version=cache_schema_version)
    key = _path_candidates(path)[-1]
    conn.execute(
        "INSERT OR REPLACE INTO project_opened(path, opened_ts) VALUES(?, ?)",
        (key, max(0, int(opened_ts))),
    )
    conn.commit()
    conn.close()


def cache_move_opened_ts(
    base_dir: Path,
    *,
    cache_schema_version: int,
    src: Path,
    dst: Path,
) -> None:
    conn = cache_connect(base_dir)
    cache_init(conn, cache_schema_version=cache_schema_version)
    row = None
    for src_key in _path_candidates(src):
        row = conn.execute(
            "SELECT opened_ts FROM project_opened WHERE path = ?",
            (src_key,),
        ).fetchone()
        if row is not None:
            break
    if row is not None:
        dst_key = _path_candidates(dst)[-1]
        conn.execute(
            "INSERT OR REPLACE INTO project_opened(path, opened_ts) VALUES(?, ?)",
            (dst_key, max(0, int(row["opened_ts"]))),
        )
        for src_key in _path_candidates(src):
            conn.execute("DELETE FROM project_opened WHERE path = ?", (src_key,))
    conn.commit()
    conn.close()


def cache_delete_opened_ts(
    base_dir: Path,
    *,
    cache_schema_version: int,
    path: Path,
) -> None:
    conn = cache_connect(base_dir)
    cache_init(conn, cache_schema_version=cache_schema_version)
    for key in _path_candidates(path):
        conn.execute("DELETE FROM project_opened WHERE path = ?", (key,))
    conn.commit()
    conn.close()


def cache_load_rows(
    base_dir: Path,
    *,
    cache_schema_version: int,
    max_age_s: int,
    deserialize_row: Callable[[sqlite3.Row, int, bool], object | None],
) -> tuple[list[object], list[object], int]:
    db = cache_db_path(base_dir)
    if not db.is_file():
        return [], [], 0

    try:
        conn = cache_connect(base_dir)
    except (OSError, sqlite3.Error):
        return [], [], 0

    try:
        cache_init(conn, cache_schema_version=cache_schema_version)
        rows = conn.execute(
            """
            SELECT path, archived, name, branch, dirty, last, src, created,
                   packed, pack_format,
                   tags_json, properties_json, description, created_ts, last_ts, git_ts, opened_ts,
                   is_fork, is_tmp, restore_target, archived_ts, wip, suffix, size_bytes, size_refresh_count, cached_at, reconciled_at
            FROM project_cache
            """
        ).fetchall()
        last_refresh_val = conn.execute(
            "SELECT value FROM cache_meta WHERE key='last_refresh_ts'"
        ).fetchone()
    except sqlite3.Error:
        conn.close()
        return [], [], 0
    conn.close()

    now_ts = int(time.time())
    active: list[object] = []
    archived: list[object] = []
    last_refresh_ts = int(str(last_refresh_val[0])) if last_refresh_val and str(last_refresh_val[0]).isdigit() else 0
    for rec in rows:
        try:
            cached_at = int(rec["cached_at"])
        except (TypeError, ValueError, KeyError):
            continue
        age = max(0, now_ts - cached_at)
        stale = age > max_age_s
        row = deserialize_row(rec, age, stale)
        if row is None:
            continue
        if bool(rec["archived"]):
            archived.append(row)
        else:
            active.append(row)
    return active, archived, last_refresh_ts


def cache_store_rows(
    base_dir: Path,
    *,
    cache_schema_version: int,
    payload_rows: list[tuple[object, ...]],
) -> int:
    now_ts = int(time.time())
    conn = cache_connect(base_dir)
    cache_init(conn, cache_schema_version=cache_schema_version)
    conn.execute("DELETE FROM project_cache")
    if payload_rows:
        conn.executemany(PROJECT_CACHE_INSERT_SQL, payload_rows)
    conn.execute(
        "INSERT OR REPLACE INTO cache_meta(key, value) VALUES('last_refresh_ts', ?)",
        (str(now_ts),),
    )
    conn.commit()
    conn.close()
    return now_ts


def cache_upsert_rows(
    base_dir: Path,
    *,
    cache_schema_version: int,
    payload_rows: list[tuple[object, ...]],
    touch_refresh_ts: bool,
) -> int:
    now_ts = int(time.time())
    if not payload_rows:
        return now_ts
    conn = cache_connect(base_dir)
    cache_init(conn, cache_schema_version=cache_schema_version)
    conn.executemany(PROJECT_CACHE_INSERT_SQL, payload_rows)
    if touch_refresh_ts:
        conn.execute(
            "INSERT OR REPLACE INTO cache_meta(key, value) VALUES('last_refresh_ts', ?)",
            (str(now_ts),),
        )
    conn.commit()
    conn.close()
    return now_ts


def cache_delete_paths(
    base_dir: Path,
    *,
    cache_schema_version: int,
    paths: list[Path],
    touch_refresh_ts: bool,
) -> int:
    now_ts = int(time.time())
    if not paths:
        return now_ts
    conn = cache_connect(base_dir)
    cache_init(conn, cache_schema_version=cache_schema_version)
    conn.executemany("DELETE FROM project_cache WHERE path = ?", [(str(path),) for path in paths])
    if touch_refresh_ts:
        conn.execute(
            "INSERT OR REPLACE INTO cache_meta(key, value) VALUES('last_refresh_ts', ?)",
            (str(now_ts),),
        )
    conn.commit()
    conn.close()
    return now_ts


def cache_load_reconcile_usage(
    base_dir: Path,
    *,
    cache_schema_version: int,
) -> tuple[dict[Path, float], dict[Path, int], dict[Path, int]]:
    db = cache_db_path(base_dir)
    if not db.is_file():
        return {}, {}, {}
    try:
        conn = cache_connect(base_dir)
        cache_init(conn, cache_schema_version=cache_schema_version)
        row = conn.execute("SELECT value FROM cache_meta WHERE key='reconcile_usage_json'").fetchone()
        conn.close()
    except sqlite3.Error:
        return {}, {}, {}
    if not row:
        return {}, {}, {}

    raw = str(row[0])
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}, {}, {}
    if not isinstance(data, dict):
        return {}, {}, {}

    score: dict[Path, float] = {}
    hits: dict[Path, int] = {}
    last_used: dict[Path, int] = {}
    for path_raw, payload in data.items():
        try:
            path = Path(str(path_raw))
        except (TypeError, ValueError):
            continue

        if isinstance(payload, dict):
            s_raw = payload.get("score", 0.0)
            h_raw = payload.get("hits", 0)
            t_raw = payload.get("last_used_ts", 0)
        else:
            s_raw = payload
            h_raw = 0
            t_raw = 0

        try:
            score_value = float(s_raw)
        except (TypeError, ValueError):
            score_value = 0.0
        if score_value <= 0:
            continue

        try:
            hits_value = max(0, int(h_raw))
        except (TypeError, ValueError):
            hits_value = 0
        try:
            ts_value = max(0, int(t_raw))
        except (TypeError, ValueError):
            ts_value = 0

        score[path] = min(1000.0, score_value)
        hits[path] = hits_value
        last_used[path] = ts_value
    return score, hits, last_used


def cache_save_reconcile_usage(
    base_dir: Path,
    *,
    cache_schema_version: int,
    score: dict[Path, float],
    hits: dict[Path, int],
    last_used: dict[Path, int],
    limit: int,
) -> None:
    if not score:
        return

    ranked = sorted(score.items(), key=lambda kv: (-float(kv[1]), str(kv[0])))
    payload: dict[str, dict[str, object]] = {}
    for path, score_value in ranked[:limit]:
        if score_value <= 0:
            continue
        payload[str(path)] = {
            "score": round(float(score_value), 3),
            "hits": int(max(0, hits.get(path, 0))),
            "last_used_ts": int(max(0, last_used.get(path, 0))),
        }

    try:
        conn = cache_connect(base_dir)
        cache_init(conn, cache_schema_version=cache_schema_version)
        conn.execute(
            "INSERT OR REPLACE INTO cache_meta(key, value) VALUES('reconcile_usage_json', ?)",
            (json.dumps(payload, sort_keys=True),),
        )
        conn.commit()
        conn.close()
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return
