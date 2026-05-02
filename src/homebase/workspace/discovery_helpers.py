from __future__ import annotations

from pathlib import Path

from ..config.prefs import nested_discovery_enabled
from ..core import utils as core_utils
from ..core.constants import ARCHIVE_DIR_NAME, BASE_MARKER_FILE, MODE_ACTIVE, MODE_ARCHIVE
from . import discovery as discovery_utils

DISCOVERY_PRUNE_DIR_NAMES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    ".direnv",
    "__pycache__",
}


def resolve_include_nested(base_dir: Path, include_nested: bool | None) -> bool:
    return discovery_utils.resolve_include_nested(
        base_dir,
        include_nested,
        nested_discovery_enabled=nested_discovery_enabled,
    )


def discovery_zone_depth(base_dir: Path, path: Path) -> tuple[str, int]:
    return discovery_utils.discovery_zone_depth(
        base_dir,
        path,
        archive_dir_name=ARCHIVE_DIR_NAME,
        mode_archive=MODE_ARCHIVE,
        mode_active=MODE_ACTIVE,
    )


def discovery_marker_allowed(
    base_dir: Path,
    marker_dir: Path,
    include_nested: bool | None,
) -> bool:
    return discovery_utils.discovery_marker_allowed(
        base_dir,
        marker_dir,
        include_nested,
        zone_depth=discovery_zone_depth,
        resolve_include_nested_fn=resolve_include_nested,
    )


def discovery_has_marker_ancestor(base_dir: Path, marker_dir: Path) -> bool:
    return discovery_utils.discovery_has_marker_ancestor(
        base_dir,
        marker_dir,
        base_marker_file=BASE_MARKER_FILE,
    )


def discovery_prune_walk_dirnames(dirnames: list[str]) -> None:
    discovery_utils.discovery_prune_walk_dirnames(
        dirnames,
        prune_names=DISCOVERY_PRUNE_DIR_NAMES,
    )


def discovery_should_skip_active_walk_path(
    base_dir: Path,
    archive_root: Path,
    cur: Path,
) -> bool:
    return discovery_utils.discovery_should_skip_active_walk_path(
        base_dir,
        archive_root,
        cur,
        is_under=core_utils.is_under,
    )
