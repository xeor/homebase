from __future__ import annotations

from ..core.models import HookTarget, ProjectRow


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
        last_modified_ts=int(row.last_ts),
        created_ts=int(row.created_ts),
        archived_ts=int(row.archived_ts),
        git_branch=str(row.branch),
        git_dirty=str(row.dirty),
    )
