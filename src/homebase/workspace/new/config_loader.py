from __future__ import annotations

from pathlib import Path
from typing import Any

from ...config.store import load_global_config_dict
from .registry import builtin_keys


class NewConfigError(ValueError):
    """Raised when `.homebase/config.yaml` 'new.sources' section is invalid."""


def load_new_sources(base_dir: Path) -> dict[str, dict[str, Any]]:
    """Return the resolved `new.sources` config, with parent inheritance
    expanded for every child. Each entry maps source key → its resolved
    option/config dict. Built-in keys without a config entry get an
    empty dict.
    """
    cfg = load_global_config_dict(base_dir)
    new_section = cfg.get("new") if isinstance(cfg, dict) else None
    sources_section = (
        new_section.get("sources") if isinstance(new_section, dict) else None
    )
    raw: dict[str, dict[str, Any]] = {}
    if isinstance(sources_section, dict):
        for key, value in sources_section.items():
            if not isinstance(key, str):
                raise NewConfigError(f"new.sources key must be a string, got {key!r}")
            if not isinstance(value, dict):
                raise NewConfigError(
                    f"new.sources.{key} must be a mapping, got {type(value).__name__}"
                )
            raw[key] = dict(value)

    builtins = set(builtin_keys())

    # Validate parents + detect cycles.
    for key, entry in raw.items():
        if key in builtins:
            if "parent" in entry:
                raise NewConfigError(
                    f"new.sources.{key} is a built-in source — must not declare parent"
                )
        else:
            parent = entry.get("parent")
            if not parent:
                raise NewConfigError(
                    f"new.sources.{key} is unknown — needs a 'parent: <key>'"
                )
            if not isinstance(parent, str):
                raise NewConfigError(
                    f"new.sources.{key}.parent must be a string"
                )

    # Cycle detection via DFS.
    visiting: set[str] = set()
    resolved_order: list[str] = []
    seen: set[str] = set()

    def visit(key: str) -> None:
        if key in seen:
            return
        if key in visiting:
            raise NewConfigError(f"new.sources: parent cycle through {key!r}")
        visiting.add(key)
        entry = raw.get(key, {})
        parent = entry.get("parent")
        if parent:
            if parent not in raw and parent not in builtins:
                raise NewConfigError(
                    f"new.sources.{key}: parent {parent!r} not found"
                )
            if parent in raw:
                visit(parent)
        visiting.remove(key)
        seen.add(key)
        resolved_order.append(key)

    for key in list(raw.keys()):
        visit(key)

    # Expand: child inherits from parent (shallow-merge options,
    # deep-merge `config:`).
    resolved: dict[str, dict[str, Any]] = {}
    for key in resolved_order:
        entry = dict(raw[key])
        parent = entry.get("parent")
        parent_resolved: dict[str, Any] = {}
        if parent:
            if parent in resolved:
                parent_resolved = resolved[parent]
            # else parent is a built-in key without config — empty defaults
        merged: dict[str, Any] = {}
        for k, v in parent_resolved.items():
            if k == "parent":
                continue  # parent is per-entry, not inherited
            if k == "config":
                merged["config"] = dict(v)
            else:
                merged[k] = v
        for k, v in entry.items():
            if k == "config":
                base_cfg = merged.get("config", {})
                if isinstance(base_cfg, dict) and isinstance(v, dict):
                    out = dict(base_cfg)
                    out.update(v)
                    merged["config"] = out
                else:
                    merged["config"] = v
            else:
                merged[k] = v
        resolved[key] = merged

    # Built-ins without a config entry → empty.
    for key in builtins:
        resolved.setdefault(key, {})
    return resolved
