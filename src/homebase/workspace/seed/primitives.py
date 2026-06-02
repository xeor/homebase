"""Low-level fixture primitives shared by demo/example and benchmark
seeders. No opinions about naming, counts, or tag policy — those live
in the callers."""
from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Callable

from ...core.constants import ARCHIVE_DIR_NAME
from ...metadata.api import save_base_data


def write_project_marker(
    path: Path,
    *,
    tags: Sequence[str] = (),
    description: str = "",
    wip: bool = False,
    repo_dir: str = "",
    log: Mapping[str, object] | None = None,
    worktree: Mapping[str, object] | None = None,
) -> None:
    """Write ``.base.yaml`` at ``path`` using only schema-allowed keys.

    Empty / falsy fields are omitted entirely so the resulting yaml
    stays tight. ``log`` and ``worktree`` are passed through verbatim
    when given — the caller is responsible for their inner shape.
    """
    data: dict[str, object] = {}
    if description:
        data["description"] = description
    tag_list = sorted({t for t in (tags or ()) if t})
    if tag_list:
        data["tags"] = tag_list
    if wip:
        data["wip"] = True
    if repo_dir:
        data["repo_dir"] = repo_dir
    if log:
        data["log"] = dict(log)
    if worktree:
        data["worktree"] = dict(worktree)
    save_base_data(path, data)


def make_active_project(
    base: Path,
    name: str,
    *,
    tags: Sequence[str] = (),
    description: str = "",
    wip: bool = False,
    repo_dir: str = "",
    log: Mapping[str, object] | None = None,
    worktree: Mapping[str, object] | None = None,
) -> Path:
    """``mkdir <base>/<name>`` + ``.base.yaml``. Returns the new path."""
    target = base / name
    target.mkdir(parents=True, exist_ok=False)
    write_project_marker(
        target,
        tags=tags,
        description=description,
        wip=wip,
        repo_dir=repo_dir,
        log=log,
        worktree=worktree,
    )
    return target


def make_archive_entry(
    base: Path,
    *,
    date: date,  # noqa: A002 — matches `date` from datetime intentionally
    slug: str,
    tags: Sequence[str] = (),
    description: str = "",
    log: Mapping[str, object] | None = None,
) -> Path:
    """Create ``<base>/_archive/<YYYY>/<YYYY-MM-DD>_<slug>/`` + marker.

    Returns the entry path. ``wip``/``repo_dir``/``worktree`` are
    intentionally not exposed — they don't apply to archive entries.
    """
    iso = date.strftime("%Y-%m-%d")
    year = date.strftime("%Y")
    entry = base / ARCHIVE_DIR_NAME / year / f"{iso}_{slug}"
    entry.mkdir(parents=True, exist_ok=False)
    write_project_marker(
        entry,
        tags=tags,
        description=description,
        log=log,
    )
    return entry


def pack_archive_entry(
    base: Path,
    entry: Path,
    *,
    archive_pack_internal: Callable[[Path, Path], Path],
) -> Path | None:
    """Pack ``entry`` (a dir under ``<base>/_archive/<year>/``) into a
    sibling ``.tgz``. Returns the new packed path, or ``None`` on
    failure. ``archive_pack_internal`` is injected by the caller — the
    production wrapper lives in ``commands.archive`` and handles
    worktree preflight + opened_ts move."""
    try:
        return archive_pack_internal(base, entry)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def make_temp_basefolder(base: Path, label: str) -> Path:
    """Resolve a fresh writable dir under the OS tmp root, named
    ``<base.name>-<label>-XXXXXX``. Used by the benchmark/test
    harnesses that need a throwaway workspace."""
    tmp_root = Path(tempfile.gettempdir()).resolve()
    prefix = f"{base.name}-{label}-"
    return Path(tempfile.mkdtemp(prefix=prefix, dir=str(tmp_root))).resolve()


__all__ = [
    "make_active_project",
    "make_archive_entry",
    "make_temp_basefolder",
    "pack_archive_entry",
    "write_project_marker",
]
