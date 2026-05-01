from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

import yaml


def scan_nested_project_paths(
    base_dir: Path,
    *,
    archive_dir_name: str,
    base_marker_file: str,
    discovery_should_skip_active_walk_path: Callable[[Path, Path, Path], bool],
    discovery_prune_walk_dirnames: Callable[[list[str]], None],
) -> list[Path]:
    out: list[Path] = []
    base_res = base_dir.resolve()
    archive_root = (base_dir / archive_dir_name).resolve()
    for dirpath, dirnames, filenames in os.walk(base_dir, topdown=True):
        cur = Path(dirpath).resolve()
        if discovery_should_skip_active_walk_path(base_dir, archive_root, cur):
            dirnames[:] = []
            continue
        discovery_prune_walk_dirnames(dirnames)
        if base_marker_file not in filenames or cur == base_res:
            continue
        rel = cur.relative_to(base_res)
        if len(rel.parts) <= 1:
            continue
        out.append(cur)
        dirnames[:] = []
    out.sort(key=lambda path: str(path))
    return out


def suggest_flat_name(base_dir: Path, nested_path: Path) -> str:
    rel = nested_path.resolve().relative_to(base_dir.resolve())
    parts = [p for p in rel.parts if p]
    if not parts:
        return nested_path.name
    if len(parts) == 1:
        return parts[0]
    return "-".join(parts)


def scan_nested_markers_all(
    base_dir: Path,
    *,
    base_marker_file: str,
    discovery_zone_depth: Callable[[Path, Path], tuple[str, int]],
    discovery_marker_allowed: Callable[[Path, Path, bool | None], bool],
) -> tuple[dict[str, int], list[dict[str, object]]]:
    base_res = base_dir.resolve()
    marker_dirs: list[Path] = []
    scanned_dirs = 0
    for dirpath, _dirnames, filenames in os.walk(base_dir, topdown=True):
        scanned_dirs += 1
        if base_marker_file in filenames:
            try:
                marker_dirs.append(Path(dirpath).resolve())
            except (OSError, RuntimeError):
                continue

    marker_set = set(marker_dirs)
    entries: list[dict[str, object]] = []
    counts = {
        "dirs_scanned": scanned_dirs,
        "markers_total": len(marker_dirs),
        "active_roots": 0,
        "archive_roots": 0,
        "active_subfolder_markers": 0,
        "archive_subfolder_markers": 0,
        "active_child_of_marker": 0,
        "archive_child_of_marker": 0,
    }

    for path in sorted(marker_dirs, key=lambda x: str(x)):
        try:
            rel = path.relative_to(base_res)
        except ValueError:
            continue
        if not rel.parts:
            continue
        zone, zone_depth = discovery_zone_depth(base_dir, path)
        in_archive = zone == "archive"

        ancestor = path.parent
        has_ancestor_marker = False
        while ancestor != base_res and ancestor != ancestor.parent:
            if ancestor in marker_set:
                has_ancestor_marker = True
                break
            ancestor = ancestor.parent

        depth = len(rel.parts)
        nested = False
        reason = ""
        active_subfolder = zone == "active" and zone_depth > 1
        discoverable = discovery_marker_allowed(base_dir, path, include_nested=False)

        if in_archive:
            nested = has_ancestor_marker
            if nested:
                reason = "inside another archive marker"
            elif discoverable:
                reason = "archive root marker"
            else:
                reason = "archive subfolder marker"
            if zone_depth > 1 and not nested:
                counts["archive_subfolder_markers"] += 1
            if nested:
                counts["archive_child_of_marker"] += 1
            elif discoverable:
                counts["archive_roots"] += 1
        else:
            nested = has_ancestor_marker
            if has_ancestor_marker:
                reason = "inside another project marker"
            elif zone_depth > 1:
                reason = "subfolder marker"
            else:
                reason = "top-level marker"
            if zone_depth > 1:
                counts["active_subfolder_markers"] += 1
            if has_ancestor_marker:
                counts["active_child_of_marker"] += 1
            if zone_depth <= 1:
                counts["active_roots"] += 1

        tags = ["nested" if nested else "root", ("archive" if in_archive else "active"), f"depth:{depth}"]
        entries.append(
            {
                "path": str(path),
                "relative": str(rel),
                "zone": "archive" if in_archive else "active",
                "nested": nested,
                "active_subfolder": active_subfolder,
                "reason": reason,
                "suggested_name": suggest_flat_name(base_dir, path),
                "suggested_tags": tags,
            }
        )

    return counts, entries


