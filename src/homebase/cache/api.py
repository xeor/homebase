from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Callable

from ..core.constants import (
    CACHE_MAX_AGE_S,
    CACHE_SCHEMA_VERSION,
    RECONCILE_USAGE_CACHE_LIMIT,
)
from ..core.models import ProjectRow
from . import store as cache_store


def _identity_normalize(keys: list[str]) -> list[str]:
    return list(keys)


def _empty_haystack(**_kwargs: object) -> str:
    return ""


def cache_db_path(base_dir: Path) -> Path:
    return cache_store.cache_db_path(base_dir)


def _cache_connect(base_dir: Path) -> sqlite3.Connection:
    return cache_store.cache_connect(base_dir)


def _cache_init(conn: sqlite3.Connection) -> None:
    cache_store.cache_init(conn, cache_schema_version=CACHE_SCHEMA_VERSION)


def cache_load_rows(
    base_dir: Path,
    max_age_s: int = CACHE_MAX_AGE_S,
    *,
    normalize_property_keys: Callable[[list[str]], list[str]] = _identity_normalize,
    build_row_haystack_lower: Callable[..., str] = _empty_haystack,
) -> tuple[list[ProjectRow], list[ProjectRow], int]:
    opened_map = cache_store.cache_load_opened_map(
        base_dir,
        cache_schema_version=CACHE_SCHEMA_VERSION,
    )

    def _opened_ts_for_path(path: Path) -> int:
        ts = int(opened_map.get(path, 0))
        if ts > 0:
            return ts
        try:
            return max(0, int(opened_map.get(path.resolve(), 0)))
        except (OSError, RuntimeError, ValueError):
            return 0

    def _deserialize_cache_row(
        rec: sqlite3.Row,
        age: int,
        stale: bool,
    ) -> ProjectRow | None:
        try:
            p = Path(str(rec["path"]))
            restore_raw = rec["restore_target"]
            restore_target = Path(str(restore_raw)) if restore_raw else None
            cached_at = int(rec["cached_at"])
            reconciled_at = int(rec["reconciled_at"])
            name = str(rec["name"])
            branch = str(rec["branch"])
            description = str(rec["description"])
            tags = [str(x) for x in json.loads(str(rec["tags_json"]))]
            properties = normalize_property_keys(
                [str(x) for x in json.loads(str(rec["properties_json"]))]
            )
            haystack_lower = build_row_haystack_lower(
                name=name,
                description=description,
                tags=tags,
                properties=properties,
                branch=branch,
                path=p,
            )
            row = ProjectRow(
                path=p,
                name=name,
                branch=branch,
                dirty=str(rec["dirty"]),
                last=str(rec["last"]),
                src=str(rec["src"]),
                created=str(rec["created"]),
                tags=tags,
                properties=properties,
                description=description,
                created_ts=int(rec["created_ts"]),
                last_ts=int(rec["last_ts"]),
                git_ts=int(rec["git_ts"]),
                opened_ts=int(rec["opened_ts"]),
                is_fork=bool(rec["is_fork"]),
                is_tmp=bool(rec["is_tmp"]),
                archived=bool(rec["archived"]),
                packed=bool(rec["packed"]),
                pack_format=(
                    str(rec["pack_format"]) if rec["pack_format"] is not None else None
                ),
                restore_target=restore_target,
                archived_ts=int(rec["archived_ts"]),
                wip=bool(rec["wip"]),
                suffix=(str(rec["suffix"]) if rec["suffix"] is not None else None),
                size_bytes=max(0, int(rec["size_bytes"])),
                size_refresh_count=max(0, int(rec["size_refresh_count"])),
                stale=stale,
                cache_age_s=age,
                last_cached_ts=cached_at,
                last_reconciled_ts=reconciled_at,
                haystack_lower=haystack_lower,
                worktree_of=str(rec["worktree_of"] or ""),
                repo_dir=str(rec["repo_dir"] or ""),
            )
            row.opened_ts = _opened_ts_for_path(p)
            return row
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    active_rows, archived_rows, last_refresh_ts = cache_store.cache_load_rows(
        base_dir,
        cache_schema_version=CACHE_SCHEMA_VERSION,
        max_age_s=max_age_s,
        deserialize_row=_deserialize_cache_row,
    )
    return (
        [row for row in active_rows if isinstance(row, ProjectRow)],
        [row for row in archived_rows if isinstance(row, ProjectRow)],
        last_refresh_ts,
    )


def cache_store_rows(
    base_dir: Path, active_rows: list[ProjectRow], archived_rows: list[ProjectRow]
) -> int:
    now_ts = int(time.time())
    payload_rows = [_cache_row_payload(row, now_ts) for row in (active_rows + archived_rows)]
    return cache_store.cache_store_rows(
        base_dir,
        cache_schema_version=CACHE_SCHEMA_VERSION,
        payload_rows=payload_rows,
    )


