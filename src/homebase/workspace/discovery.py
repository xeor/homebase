from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path


def resolve_include_nested(
    base_dir: Path,
    include_nested: bool | None,
    *,
    nested_discovery_enabled: Callable[[Path], bool],
) -> bool:
    if include_nested is None:
        return nested_discovery_enabled(base_dir)
    return bool(include_nested)


def discovery_zone_depth(
    base_dir: Path,
    path: Path,
    *,
    archive_dir_name: str,
    mode_archive: str,
    mode_active: str,
) -> tuple[str, int]:
    rel = path.resolve().relative_to(base_dir.resolve())
    if rel.parts and rel.parts[0] == archive_dir_name:
        return mode_archive, max(0, len(rel.parts) - 1)
    return mode_active, len(rel.parts)


def discovery_marker_allowed(
    base_dir: Path,
    marker_dir: Path,
    include_nested: bool | None,
    *,
    zone_depth: Callable[[Path, Path], tuple[str, int]],
    resolve_include_nested_fn: Callable[[Path, bool | None], bool],
) -> bool:
    _zone, depth = zone_depth(base_dir, marker_dir)
    if depth <= 1:
        return True
    return resolve_include_nested_fn(base_dir, include_nested)


def discovery_has_marker_ancestor(base_dir: Path, marker_dir: Path, *, base_marker_file: str) -> bool:
    base_res = base_dir.resolve()
    cur = marker_dir.resolve().parent
    while cur != base_res and cur != cur.parent:
        if (cur / base_marker_file).is_file():
            return True
        cur = cur.parent
    return False


def discovery_prune_walk_dirnames(dirnames: list[str], *, prune_names: set[str]) -> None:
    pruned: list[str] = []
    for name in dirnames:
        if name in prune_names:
            continue
        if name.startswith(".") or name.startswith("_"):
            continue
        pruned.append(name)
    dirnames[:] = sorted(pruned)


def discovery_should_skip_active_walk_path(
    base_dir: Path,
    archive_root: Path,
    cur: Path,
    *,
    is_under: Callable[[Path, Path], bool],
) -> bool:
    base_res = base_dir.resolve()
    if cur == archive_root or is_under(cur, archive_root):
        return True
    if cur == base_res:
        return False
    try:
        rel_parts = cur.relative_to(base_res).parts
    except (OSError, ValueError):
        return False
    return bool(
        rel_parts
        and (
            rel_parts[0] == "_tags"
            or any(part.startswith(".") or part.startswith("_") for part in rel_parts)
        )
    )


def collect_projects(
    base_dir: Path,
    *,
    include_git_dirty: bool,
    include_nested: bool | None,
    size_cache: dict[Path, tuple[int, int]] | None,
    archive_dir_name: str,
    base_marker_file: str,
    resolve_include_nested_fn: Callable[[Path, bool | None], bool],
    skip_active_walk_path: Callable[[Path, Path, Path], bool],
    prune_walk_dirnames: Callable[[list[str]], None],
    project_row: Callable[..., object],
) -> list[object]:
    rows: list[object] = []
    seen: set[Path] = set()
    archive_root = (base_dir / archive_dir_name).resolve()
    base_res = base_dir.resolve()

    for p in sorted(base_dir.iterdir()):
        try:
            if not p.is_dir():
                continue
        except OSError:
            continue
        name = p.name
        if name.startswith(".") or name.startswith("_"):
            continue
        project_dir = p.resolve()
        if project_dir == base_res or project_dir in seen:
            continue
        seen.add(project_dir)
        size_prev = (size_cache or {}).get(project_dir)
        prev_size = int(size_prev[0]) if size_prev is not None else None
        prev_count = int(size_prev[1]) if size_prev is not None else 0
        rows.append(
            project_row(
                project_dir,
                include_git_dirty=include_git_dirty,
                prev_size_bytes=prev_size,
                prev_size_refresh_count=prev_count,
            )
        )

    nested = resolve_include_nested_fn(base_dir, include_nested)
    if not nested:
        return rows

    for dirpath, dirnames, filenames in os.walk(base_dir, topdown=True):
        cur = Path(dirpath).resolve()
        if skip_active_walk_path(base_dir, archive_root, cur):
            dirnames[:] = []
            continue
        prune_walk_dirnames(dirnames)
        if base_marker_file not in filenames:
            continue
        if cur == base_res:
            continue
        if cur in seen:
            dirnames[:] = []
            continue
        seen.add(cur)
        size_prev = (size_cache or {}).get(cur)
        prev_size = int(size_prev[0]) if size_prev is not None else None
        prev_count = int(size_prev[1]) if size_prev is not None else 0
        rows.append(
            project_row(
                cur,
                include_git_dirty=include_git_dirty,
                prev_size_bytes=prev_size,
                prev_size_refresh_count=prev_count,
            )
        )
        dirnames[:] = []
    return rows


