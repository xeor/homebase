from __future__ import annotations

from pathlib import Path

from ..archive import ops as archive_ops
from ..cache import queue as queue_utils
from ..cache.api import cache_load_opened_map
from ..core import utils as core_utils
from ..core.constants import (
    ARCHIVE_DIR_NAME,
    ARCHIVE_TZ,
    BASE_MARKER_FILE,
    PACKED_ARCHIVE_SUFFIX,
    SORT_MODE_SPECS,
)
from ..core.models import ProjectRow
from . import discovery as discovery_utils
from . import discovery_helpers, filter_compile
from .projects import classify_name, project_row, refresh_row_caches

_FILTER_TOKEN_RE = filter_compile._FILTER_TOKEN_RE


def _resolve_include_nested(base_dir: Path, include_nested: bool | None) -> bool:
    return discovery_helpers.resolve_include_nested(base_dir, include_nested)


def _discovery_zone_depth(base_dir: Path, path: Path) -> tuple[str, int]:
    return discovery_helpers.discovery_zone_depth(base_dir, path)


def _discovery_marker_allowed(
    base_dir: Path,
    marker_dir: Path,
    include_nested: bool | None,
) -> bool:
    return discovery_helpers.discovery_marker_allowed(base_dir, marker_dir, include_nested)


def _discovery_has_marker_ancestor(base_dir: Path, marker_dir: Path) -> bool:
    return discovery_helpers.discovery_has_marker_ancestor(base_dir, marker_dir)


def reconcile_queue_push(
    queue: list[tuple[int, str, str, list[Path]]],
    mode: str,
    reason: str,
    paths: list[Path],
    priority: int,
    limit: int = 40,
) -> list[tuple[int, str, str, list[Path]]]:
    return queue_utils.reconcile_queue_push(
        queue,
        mode,
        reason,
        paths,
        priority,
        limit=limit,
    )


def reconcile_queue_pop_next(
    queue: list[tuple[int, str, str, list[Path]]],
    worker_running: bool,
) -> tuple[
    list[tuple[int, str, str, list[Path]]], tuple[int, str, str, list[Path]] | None
]:
    return queue_utils.reconcile_queue_pop_next(
        queue,
        worker_running=worker_running,
    )


def _discovery_prune_walk_dirnames(dirnames: list[str]) -> None:
    discovery_helpers.discovery_prune_walk_dirnames(dirnames)


def _discovery_should_skip_active_walk_path(
    base_dir: Path,
    archive_root: Path,
    cur: Path,
) -> bool:
    return discovery_helpers.discovery_should_skip_active_walk_path(base_dir, archive_root, cur)


def collect_workspace_rows(
    base_dir: Path,
    include_git_dirty: bool = True,
    include_nested: bool | None = None,
    size_cache: dict[Path, tuple[int, int]] | None = None,
) -> tuple[list[ProjectRow], list[ProjectRow]]:
    opened_ts_map = cache_load_opened_map(base_dir)
    nested = _resolve_include_nested(base_dir, include_nested)
    active = collect_projects(
        base_dir,
        include_git_dirty=include_git_dirty,
        include_nested=nested,
        size_cache=size_cache,
        opened_ts_map=opened_ts_map,
    )
    archived = collect_archived(
        base_dir,
        include_git_dirty=include_git_dirty,
        include_nested=nested,
        size_cache=size_cache,
        opened_ts_map=opened_ts_map,
    )
    return active, archived


def collect_projects(
    base_dir: Path,
    include_git_dirty: bool = True,
    include_nested: bool | None = None,
    size_cache: dict[Path, tuple[int, int]] | None = None,
    opened_ts_map: dict[Path, int] | None = None,
) -> list[ProjectRow]:
    opened_map = opened_ts_map if opened_ts_map is not None else cache_load_opened_map(base_dir)

    def _project_row_with_opened(path: Path, **kwargs: object) -> ProjectRow:
        opened_ts = int(opened_map.get(path, 0))
        if opened_ts <= 0:
            try:
                opened_ts = int(opened_map.get(path.resolve(), 0))
            except (OSError, RuntimeError, ValueError):
                opened_ts = 0
        opened_ts = max(0, opened_ts)
        return project_row(path, opened_ts_override=opened_ts, **kwargs)

    rows = discovery_utils.collect_projects(
        base_dir,
        include_git_dirty=include_git_dirty,
        include_nested=include_nested,
        size_cache=size_cache,
        archive_dir_name=ARCHIVE_DIR_NAME,
        base_marker_file=BASE_MARKER_FILE,
        resolve_include_nested_fn=_resolve_include_nested,
        skip_active_walk_path=_discovery_should_skip_active_walk_path,
        prune_walk_dirnames=_discovery_prune_walk_dirnames,
        project_row=_project_row_with_opened,
    )
    return [row for row in rows if isinstance(row, ProjectRow)]


def archived_restore_target(base_dir: Path, archived_path: Path) -> Path:
    rel = archived_path.relative_to(base_dir / ARCHIVE_DIR_NAME)
    name = (
        core_utils.packed_archive_dir_name(rel, PACKED_ARCHIVE_SUFFIX)
        if str(rel).endswith(PACKED_ARCHIVE_SUFFIX)
        else rel.name
    )
    stem, ts = core_utils.split_archive_name(
        name,
        parse_timestamp=lambda value: core_utils.parse_archive_timestamp(value, ARCHIVE_TZ),
    )
    if ts > 0:
        rel = rel.with_name(stem)
    elif str(rel).endswith(PACKED_ARCHIVE_SUFFIX):
        rel = rel.with_name(name)
    return base_dir / rel


