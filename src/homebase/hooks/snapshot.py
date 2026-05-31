from __future__ import annotations

from pathlib import Path

from ..core.models import HookTarget, ProjectRow
from ..metadata.api import load_base_data


def snapshot_target(row: ProjectRow, base_meta: dict[str, object]) -> HookTarget:
    return HookTarget(
        path=row.path,
        name=row.name,
        archived=bool(row.archived),
        tags=list(row.tags),
        properties=list(row.properties),
        description=str(row.description),
        wip=bool(row.wip),
        suffix=row.suffix,
        packed=bool(row.packed),
        base_meta=dict(base_meta),
        modified_ts=int(row.last_ts),
        created_ts=int(row.created_ts),
        archived_ts=int(row.archived_ts),
        git_branch=str(row.branch),
        git_dirty=str(row.dirty),
    )


def snapshot_target_from_path(path: Path, *, archived: bool = False) -> HookTarget:
    base_meta = load_base_data(path)
    tags_raw = base_meta.get("tags", [])
    tags = [str(tag) for tag in tags_raw] if isinstance(tags_raw, list) else []
    props_raw = base_meta.get("properties", [])
    props = [str(prop) for prop in props_raw] if isinstance(props_raw, list) else []
    return HookTarget(
        path=path,
        name=path.name,
        archived=bool(archived),
        tags=tags,
        properties=props,
        description=str(base_meta.get("description", "") or ""),
        wip=bool(base_meta.get("wip", False)),
        suffix=(str(base_meta.get("suffix")) if base_meta.get("suffix") is not None else None),
        packed=False,
        base_meta=dict(base_meta),
        modified_ts=0,
        created_ts=0,
        archived_ts=0,
        git_branch="",
        git_dirty="",
    )
