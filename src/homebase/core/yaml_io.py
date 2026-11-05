"""YAML loading through libyaml when PyYAML has it (about 8x faster than
the pure-Python parser on the global config and project metadata)."""
from __future__ import annotations

from typing import Any

import yaml

_SAFE_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def yaml_safe_load(stream: str | bytes) -> Any:
    return yaml.load(stream, Loader=_SAFE_LOADER)  # nosec B506 - safe loader (C or Python)


__all__ = ["yaml_safe_load"]
