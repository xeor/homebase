from __future__ import annotations


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
        if not command:
            continue
        out.append(
            {
                "id": cid,
                "label": label,
                "scope": scope,
                "command": command,
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
) -> dict[str, dict[str, object]]:
    out = {
        "active": dict(defaults["active"]),
        "archive": dict(defaults["archive"]),
    }
    raw = data.get("reconcile", {}) if isinstance(data, dict) else {}
    if not isinstance(raw, dict):
        return out

    for mode in ("active", "archive"):
        mode_data = raw.get(mode, {})
        if not isinstance(mode_data, dict):
            continue
        if "enabled" in mode_data:
            out[mode]["enabled"] = bool(mode_data.get("enabled"))
        try:
            out[mode]["interval_s"] = max(
                1.0,
                float(mode_data.get("interval_s", out[mode]["interval_s"])),
            )
        except (TypeError, ValueError):
            pass
        try:
            out[mode]["batch_size"] = max(
                1,
                int(mode_data.get("batch_size", out[mode]["batch_size"])),
            )
        except (TypeError, ValueError):
            pass
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
