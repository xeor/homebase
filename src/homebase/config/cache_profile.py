from __future__ import annotations

from collections.abc import Mapping

from ..core.constants import MODE_ACTIVE, MODE_ARCHIVE

_CACHE_PROFILE_SCOPE_ALL = "all"
_CACHE_PROFILE_VIEWS = (MODE_ACTIVE, MODE_ARCHIVE)
_CACHE_PROFILE_KEYS = {
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
_CACHE_PROFILE_REQUIRED_KEYS = {
    "update_interval_s",
    "update_batch_size",
    "update_priority",
    "cache_mode",
    "cache_ttl_s",
}
_CACHE_PROFILE_HARD_DEFAULTS: dict[str, object] = {
    "update_interval_s": 10.0,
    "update_batch_size": 1,
    "update_priority": 50,
    "cache_mode": "ttl",
    "cache_ttl_s": 30.0,
    "use_usage_score": False,
    "usage_weight": 0.0,
    "stale_boost": False,
    "max_parallelism": 1,
}


def _normalize_profile_entry(
    *,
    profile_name: str,
    scope: str,
    value: object,
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(
            f"cache_profile.{scope}.{profile_name} must be a mapping, got {type(value).__name__}"
        )
    out = dict(value)
    invalid = sorted(str(k) for k in out if str(k) not in _CACHE_PROFILE_KEYS)
    if invalid:
        invalid_csv = ", ".join(invalid)
        raise ValueError(
            f"cache_profile.{scope}.{profile_name} has invalid keys: {invalid_csv}"
        )
    return out


def _merge_profile_layers(layers: list[Mapping[str, object]]) -> dict[str, object]:
    merged: dict[str, object] = {}
    for layer in layers:
        merged.update(dict(layer))
    return merged


def load_cache_profile_table(data: object) -> dict[str, dict[str, dict[str, object]]]:
    out: dict[str, dict[str, dict[str, object]]] = {
        _CACHE_PROFILE_SCOPE_ALL: {},
        MODE_ACTIVE: {},
        MODE_ARCHIVE: {},
    }
    if not isinstance(data, Mapping):
        return out
    raw = data.get("cache_profile", {})
    if not isinstance(raw, Mapping):
        return out

    for scope in (_CACHE_PROFILE_SCOPE_ALL, *_CACHE_PROFILE_VIEWS):
        scope_raw = raw.get(scope, {})
        if not isinstance(scope_raw, Mapping):
            continue
        for profile_name, profile_value in scope_raw.items():
            name = str(profile_name).strip()
            if not name:
                continue
            out[scope][name] = _normalize_profile_entry(
                profile_name=name,
                scope=scope,
                value=profile_value,
            )
    return out


def _apply_profile_overrides(
    resolved: dict[str, object],
    view: str,
    profile_overrides: Mapping[str, object],
) -> dict[str, object]:
    if not isinstance(profile_overrides, Mapping):
        raise ValueError("cache_profile_overrides must be a mapping")
    override_all = profile_overrides.get(_CACHE_PROFILE_SCOPE_ALL, {})
    override_view = profile_overrides.get(view, {})
    if override_all and not isinstance(override_all, Mapping):
        raise ValueError("cache_profile_overrides.all must be a mapping")
    if override_view and not isinstance(override_view, Mapping):
        raise ValueError(f"cache_profile_overrides.{view} must be a mapping")
    all_part = dict(override_all) if isinstance(override_all, Mapping) else {}
    view_part = dict(override_view) if isinstance(override_view, Mapping) else {}
    return _merge_profile_layers([resolved, all_part, view_part])


def _validate_resolved_keys(resolved: dict[str, object]) -> None:
    invalid = sorted(
        str(k) for k in resolved if str(k) not in _CACHE_PROFILE_KEYS
    )
    if invalid:
        raise ValueError(
            f"resolved cache profile has invalid keys: {', '.join(invalid)}"
        )
    missing = sorted(
        k for k in _CACHE_PROFILE_REQUIRED_KEYS if k not in resolved
    )
    if missing:
        raise ValueError(
            f"resolved cache profile missing keys: {', '.join(missing)}"
        )


def resolve_cache_profile(
    *,
    profile_name: str,
    view: str,
    profile_table: Mapping[str, Mapping[str, Mapping[str, object]]],
    explicit_fields: Mapping[str, object] | None = None,
    profile_overrides: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if view not in _CACHE_PROFILE_VIEWS:
        raise ValueError(f"unknown cache profile view: {view}")
    all_scope = profile_table.get(_CACHE_PROFILE_SCOPE_ALL, {})
    view_scope = profile_table.get(view, {})
    base_layer = all_scope.get(profile_name)
    view_layer = view_scope.get(profile_name)
    if base_layer is None and view_layer is None:
        raise ValueError(f"unknown cache_profile reference: {profile_name}")
    resolved = _merge_profile_layers(
        [
            _CACHE_PROFILE_HARD_DEFAULTS,
            base_layer or {},
            view_layer or {},
            explicit_fields or {},
        ]
    )
    if profile_overrides is not None:
        resolved = _apply_profile_overrides(resolved, view, profile_overrides)
    _validate_resolved_keys(resolved)
    return resolved
