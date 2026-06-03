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


def _merge_source_cfg(merged: dict[str, Any], source_cfg: dict[str, Any]) -> None:
    for key, value in source_cfg.items():
        if key in ("parent", "config"):
            continue
        # YAML convention is kebab-case; map to the snake_case option name
        # used by argparse + the resolver.
        normalised = key.replace("-", "_")
        merged[normalised] = value


def _apply_cli_bool_overrides(merged: dict[str, Any], cli_ns: Namespace) -> None:
    for opt in _BOOL_OPTS:
        coerced = _coerce_bool(getattr(cli_ns, opt, None))
        if coerced is not None:
            merged[opt] = coerced
    cd_value = _coerce_bool(getattr(cli_ns, "cd", None))
    if cd_value is not None:
        merged["open"] = cd_value


def _apply_cli_scalar_overrides(merged: dict[str, Any], cli_ns: Namespace) -> None:
    if getattr(cli_ns, "template", "") != "":
        merged["template"] = str(cli_ns.template)
    cli_from = getattr(cli_ns, "from_project", "") or ""
    if cli_from:
        merged["from_project"] = str(cli_from)


def _apply_cli_list_overrides(merged: dict[str, Any], cli_ns: Namespace) -> None:
    cli_tags = getattr(cli_ns, "tag", None) or []
    if cli_tags:
        merged["tags"] = list(merged.get("tags") or []) + [str(t) for t in cli_tags]
    cli_post = getattr(cli_ns, "post", None) or []
    if cli_post:
        merged["post"] = list(merged.get("post") or []) + [str(c) for c in cli_post]


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
    merged: dict[str, Any] = dict(cls.default_options)
    if source_cfg:
        _merge_source_cfg(merged, source_cfg)
    _apply_cli_bool_overrides(merged, cli_ns)
    _apply_cli_scalar_overrides(merged, cli_ns)
    _apply_cli_list_overrides(merged, cli_ns)
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
        from_project=str(merged.get("from_project", "") or ""),
    )
