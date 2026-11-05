from __future__ import annotations

import hashlib
from pathlib import Path


def workspace_quick_signature(
    *,
    base_dir: Path,
    archive_dir_name: str,
    packed_archive_suffix: str,
) -> str:
    parts: list[str] = []
    try:
        base_names = [
            p.name
            for p in base_dir.iterdir()
            if p.is_dir() and not p.name.startswith(".") and not p.name.startswith("_")
        ]
        base_names.sort()
        h = hashlib.sha1(usedforsecurity=False)
        for name in base_names:
            h.update(name.encode("utf-8", errors="ignore"))
            h.update(b"\0")
        parts.append(f"active:{len(base_names)}:{h.hexdigest()[:20]}")
    except (OSError, ValueError):
        parts.append("active:err")

    archive_root = base_dir / archive_dir_name
    try:
        if archive_root.is_dir():
            roots = [
                p.name
                for p in archive_root.iterdir()
                if p.is_dir() or p.name.endswith(packed_archive_suffix)
            ]
            roots.sort()
            h2 = hashlib.sha1(usedforsecurity=False)
            for name in roots:
                h2.update(name.encode("utf-8", errors="ignore"))
                h2.update(b"\0")
            parts.append(f"archive:{len(roots)}:{h2.hexdigest()[:20]}")
        else:
            parts.append("archive:0")
    except (OSError, ValueError):
        parts.append("archive:err")

    return "||".join(parts)
