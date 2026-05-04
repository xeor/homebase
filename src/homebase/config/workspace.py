from __future__ import annotations

from . import cache_profile as cache_profile_config


def load_suffixes(data: object, *, default_suffixes: list[str]) -> list[str]:
    if not isinstance(data, dict):
        return list(default_suffixes)
    suffixes = data.get("suffixes", [])
    if not isinstance(suffixes, list):
        return list(default_suffixes)
    out: list[str] = []
    seen: set[str] = set()
    for item in suffixes:
        value = str(item).strip().lstrip(".").lower()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out or list(default_suffixes)


def load_file_view_exclude_patterns(data: object) -> list[str]:
    if not isinstance(data, dict):
        return []
    files_view = data.get("files_view", {})
    if not isinstance(files_view, dict):
        return []
    extra = files_view.get("exclude_patterns", [])
    legacy = files_view.get("exclude_dirs", [])
    values: list[str] = []
    if isinstance(extra, list):
        values.extend(str(x).strip() for x in extra)
    if isinstance(legacy, list):
        values.extend(str(x).strip() for x in legacy)
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        value = str(item).strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def load_custom_actions(data: object) -> list[dict[str, str]]:
    raw = data.get("custom_actions", []) if isinstance(data, dict) else []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id", "")).strip() or f"custom_{idx + 1}"
        if cid in seen:
            continue
        seen.add(cid)
        label = str(item.get("label", cid)).strip() or cid
        scope = str(item.get("scope", "item")).strip().lower()
        if scope not in {"item", "selection", "global"}:
            scope = "item"
        command = str(item.get("command", "")).strip()
        action = str(item.get("action", "")).strip()
        if not command and not action:
            continue
        row = {
            "id": cid,
            "label": label,
            "scope": scope,
        }
        if command:
            row["command"] = command
        if action:
            row["action"] = action
        out.append(row)
    return out


def load_custom_hotkeys(data: object) -> list[dict[str, str]]:
    raw = data.get("custom_hotkeys", []) if isinstance(data, dict) else []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        hid = str(item.get("id", "")).strip() or f"custom_hotkey_{idx + 1}"
        if hid in seen:
            continue
        seen.add(hid)
        hotkey = str(item.get("hotkey", "")).strip().lower()
        target = str(item.get("target", "")).strip()
        if not hotkey or not target:
            continue
        out.append(
            {
                "id": hid,
                "hotkey": hotkey,
                "target": target,
            }
        )
    return out


def load_create_templates(data: object) -> list[dict[str, object]]:
    raw = data.get("create_templates", []) if isinstance(data, dict) else []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        options_raw = item.get("options", [])
        options: list[str] = []
        if isinstance(options_raw, list):
            options = [str(v).strip() for v in options_raw if str(v).strip()]
        template = str(item.get("template", "")).strip() or None
        tags_raw = item.get("tags", [])
        tags = [str(v).strip() for v in tags_raw if str(v).strip()] if isinstance(tags_raw, list) else []
        name = str(item.get("name", key)).strip() or key
        out.append(
            {
                "key": key,
                "name": name,
                "options": options,
                "template": template,
                "tags": tags,
            }
        )
    return out


def load_notes_config(data: object, *, defaults: dict[str, str]) -> dict[str, str]:
    out = dict(defaults)
    raw = data.get("notes", {}) if isinstance(data, dict) else {}
    if not isinstance(raw, dict):
        return out

    path_template = str(raw.get("path_template", out["path_template"]) or "").strip()
    open_command = str(raw.get("open_command", out["open_command"]) or "").strip()
    create_command = str(raw.get("create_command", out["create_command"]) or "").strip()
    if path_template:
        out["path_template"] = path_template
    if open_command:
        out["open_command"] = open_command
    if create_command:
        out["create_command"] = create_command
    return out


