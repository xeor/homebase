from __future__ import annotations

from pathlib import Path
from typing import Any

from ...core.models import ProjectRow


def cached_top_active_names(*, base_dir: Path, active_rows: list[ProjectRow]) -> set[str]:
    out: set[str] = set()
    base_res = base_dir.resolve()
    for row in active_rows:
        try:
            if row.path.parent.resolve() != base_res:
                continue
        except (OSError, RuntimeError, ValueError):
            continue
        out.add(row.name)
    return out


def quick_active_dir_names(*, base_dir: Path) -> set[str]:
    out: set[str] = set()
    try:
        for path in base_dir.iterdir():
            if not path.is_dir():
                continue
            if path.name.startswith(".") or path.name.startswith("_"):
                continue
            out.add(path.name)
    except OSError:
        return set()
    return out


def startup_quick_active_dir_check(app: Any, *, level_info: str) -> None:
    if app.fast_exit_requested:
        return
    live_names = app._quick_active_dir_names()
    if not live_names:
        return
    cached_names = app._cached_top_active_names()
    added = live_names - cached_names
    removed = cached_names - live_names
    if not added and not removed:
        return
    app._log(
        f"startup quick check: top-level delta +{len(added)} -{len(removed)}; refreshing cache",
        level_info,
    )
    app._start_cache_refresh("startup top-level dir delta", force=True)
