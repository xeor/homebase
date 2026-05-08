from __future__ import annotations

from pathlib import Path

from ..workspace.rows import collect_projects as _collect_projects


def collect_projects(base_dir: Path):
    return _collect_projects(base_dir)