def collect_archived(
    base_dir: Path,
    include_git_dirty: bool = True,
    include_nested: bool | None = None,
    size_cache: dict[Path, tuple[int, int]] | None = None,
    opened_ts_map: dict[Path, int] | None = None,
) -> list[ProjectRow]:
    opened_map = opened_ts_map if opened_ts_map is not None else cache_load_opened_map(base_dir)

    def _project_row_with_opened(path: Path, **kwargs: object) -> ProjectRow:
        opened_ts = int(opened_map.get(path, 0))
        if opened_ts <= 0:
            try:
                opened_ts = int(opened_map.get(path.resolve(), 0))
            except (OSError, RuntimeError, ValueError):
                opened_ts = 0
        opened_ts = max(0, opened_ts)
        return project_row(path, opened_ts_override=opened_ts, **kwargs)

    rows = discovery_utils.collect_archived(
        base_dir,
        include_git_dirty=include_git_dirty,
        include_nested=include_nested,
        size_cache=size_cache,
        archive_dir_name=ARCHIVE_DIR_NAME,
        base_marker_file=BASE_MARKER_FILE,
        packed_archive_suffix=PACKED_ARCHIVE_SUFFIX,
        resolve_include_nested_fn=_resolve_include_nested,
        marker_allowed=_discovery_marker_allowed,
        has_marker_ancestor=_discovery_has_marker_ancestor,
        split_archive_entry_name=lambda path: core_utils.split_archive_entry_name(
            path,
            packed_archive_suffix=PACKED_ARCHIVE_SUFFIX,
            parse_timestamp=lambda value: core_utils.parse_archive_timestamp(
                value,
                ARCHIVE_TZ,
            ),
        ),
        archived_restore_target=archived_restore_target,
        project_row=_project_row_with_opened,
        classify_name=classify_name,
        refresh_row_caches=refresh_row_caches,
    )
    return [row for row in rows if isinstance(row, ProjectRow)]


def sort_rows(rows: list[ProjectRow], mode: str) -> list[ProjectRow]:
    if mode == "archived":
        return sorted(rows, key=lambda r: (r.archived_ts, r.last_ts), reverse=True)
    if mode == "created":
        return sorted(rows, key=lambda r: (r.created_ts, r.last_ts), reverse=True)
    if mode == "opened":
        return sorted(rows, key=lambda r: (r.opened_ts, r.last_ts), reverse=True)
    if mode == "restore_to":
        return sorted(
            rows,
            key=lambda r: ((str(r.restore_target or "").lower()), r.name.lower()),
        )
    if mode == "tags":
        return sorted(
            rows,
            key=lambda r: (
                ",".join(sorted(str(t).lower() for t in r.tags)),
                r.name.lower(),
            ),
        )
    if mode == "properties":
        return sorted(
            rows,
            key=lambda r: (
                ",".join(sorted(str(p).lower() for p in r.properties)),
                r.name.lower(),
            ),
        )
    if mode == "description":
        return sorted(rows, key=lambda r: (str(r.description).lower(), r.name.lower()))
    if mode == "size":
        return sorted(rows, key=lambda r: (int(r.size_bytes), r.name.lower()), reverse=True)
    if mode == "name":
        return sorted(rows, key=lambda r: r.name.lower())
    if mode == "git":
        return sorted(rows, key=lambda r: (r.git_ts, r.last_ts), reverse=True)
    return sorted(rows, key=lambda r: r.last_ts, reverse=True)


def _sort_modes_for_view(view_mode: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    vm = str(view_mode).strip()
    for spec in SORT_MODE_SPECS:
        sid = str(spec.get("id", "")).strip()
        label = str(spec.get("label", sid)).strip() or sid
        views = [str(v) for v in spec.get("views", [])]
        if sid and vm in views:
            out.append((sid, label))
    return out


def _normalize_sort_mode_for_view(view_mode: str, sort_mode: str) -> str:
    vm = str(view_mode).strip()
    sm = str(sort_mode).strip()
    allowed = {sid for sid, _label in _sort_modes_for_view(vm)}
    if sm in allowed:
        return sm
    return "last"


def match_query(row: ProjectRow, query: str) -> bool:
    return filter_compile.match_query(row, query)


def compile_filter_expr(expr: str):
    return filter_compile.compile_filter_expr(expr)


def query_uses_filter_syntax(text: str) -> bool:
    return filter_compile.query_uses_filter_syntax(text)


def normalize_filter_expression(expr: str) -> str:
    return filter_compile.normalize_filter_expression(expr)


def pretty_filter_expression(expr: str) -> str:
    return filter_compile.pretty_filter_expression(expr)


def resolve_archive_prefix(src: Path, base_dir: Path) -> str:
    return archive_ops.resolve_archive_prefix(src, base_dir)


def archive_destination(src: Path, base_dir: Path) -> Path:
    return archive_ops.archive_destination(
        src,
        base_dir,
        archive_dir_name=ARCHIVE_DIR_NAME,
        split_archive_name=lambda name: core_utils.split_archive_name(
            name,
            parse_timestamp=lambda value: core_utils.parse_archive_timestamp(
                value,
                ARCHIVE_TZ,
            ),
        ),
        archive_iso_from_ts=lambda ts: core_utils.archive_iso_from_ts(ts, ARCHIVE_TZ),
        archive_now_iso=lambda: core_utils.archive_now_iso(ARCHIVE_TZ),
    )
