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


def load_property_defs(base_dir: Path) -> list[PropertyDef]:
    raw = load_global_config_dict(base_dir)
    profile_table = cache_profile_config.load_cache_profile_table(raw)
    vars_ctx = _variables_context(raw) if isinstance(raw, dict) else {}
    properties_raw = raw.get("properties", {}) if isinstance(raw, dict) else {}
    if not isinstance(properties_raw, dict):
        return []

    defs: list[PropertyDef] = []
    for token_key, item in properties_raw.items():
        if not isinstance(item, dict):
            continue
        token = str(token_key).strip().upper()
        if not token:
            continue
        key = token.lower()
        if not key:
            continue
        label = _render_value(str(item.get("label", token)).strip() or token, vars_ctx)
        color = _render_value(str(item.get("color", "")).strip(), vars_ctx)
        file_exists = _to_tuple(_render_obj(item.get("file-exists", []), vars_ctx))
        dir_exists = _to_tuple(_render_obj(item.get("dir-exists", []), vars_ctx))
        path_exists = _to_tuple(_render_obj(item.get("path-exists", []), vars_ctx))
        queries_raw = _render_obj(item.get("queries", []), vars_ctx)
        queries: tuple[dict[str, object], ...] = ()
        if isinstance(queries_raw, list):
            norm: list[dict[str, object]] = []
            for q in queries_raw:
                if isinstance(q, dict) and str(q.get("type", "")).strip():
                    norm.append(dict(q))
            queries = tuple(norm)
        enabled_detectors = sum(
            1 if x else 0
            for x in (bool(file_exists), bool(dir_exists), bool(path_exists), bool(queries))
        )
        if enabled_detectors != 1:
            continue
        try:
            cache_ttl_s = float(item.get("cache_ttl_s", 15.0))
        except (TypeError, ValueError):
            cache_ttl_s = 15.0
        explicit_cache_fields = {
            str(k): v
            for k, v in item.items()
            if str(k)
            in {
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
        }
        cache_profile = str(item.get("cache_profile", "")).strip()
        profile_overrides = item.get("cache_profile_overrides", None)
        cache_profiles_by_view: dict[str, dict[str, object]] | None = None
        if cache_profile:
            try:
                active_profile = cache_profile_config.resolve_cache_profile(
                    profile_name=cache_profile,
                    view="active",
                    profile_table=profile_table,
                    explicit_fields=explicit_cache_fields,
                    profile_overrides=profile_overrides,
                )
                archive_profile = cache_profile_config.resolve_cache_profile(
                    profile_name=cache_profile,
                    view="archive",
                    profile_table=profile_table,
                    explicit_fields=explicit_cache_fields,
                    profile_overrides=profile_overrides,
                )
            except ValueError as exc:
                raise ValueError(f"invalid cache profile for property {token}: {exc}") from exc
            cache_profiles_by_view = {
                "active": active_profile,
                "archive": archive_profile,
            }
            try:
                cache_ttl_s = float(active_profile.get("cache_ttl_s", cache_ttl_s))
            except (TypeError, ValueError):
                pass
        defs.append(
            PropertyDef(
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
        )
    return defs
