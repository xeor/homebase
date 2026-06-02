"""Wrappers around ``filter.tag_index`` that wire up the workspace's
``collect_projects`` so the tag-symlink sync knows where to find rows.

Lives in workspace because it composes ``filter`` (tag layout) with
``workspace.rows`` (project discovery). Both metadata and filter are
below workspace in the layering, so they can't reach here themselves."""
from __future__ import annotations

from pathlib import Path

from ..core.constants import BASE_MARKER_FILE
from ..filter import tag_index
from .rows import collect_projects


def sync_tag_symlinks_detailed(
    base_dir: Path,
    verbose: bool = False,
    debug: bool = False,
) -> tuple[str | None, list[str]]:
    return tag_index.sync_tag_symlinks_detailed(
        base_dir,
        base_marker_file=BASE_MARKER_FILE,
        collect_projects=collect_projects,
        verbose=verbose,
        debug=debug,
    )


def sync_tag_symlinks(base_dir: Path) -> str | None:
    return tag_index.sync_tag_symlinks(
        base_dir,
        base_marker_file=BASE_MARKER_FILE,
        collect_projects=collect_projects,
    )


def cleanup_tag_symlinks_pointing_at(base_dir: Path, target: Path) -> int:
    """Cheap O(|_tags/|) cleanup used after a single project's path is
    deleted or moved — much faster than a full ``sync_tag_symlinks``
    rebuild."""
    return tag_index.cleanup_tag_symlinks_pointing_at(base_dir, target)