def cmd_utils_opt_in_nested_discovery(
    base_dir: Path,
    *,
    base_marker_file: str,
    archive_dir_name: str,
    nested_discovery_enabled: Callable[[Path], bool],
    set_nested_discovery_enabled: Callable[[Path, bool], None],
    prompt_yes_no: Callable[[str, bool], bool],
    scan_nested_markers_all_fn: Callable[[Path], tuple[dict[str, int], list[dict[str, object]]]],
) -> int:
    print(f"nested discovery utility: base={base_dir}")
    print(f"scanning all subfolders for {base_marker_file} markers (active + {archive_dir_name})...")
    counts, entries = scan_nested_markers_all_fn(base_dir)
    nested_entries = [entry for entry in entries if bool(entry.get("nested"))]

    top_level_names = {
        p.name
        for p in base_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".") and not p.name.startswith("_")
    }
    suggestion_names = [str(entry.get("suggested_name", "")) for entry in nested_entries]
    duplicates = sorted({name for name in suggestion_names if name and suggestion_names.count(name) > 1})
    collisions = sorted({name for name in suggestion_names if name in top_level_names})

    print("")
    print("scan summary:")
    print(f"- dirs scanned: {counts['dirs_scanned']}")
    print(f"- markers total: {counts['markers_total']}")
    print(f"- active roots: {counts['active_roots']}")
    print(f"- archive roots: {counts['archive_roots']}")
    print(f"- active subfolder markers: {counts['active_subfolder_markers']}")
    print(f"- archive subfolder markers: {counts['archive_subfolder_markers']}")
    print(f"- active child-of-marker (invalid): {counts['active_child_of_marker']}")
    print(f"- archive child-of-marker (invalid): {counts['archive_child_of_marker']}")

    nested_enabled = nested_discovery_enabled(base_dir)
    valid_subfolder_markers = [
        entry for entry in entries if bool(entry.get("active_subfolder")) and not bool(entry.get("nested"))
    ]

    if nested_entries:
        print("")
        print("invalid marker details (sample):")
        max_lines = 120
        for i, entry in enumerate(nested_entries):
            if i >= max_lines:
                print(f"- ... +{len(nested_entries) - max_lines} more")
                break
            rel = str(entry.get("relative", ""))
            reason = str(entry.get("reason", ""))
            sug = str(entry.get("suggested_name", ""))
            tags = ",".join(str(t) for t in entry.get("suggested_tags", []))
            print(f"- {rel} | {reason} | suggested name: {sug} | tags: {tags}")

        if duplicates:
            print("")
            print("duplicate suggested names:")
            for name in duplicates:
                print(f"- {name}")
        if collisions:
            print("")
            print("collisions with existing top-level names:")
            for name in collisions:
                print(f"- {name}")

        if prompt_yes_no("Write full nested marker report to .base-nested-discovery.yml?", True):
            report = {
                "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                "base_dir": str(base_dir),
                "summary": counts,
                "duplicates": duplicates,
                "collisions": collisions,
                "entries": entries,
            }
            out_path = Path.cwd() / ".base-nested-discovery.yml"
            out_path.write_text(yaml.safe_dump(report, sort_keys=False, default_flow_style=False))
            print(f"wrote: {out_path}")

        print("")
        print("invalid child-of-marker entries found; fix/migrate those first.")
        if valid_subfolder_markers and not nested_enabled:
            print(
                f"note: {len(valid_subfolder_markers)} valid subfolder markers are present and require discovery.nested.enabled=true"
            )
            if prompt_yes_no("Enable nested discovery now?", True):
                set_nested_discovery_enabled(base_dir, True)
                print("set discovery.nested.enabled=true")
            else:
                print("kept discovery.nested.enabled as-is")
        return 2

    print("")
    print("no invalid child-of-marker markers found.")
    if valid_subfolder_markers:
        print(f"valid subfolder markers found: {len(valid_subfolder_markers)}")
        if not nested_enabled:
            print("nested discovery is currently disabled, so these markers are ignored in both active and archive views.")
            if prompt_yes_no("Enable nested discovery now?", True):
                set_nested_discovery_enabled(base_dir, True)
                print("set discovery.nested.enabled=true")
            else:
                print("kept discovery.nested.enabled as-is")
        else:
            print("nested discovery is enabled; subfolder markers are supported in active + archive.")
    else:
        print("no valid subfolder markers found.")
        if nested_enabled:
            if prompt_yes_no("Disable nested discovery now?", True):
                set_nested_discovery_enabled(base_dir, False)
                print("set discovery.nested.enabled=false")
            else:
                print("kept discovery.nested.enabled as-is")
        else:
            print("nested discovery remains disabled.")
    return 0


def cmd_utils(base_dir: Path, subcommand: str, *, cmd_utils_opt_in_nested_discovery: Callable[[Path], int]) -> int:
    if subcommand == "opt-in-nested-discovery":
        return cmd_utils_opt_in_nested_discovery(base_dir)
    print("unknown utils subcommand", file=sys.stderr)
    return 1
