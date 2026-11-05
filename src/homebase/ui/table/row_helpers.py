from __future__ import annotations

from pathlib import Path

from ...core.models import ProjectRow
from ...metadata.api import property_tokens


def match_query_lower(row: ProjectRow, q_lower: str) -> bool:
    if not q_lower:
        return True
    hay = " ".join(
        [
            row.name,
            row.description,
            " ".join(row.tags),
            " ".join(row.properties),
            property_tokens(row.properties),
            row.branch,
            row.path.as_posix(),
        ]
    ).lower()
    return q_lower in hay


def same_path(a: Path | None, b: Path | None) -> bool:
    if a is None or b is None:
        return False
    if a == b:
        return True
    try:
        return a.resolve() == b.resolve()
    except (OSError, RuntimeError, ValueError):
        return str(a) == str(b)


def has_open_pane(path: Path, open_pane_count_by_project: dict[Path, int]) -> bool:
    return open_pane_count_by_project.get(path, 0) > 0


