from __future__ import annotations

import re
from pathlib import Path

from ..core.models import PropertyDef
from .store import load_global_config_dict


def load_property_defs(base_dir: Path) -> list[PropertyDef]:
    raw = load_global_config_dict(base_dir)

    items: list[object] = []
    if isinstance(raw, dict):
        val = raw.get("properties", [])
        if isinstance(val, list):
            items = val

    defs_by_key: dict[str, PropertyDef] = {}

    def alloc_id(seed: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "_", seed.lower()).strip("_") or "prop"
        key = base
        i = 2
        while key in defs_by_key:
            key = f"{base}_{i}"
            i += 1
        return key

    def to_tuple(value: object) -> tuple[str, ...]:
        if isinstance(value, str):
            text = value.strip()
            return (text,) if text else ()
        if isinstance(value, list):
            out: list[str] = []
            for item in value:
                text = str(item).strip()
                if text:
                    out.append(text)
            return tuple(out)
        return ()

    for item in items:
        if not isinstance(item, dict):
            continue
        label_raw = str(item.get("label", "")).strip()
        token_raw = str(item.get("token", "")).strip()
        file_exists = to_tuple(item.get("file-exists", []))
        dir_exists = to_tuple(item.get("dir-exists", []))
        path_exists = to_tuple(item.get("path-exists", []))

        if not (file_exists or dir_exists or path_exists):
            continue

        seed = (
            label_raw
            or token_raw
            or (file_exists[0] if file_exists else "")
            or (dir_exists[0] if dir_exists else "")
            or (path_exists[0] if path_exists else "")
        )
        if not seed:
            continue
        key = alloc_id(seed)

        label = label_raw or key
        token = token_raw or (label[:3].upper() if label else key[:3].upper())

        defs_by_key[key] = PropertyDef(
            key=key,
            label=label,
            token=token,
            file_exists=file_exists,
            dir_exists=dir_exists,
            path_exists=path_exists,
        )

    return sorted(defs_by_key.values(), key=lambda p: p.key)
