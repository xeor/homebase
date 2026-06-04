from __future__ import annotations

import re
from pathlib import Path

from ..core.models import PropertyDef
from . import cache_profile as cache_profile_config
from .store import load_global_config_dict

_VAR_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def _variables_context(raw: dict[str, object]) -> dict[str, str]:
    vars_raw = raw.get("variables", {})
    if not isinstance(vars_raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in vars_raw.items():
        name = str(key).strip()
        if not name:
            continue
        out[name] = str(value)
    return out


def _render_value(text: str, ctx: dict[str, str]) -> str:
    if not text or not ctx:
        return text
    return _VAR_PATTERN.sub(lambda m: str(ctx.get(m.group(1), m.group(0))), text)


def _render_obj(value: object, ctx: dict[str, str]) -> object:
    if isinstance(value, str):
        return _render_value(value, ctx)
    if isinstance(value, list):
        return [_render_obj(v, ctx) for v in value]
    if isinstance(value, dict):
        return {str(k): _render_obj(v, ctx) for k, v in value.items()}
    return value


def _to_tuple(value: object) -> tuple[str, ...]:
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


_CACHE_OVERRIDE_KEYS = frozenset(
    {
        "update_interval_s",
        "update_batch_size",
        "update_priority",
        "cache_mode",
        "cache_ttl_s",
        "use_usage_score",
        "usage_weight",
        "stale_boost",
        "max_parallelism",
        "min_interval_s",
        "refresh_on_event",
        "jitter_pct",
    }
)


def _parse_queries(raw_queries: object) -> tuple[dict[str, object], ...]:
    if not isinstance(raw_queries, list):
        return ()
    norm: list[dict[str, object]] = []
    for q in raw_queries:
        if isinstance(q, dict) and str(q.get("type", "")).strip():
            norm.append(dict(q))
    return tuple(norm)


def _explicit_cache_fields(item: dict) -> dict[str, object]:
    return {
        str(k): v for k, v in item.items() if str(k) in _CACHE_OVERRIDE_KEYS
    }


def _resolve_cache_profiles(
    token: str,
    item: dict,
    profile_table: dict,
    cache_ttl_s: float,
) -> tuple[dict[str, dict[str, object]] | None, float, str]:
    cache_profile = str(item.get("cache_profile", "")).strip()
    if not cache_profile:
        return None, cache_ttl_s, cache_profile
    explicit_fields = _explicit_cache_fields(item)
    profile_overrides = item.get("cache_profile_overrides", None)
    try:
        active_profile = cache_profile_config.resolve_cache_profile(
            profile_name=cache_profile,
            view="active",
            profile_table=profile_table,
            explicit_fields=explicit_fields,
            profile_overrides=profile_overrides,
        )
        archive_profile = cache_profile_config.resolve_cache_profile(
            profile_name=cache_profile,
            view="archive",
            profile_table=profile_table,
            explicit_fields=explicit_fields,
            profile_overrides=profile_overrides,
        )
    except ValueError as exc:
        raise ValueError(
            f"invalid cache profile for property {token}: {exc}"
        ) from exc
    raw_ttl = active_profile.get("cache_ttl_s", cache_ttl_s)
    if isinstance(raw_ttl, (int, float, str)):
        try:
            cache_ttl_s = float(raw_ttl)
        except (TypeError, ValueError):
            pass
    return (
        {"active": active_profile, "archive": archive_profile},
        cache_ttl_s,
        cache_profile,
    )


def _build_property_def(
    token_key: object,
    item: object,
    vars_ctx: dict,
    profile_table: dict,
) -> PropertyDef | None:
    if not isinstance(item, dict):
        return None
    token = str(token_key).strip().upper()
    if not token:
        return None
    key = token.lower()
    label = _render_value(str(item.get("label", token)).strip() or token, vars_ctx)
    color = _render_value(str(item.get("color", "")).strip(), vars_ctx)
    file_exists = _to_tuple(_render_obj(item.get("file-exists", []), vars_ctx))
    dir_exists = _to_tuple(_render_obj(item.get("dir-exists", []), vars_ctx))
    path_exists = _to_tuple(_render_obj(item.get("path-exists", []), vars_ctx))
    queries = _parse_queries(_render_obj(item.get("queries", []), vars_ctx))
    enabled = sum(
        1
        for x in (file_exists, dir_exists, path_exists, queries)
        if x
    )
    if enabled != 1:
        return None
    try:
        cache_ttl_s = float(item.get("cache_ttl_s", 15.0))
    except (TypeError, ValueError):
        cache_ttl_s = 15.0
    cache_profiles_by_view, cache_ttl_s, cache_profile = _resolve_cache_profiles(
        token, item, profile_table, cache_ttl_s
    )
    return PropertyDef(
        key=key,
        label=label,
        token=token,
        color=color,
        file_exists=file_exists,
        dir_exists=dir_exists,
        path_exists=path_exists,
        queries=queries,
        cache_ttl_s=max(1.0, cache_ttl_s),
        cache_profile=cache_profile,
        cache_profiles_by_view=cache_profiles_by_view,
    )


def load_property_defs(base_dir: Path) -> list[PropertyDef]:
    raw = load_global_config_dict(base_dir)
    profile_table = cache_profile_config.load_cache_profile_table(raw)
    vars_ctx = _variables_context(raw) if isinstance(raw, dict) else {}
    properties_raw = raw.get("properties", {}) if isinstance(raw, dict) else {}
    if not isinstance(properties_raw, dict):
        return []
    defs: list[PropertyDef] = []
    for token_key, item in properties_raw.items():
        prop = _build_property_def(token_key, item, vars_ctx, profile_table)
        if prop is not None:
            defs.append(prop)
    return defs