def load_reconcile_config(
    data: object,
    *,
    defaults: dict[str, dict[str, object]],
    default_cache_profiles: dict[str, dict[str, dict[str, object]]] | None = None,
) -> dict[str, dict[str, object]]:
    out = {
        "active": dict(defaults["active"]),
        "archive": dict(defaults["archive"]),
    }
    raw = data.get("reconcile", {}) if isinstance(data, dict) else {}
    if not isinstance(raw, dict):
        return out

    profile_source: dict[str, object] = dict(data) if isinstance(data, dict) else {}
    default_profiles = default_cache_profiles or {}
    if isinstance(default_profiles, dict):
        merged_profiles = {
            "all": dict(default_profiles.get("all", {})),
            "active": dict(default_profiles.get("active", {})),
            "archive": dict(default_profiles.get("archive", {})),
        }
        raw_profiles = profile_source.get("cache_profile", {})
        if isinstance(raw_profiles, dict):
            for scope in ("all", "active", "archive"):
                scope_raw = raw_profiles.get(scope, {})
                if not isinstance(scope_raw, dict):
                    continue
                cur = merged_profiles.get(scope, {})
                cur.update(scope_raw)
                merged_profiles[scope] = cur
        profile_source["cache_profile"] = merged_profiles
    profile_table = cache_profile_config.load_cache_profile_table(profile_source)

    def _apply_profile(mode: str, mode_data: dict[str, object]) -> None:
        profile_name = str(mode_data.get("cache_profile", "")).strip()
        if not profile_name:
            return
        resolved = cache_profile_config.resolve_cache_profile(
            profile_name=profile_name,
            view=mode,
            profile_table=profile_table,
            explicit_fields={},
            profile_overrides=mode_data.get("cache_profile_overrides", None),
        )
        out[mode]["interval_s"] = max(1.0, float(resolved.get("update_interval_s", 5.0)))
        out[mode]["batch_size"] = max(1, int(resolved.get("update_batch_size", 1)))
        out[mode]["parallelism"] = max(1, int(resolved.get("max_parallelism", 1)))
        out[mode]["use_usage_score"] = bool(resolved.get("use_usage_score", True))
        out[mode]["usage_weight"] = max(0.0, float(resolved.get("usage_weight", 1.0)))
        out[mode]["stale_boost"] = bool(resolved.get("stale_boost", True))

    for mode in ("active", "archive"):
        mode_raw = raw.get(mode, {})
        mode_data = dict(out[mode])
        if isinstance(mode_raw, dict):
            mode_data.update(mode_raw)
        _apply_profile(mode, mode_data)
        if isinstance(mode_raw, dict) and "enabled" in mode_raw:
            out[mode]["enabled"] = bool(mode_raw.get("enabled"))
        try:
            out[mode]["interval_s"] = max(
                1.0,
                float(
                    mode_raw.get("interval_s", out[mode].get("interval_s", 5.0))
                    if isinstance(mode_raw, dict)
                    else out[mode].get("interval_s", 5.0)
                ),
            )
        except (TypeError, ValueError):
            pass
        try:
            out[mode]["batch_size"] = max(
                1,
                int(
                    mode_raw.get("batch_size", out[mode].get("batch_size", 1))
                    if isinstance(mode_raw, dict)
                    else out[mode].get("batch_size", 1)
                ),
            )
        except (TypeError, ValueError):
            pass
        try:
            out[mode]["stale_interval_s"] = max(
                0.05,
                float(
                    mode_raw.get(
                        "stale_interval_s",
                        out[mode].get("stale_interval_s", out[mode]["interval_s"]),
                    )
                    if isinstance(mode_raw, dict)
                    else out[mode].get("stale_interval_s", out[mode]["interval_s"])
                ),
            )
        except (TypeError, ValueError):
            pass
        try:
            out[mode]["stale_batch_size"] = max(
                1,
                int(
                    mode_raw.get(
                        "stale_batch_size",
                        out[mode].get("stale_batch_size", out[mode]["batch_size"]),
                    )
                    if isinstance(mode_raw, dict)
                    else out[mode].get("stale_batch_size", out[mode]["batch_size"])
                ),
            )
        except (TypeError, ValueError):
            pass
        try:
            out[mode]["stale_parallelism"] = max(
                1,
                int(
                    mode_raw.get(
                        "stale_parallelism",
                        out[mode].get("stale_parallelism", out[mode].get("parallelism", 1)),
                    )
                    if isinstance(mode_raw, dict)
                    else out[mode].get("stale_parallelism", out[mode].get("parallelism", 1))
                ),
            )
        except (TypeError, ValueError):
            pass
        try:
            out[mode]["parallelism"] = max(
                1,
                int(
                    mode_raw.get("parallelism", out[mode].get("parallelism", 1))
                    if isinstance(mode_raw, dict)
                    else out[mode].get("parallelism", 1)
                ),
            )
        except (TypeError, ValueError):
            pass
        if isinstance(mode_raw, dict) and "use_usage_score" in mode_raw:
            out[mode]["use_usage_score"] = bool(mode_raw.get("use_usage_score"))
        try:
            out[mode]["usage_weight"] = max(
                0.0,
                float(
                    mode_raw.get("usage_weight", out[mode].get("usage_weight", 1.0))
                    if isinstance(mode_raw, dict)
                    else out[mode].get("usage_weight", 1.0)
                ),
            )
        except (TypeError, ValueError):
            pass
        if isinstance(mode_raw, dict) and "stale_boost" in mode_raw:
            out[mode]["stale_boost"] = bool(mode_raw.get("stale_boost"))
    return out


def nested_discovery_enabled(data: object) -> bool:
    if not isinstance(data, dict):
        return False
    discovery = data.get("discovery", {})
    if not isinstance(discovery, dict):
        return False
    nested = discovery.get("nested", {})
    if isinstance(nested, dict) and "enabled" in nested:
        return bool(nested.get("enabled"))
    if "nested_enabled" in discovery:
        return bool(discovery.get("nested_enabled"))
    return False


def set_nested_discovery_enabled(data: object, *, enabled: bool) -> dict[str, object]:
    out = dict(data) if isinstance(data, dict) else {}
    discovery = out.get("discovery", {})
    if not isinstance(discovery, dict):
        discovery = {}
    nested = discovery.get("nested", {})
    if not isinstance(nested, dict):
        nested = {}
    nested["enabled"] = bool(enabled)
    discovery["nested"] = nested
    out["discovery"] = discovery
    return out
