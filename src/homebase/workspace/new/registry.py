from __future__ import annotations

from typing import Any

from .base import NewConfig, Source

_SOURCES: dict[str, type[Source]] = {}


def register_source(cls: type[Source]) -> type[Source]:
    if not cls.key:
        raise ValueError(f"Source {cls.__name__} missing 'key'")
    if cls.key in _SOURCES:
        raise ValueError(f"Source key already registered: {cls.key}")
    _SOURCES[cls.key] = cls
    return cls


def builtin_keys() -> list[str]:
    return sorted(_SOURCES.keys())


def get_source_class(key: str) -> type[Source]:
    if key not in _SOURCES:
        raise KeyError(f"unknown source: {key}")
    return _SOURCES[key]


def construct_source(key: str, config: dict[str, Any] | None = None) -> Source:
    cls = get_source_class(key)
    merged = dict(cls.default_config)
    if config:
        merged.update(config)
    return cls(NewConfig(data=merged))