def _cache_row_payload(row: ProjectRow, cached_at: int) -> tuple[object, ...]:
    reconciled_at = int(row.last_reconciled_ts or cached_at)
    return (
        str(row.path),
        1 if row.archived else 0,
        1 if row.packed else 0,
        row.pack_format,
        row.name,
        row.branch,
        row.dirty,
        row.last,
        row.src,
        row.created,
        json.dumps(row.tags),
        json.dumps(row.properties),
        row.description,
        row.created_ts,
        row.last_ts,
        row.git_ts,
        row.opened_ts,
        1 if row.is_fork else 0,
        1 if row.is_tmp else 0,
        str(row.restore_target) if row.restore_target is not None else None,
        row.archived_ts,
        1 if row.wip else 0,
        row.suffix,
        max(0, int(row.size_bytes)),
        max(0, int(row.size_refresh_count)),
        cached_at,
        reconciled_at,
        row.worktree_of,
        row.repo_dir,
    )


def cache_upsert_rows(
    base_dir: Path, rows: list[ProjectRow], touch_refresh_ts: bool = False
) -> int:
    now_ts = int(time.time())
    payload_rows = [_cache_row_payload(row, now_ts) for row in rows]
    return cache_store.cache_upsert_rows(
        base_dir,
        cache_schema_version=CACHE_SCHEMA_VERSION,
        payload_rows=payload_rows,
        touch_refresh_ts=touch_refresh_ts,
    )


def cache_delete_paths(
    base_dir: Path, paths: list[Path], touch_refresh_ts: bool = False
) -> int:
    return cache_store.cache_delete_paths(
        base_dir,
        cache_schema_version=CACHE_SCHEMA_VERSION,
        paths=paths,
        touch_refresh_ts=touch_refresh_ts,
    )


def cache_load_reconcile_usage(
    base_dir: Path,
) -> tuple[dict[Path, float], dict[Path, int], dict[Path, int]]:
    return cache_store.cache_load_reconcile_usage(
        base_dir,
        cache_schema_version=CACHE_SCHEMA_VERSION,
    )


def cache_save_reconcile_usage(
    base_dir: Path,
    score: dict[Path, float],
    hits: dict[Path, int],
    last_used: dict[Path, int],
) -> None:
    cache_store.cache_save_reconcile_usage(
        base_dir,
        cache_schema_version=CACHE_SCHEMA_VERSION,
        score=score,
        hits=hits,
        last_used=last_used,
        limit=RECONCILE_USAGE_CACHE_LIMIT,
    )


def cache_load_opened_map(base_dir: Path) -> dict[Path, int]:
    return cache_store.cache_load_opened_map(
        base_dir,
        cache_schema_version=CACHE_SCHEMA_VERSION,
    )


def cache_set_opened_ts(base_dir: Path, path: Path, opened_ts: int) -> None:
    cache_store.cache_set_opened_ts(
        base_dir,
        cache_schema_version=CACHE_SCHEMA_VERSION,
        path=path,
        opened_ts=opened_ts,
    )


def cache_move_opened_ts(base_dir: Path, src: Path, dst: Path) -> None:
    cache_store.cache_move_opened_ts(
        base_dir,
        cache_schema_version=CACHE_SCHEMA_VERSION,
        src=src,
        dst=dst,
    )


def cache_delete_opened_ts(base_dir: Path, path: Path) -> None:
    cache_store.cache_delete_opened_ts(
        base_dir,
        cache_schema_version=CACHE_SCHEMA_VERSION,
        path=path,
    )


def cache_load_worktree_health(
    base_dir: Path,
) -> tuple[int, list[dict[str, object]]] | None:
    return cache_store.cache_load_worktree_health(
        base_dir,
        cache_schema_version=CACHE_SCHEMA_VERSION,
    )


def cache_save_worktree_health(
    base_dir: Path,
    scan_at: int,
    issues: list[dict[str, object]],
) -> None:
    cache_store.cache_save_worktree_health(
        base_dir,
        scan_at,
        issues,
        cache_schema_version=CACHE_SCHEMA_VERSION,
    )


def cache_load_worktree_health_rows(
    base_dir: Path,
) -> dict[str, tuple[str, int, list[dict[str, object]]]]:
    return cache_store.cache_load_worktree_health_rows(
        base_dir,
        cache_schema_version=CACHE_SCHEMA_VERSION,
    )


def cache_upsert_worktree_health_row(
    base_dir: Path,
    path: str,
    inputs_sig: str,
    scan_at: int,
    issues: list[dict[str, object]],
) -> None:
    cache_store.cache_upsert_worktree_health_row(
        base_dir,
        path,
        inputs_sig,
        scan_at,
        issues,
        cache_schema_version=CACHE_SCHEMA_VERSION,
    )


def cache_prune_worktree_health_rows(
    base_dir: Path,
    keep_paths: set[str],
) -> None:
    cache_store.cache_prune_worktree_health_rows(
        base_dir,
        keep_paths,
        cache_schema_version=CACHE_SCHEMA_VERSION,
    )