def collect_archived(
    base_dir: Path,
    *,
    include_git_dirty: bool,
    include_nested: bool | None,
    size_cache: dict[Path, tuple[int, int]] | None,
    archive_dir_name: str,
    base_marker_file: str,
    packed_archive_suffix: str,
    resolve_include_nested_fn: Callable[[Path, bool | None], bool],
    marker_allowed: Callable[[Path, Path, bool | None], bool],
    has_marker_ancestor: Callable[[Path, Path], bool],
    split_archive_entry_name: Callable[[Path], tuple[str, int]],
    archived_restore_target: Callable[[Path, Path], Path],
    project_row: Callable[..., object],
    classify_name: Callable[[str], tuple[bool, bool, str | None]],
) -> list[object]:
    rows: list[object] = []
    root = base_dir / archive_dir_name
    if not root.is_dir():
        return rows
    nested = resolve_include_nested_fn(base_dir, include_nested)

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        cur = Path(dirpath)
        dirnames.sort()
        filenames.sort()

        if base_marker_file in filenames:
            if not marker_allowed(base_dir, cur, nested):
                dirnames[:] = []
                continue
            if has_marker_ancestor(base_dir, cur):
                dirnames[:] = []
                continue
            stem, archived_ts = split_archive_entry_name(cur)
            restore = archived_restore_target(base_dir, cur)
            cur_res = cur.resolve()
            size_prev = (size_cache or {}).get(cur_res)
            prev_size = int(size_prev[0]) if size_prev is not None else None
            prev_count = int(size_prev[1]) if size_prev is not None else 0
            row = project_row(
                cur,
                archived=True,
                restore_target=restore,
                archived_ts=archived_ts,
                include_git_dirty=include_git_dirty,
                prev_size_bytes=prev_size,
                prev_size_refresh_count=prev_count,
            )
            row.name = stem
            row.is_fork, row.is_tmp, row.suffix = classify_name(row.name)
            rows.append(row)
            dirnames[:] = []
            continue

        for name in filenames:
            if not name.endswith(packed_archive_suffix):
                continue
            path = cur / name
            if not marker_allowed(base_dir, path, nested):
                continue
            if has_marker_ancestor(base_dir, path):
                continue
            stem, archived_ts = split_archive_entry_name(path)
            restore = archived_restore_target(base_dir, path)
            path_res = path.resolve()
            size_prev = (size_cache or {}).get(path_res)
            prev_size = int(size_prev[0]) if size_prev is not None else None
            prev_count = int(size_prev[1]) if size_prev is not None else 0
            row = project_row(
                path,
                archived=True,
                restore_target=restore,
                archived_ts=archived_ts,
                include_git_dirty=include_git_dirty,
                prev_size_bytes=prev_size,
                prev_size_refresh_count=prev_count,
            )
            row.name = stem
            row.is_fork, row.is_tmp, row.suffix = classify_name(row.name)
            rows.append(row)
    return rows
