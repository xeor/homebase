from __future__ import annotations

import sys
from pathlib import Path

from ..workspace.deworktree import deworktree as _deworktree


def cmd_deworktree(base_dir: Path, target_path: str) -> int:
    target = Path(target_path).resolve() if target_path else None
    if target is None or not target.is_dir():
        print(f"b deworktree: target not found: {target_path}", file=sys.stderr)
        return 1
    try:
        _deworktree(base_dir, target)
    except ValueError as exc:
        print(f"b deworktree: {exc}", file=sys.stderr)
        return 1
    print(f"deworktreed: {target}")
    return 0
