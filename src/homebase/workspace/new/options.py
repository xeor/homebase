from __future__ import annotations

from argparse import Namespace
from typing import Any

from .base import NewOptions
from .registry import get_source_class

_BOOL_OPTS = (
    "tmp",
    "timestamp",
    "open",
    "confirm",
    "ts_name",
    "alpha_name",
    "ask_name",
    "ask_source",
    "archive",
    "dry_run",
    "yes",
    "multi",
)


def _coerce_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise ValueError(f"expected bool, got {type(value).__name__}: {value!r}")


def resolve_options(
    source_key: str,
    cli_ns: Namespace,
    source_cfg: dict[str, Any] | None = None,
) -> NewOptions:
    """Resolve options in 3 layers: Source defaults → user config → CLI flags.

    `source_cfg` is the resolved per-source config block from
    .homebase/config.yaml (already inherited from any parent).
    """
    cls = get_source_class(source_key)
    merged: dict[str, Any] = {}
    for key, default in cls.default_options.items():
        merged[key] = default
    if source_cfg:
        for key, value in source_cfg.items():
            if key in ("parent", "config"):
                continue
            # YAML convention is kebab-case; map to the snake_case
            # option name used by argparse + the resolver.
            normalised = key.replace("-", "_")
            merged[normalised] = value

    # CLI overrides (None = "not set" / fall through)
    for opt in _BOOL_OPTS:
        cli_value = getattr(cli_ns, opt, None)
        coerced = _coerce_bool(cli_value)
        if coerced is not None:
            merged[opt] = coerced
    # --cd is an alias for --open
    cd_value = _coerce_bool(getattr(cli_ns, "cd", None))
    if cd_value is not None:
        merged["open"] = cd_value
    if getattr(cli_ns, "template", "") != "":
        merged["template"] = str(cli_ns.template)
    cli_tags = getattr(cli_ns, "tag", None) or []
    if cli_tags:
        existing = merged.get("tags") or []
        merged["tags"] = list(existing) + [str(t) for t in cli_tags]
    cli_post = getattr(cli_ns, "post", None) or []
    if cli_post:
        existing = merged.get("post") or []
        merged["post"] = list(existing) + [str(c) for c in cli_post]

    return NewOptions(
        tmp=bool(merged.get("tmp", False)),
        timestamp=bool(merged.get("timestamp", False)),
        # ``open`` defaults to True — the common case is to drop the
        # user into the new project. Pass ``--no-open`` / ``--no-cd``
        # to stay where you were.
        open=bool(merged.get("open", True)),
        confirm=bool(merged.get("confirm", False)),
        ts_name=bool(merged.get("ts_name", False)),
        alpha_name=bool(merged.get("alpha_name", False)),
        ask_name=bool(merged.get("ask_name", False)),
        ask_source=bool(merged.get("ask_source", False)),
        archive=bool(merged.get("archive", False)),
        dry_run=bool(merged.get("dry_run", False)),
        yes=bool(merged.get("yes", False)),
        multi=bool(merged.get("multi", False)),
        template=str(merged.get("template", "") or ""),
        tags=tuple(str(t) for t in (merged.get("tags") or [])),
        post=tuple(str(c) for c in (merged.get("post") or [])),
    )
