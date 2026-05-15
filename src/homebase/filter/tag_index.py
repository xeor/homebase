from __future__ import annotations

import os
import re
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Callable

import yaml


def safe_tag_component(tag: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", tag.strip())
    cleaned = cleaned.strip("._")
    return cleaned or "tag"


def safe_link_name(name: str) -> str:
    cleaned = re.sub(r"[\\/]+", "_", name.strip())
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", cleaned)
    cleaned = cleaned.strip()
    return cleaned or "project"


def project_tag_link_name(base_dir: Path, project_path: Path) -> str:
    rel = project_path.resolve().relative_to(base_dir.resolve())
    if len(rel.parts) > 1:
        return safe_link_name(f"{rel.parts[0]}__{rel.parts[-1]}")
    return safe_link_name(rel.parts[-1])


def sync_tag_symlinks_detailed(
    base_dir: Path,
    *,
    base_marker_file: str,
    collect_projects: Callable[[Path], list[Any]],
    verbose: bool,
    debug: bool,
) -> tuple[str | None, list[str]]:
    root = (base_dir / "_tags").resolve()
    lines: list[str] = []
    created = 0
    updated = 0
    kept = 0
    skipped_conflicts = 0
    removed_stale = 0
    removed_empty_dirs = 0

    if root.exists() and not root.is_dir():
        return f"_tags is not a directory: {root}", lines

    try:
        root.mkdir(parents=True, exist_ok=True)
        markers = sorted(base_dir.rglob(base_marker_file))
        rows = sorted(collect_projects(base_dir), key=lambda row: str(row.path).lower())

        if verbose:
            lines.append(f"base: {base_dir}")
            lines.append(f"_tags root: {root}")
            lines.append(f"markers found: {len(markers)}")
            lines.append(f"active projects scanned: {len(rows)}")

        desired: dict[Path, Path] = {}
        for row in rows:
            target = row.path.resolve()
            tags = sorted({str(tag).strip() for tag in row.tags if str(tag).strip()})
            if debug:
                rel = target.relative_to(base_dir)
                lines.append(f"project: {rel} tags={','.join(tags) if tags else '-'}")
            if not tags:
                continue

            base_name = project_tag_link_name(base_dir, row.path)
            for raw_tag in tags:
                tag_dir = root / safe_tag_component(raw_tag)
                tag_dir.mkdir(parents=True, exist_ok=True)
                candidate = tag_dir / base_name
                n = 2
                while candidate in desired and desired[candidate] != target:
                    candidate = tag_dir / f"{base_name}_{n}"
                    n += 1
                desired[candidate] = target
                if debug:
                    lines.append(f"want: {candidate.relative_to(base_dir)} -> {target}")

        if verbose:
            lines.append(f"desired symlinks: {len(desired)}")

        for link_path, target in desired.items():
            if link_path.exists() or link_path.is_symlink():
                if link_path.is_symlink():
                    try:
                        if link_path.resolve() == target:
                            kept += 1
                            continue
                    except OSError:
                        pass
                    link_path.unlink(missing_ok=True)
                    updated += 1
                    if verbose:
                        lines.append(f"update symlink: {link_path} -> {target}")
                else:
                    skipped_conflicts += 1
                    if verbose:
                        lines.append(f"skip non-symlink path: {link_path}")
                    continue

            link_path.symlink_to(target)
            created += 1
            if verbose:
                lines.append(f"create symlink: {link_path} -> {target}")

        stale = [cur for cur in root.rglob("*") if cur.is_symlink() and cur not in desired]
        for cur in stale:
            cur.unlink(missing_ok=True)
            removed_stale += 1
            if verbose:
                lines.append(f"remove stale symlink: {cur}")

        dirs = [p for p in root.rglob("*") if p.is_dir() and not p.is_symlink()]
        dirs.sort(key=lambda p: len(p.parts), reverse=True)
        for d in dirs:
            try:
                next(d.iterdir())
            except StopIteration:
                d.rmdir()
                removed_empty_dirs += 1
                if verbose:
                    lines.append(f"remove empty dir: {d}")
            except OSError:
                pass

        lines.append(
            "summary: "
            f"created={created} updated={updated} kept={kept} "
            f"removed_stale={removed_stale} removed_empty_dirs={removed_empty_dirs} "
            f"skipped_conflicts={skipped_conflicts}"
        )
        return None, lines
    except (
        OSError,
        ValueError,
        TypeError,
        sqlite3.Error,
        yaml.YAMLError,
        subprocess.SubprocessError,
    ) as exc:
        return str(exc), lines


def sync_tag_symlinks(
    base_dir: Path,
    *,
    base_marker_file: str,
    collect_projects: Callable[[Path], list[Any]],
) -> str | None:
    err, _lines = sync_tag_symlinks_detailed(
        base_dir,
        base_marker_file=base_marker_file,
        collect_projects=collect_projects,
        verbose=False,
        debug=False,
    )
    return err


def cleanup_tag_symlinks_pointing_at(base_dir: Path, target: Path) -> int:
    """Remove every ``_tags/*/`` symlink that points at ``target`` (or
    anything underneath it). Returns the count of symlinks removed.

    Used after ``b rm`` / ``b archive`` instead of the full
    ``sync_tag_symlinks`` rebuild: a single deletion / move only
    invalidates symlinks pointing at the one moved/removed path,
    and detecting that is O(|_tags/|) instead of O(|base/|).
    Walking all projects under base (with their nested files / git
    histories) is what blows a delete up to 10+ seconds; this helper
    walks only the small ``_tags/`` tree and untouched symlinks stay
    in place.

    Also prunes any tag-directories that become empty as a result.
    """
    tags_root = base_dir / "_tags"
    if not tags_root.is_dir():
        return 0
    target_str = str(target)
    target_prefix = target_str + os.sep
    removed = 0
    for link in tags_root.rglob("*"):
        if not link.is_symlink():
            continue
        try:
            link_target = os.readlink(link)
        except OSError:
            continue
        if link_target == target_str or link_target.startswith(target_prefix):
            try:
                link.unlink()
                removed += 1
            except OSError:
                pass
    # Tag dirs that just lost their last symlink are now empty —
    # drop them so ``_tags/`` doesn't accumulate orphan dirs.
    empties = sorted(
        (p for p in tags_root.rglob("*") if p.is_dir() and not p.is_symlink()),
        key=lambda p: len(p.parts),
        reverse=True,
    )
    for d in empties:
        try:
            d.rmdir()
        except OSError:
            pass  # not empty — fine
    return removed
