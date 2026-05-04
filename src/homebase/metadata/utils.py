from __future__ import annotations

from collections.abc import Mapping


def extract_base_meta_fields(data: object) -> tuple[list[str], str, bool]:
    if not isinstance(data, Mapping):
        return [], "", False

    tags_value = data.get("tags", [])
    if isinstance(tags_value, str):
        tags_value = [tags_value]
    if not isinstance(tags_value, list):
        tags_value = []
    tags = [str(tag).strip() for tag in tags_value if str(tag).strip()]

    description = str(data.get("description", "")).strip()
    wip = bool(data.get("wip", False))

    return tags, description, wip


def normalize_base_data(data: Mapping[str, object]) -> tuple[dict[str, object], list[str]]:
    out = dict(data)
    notes: list[str] = []

    raw_tags = out.get("tags", [])
    tags_list: list[str] = []
    if isinstance(raw_tags, str):
        raw_tags = [raw_tags]
    if isinstance(raw_tags, list):
        seen: set[str] = set()
        for tag in raw_tags:
            value = str(tag).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            tags_list.append(value)
    elif raw_tags is not None:
        notes.append("normalized tags")
    out["tags"] = tags_list

    description = out.get("description", "")
    if not isinstance(description, str):
        notes.append("normalized description")
        description = str(description)
    out["description"] = description

    wip = out.get("wip", False)
    if not isinstance(wip, bool):
        notes.append("normalized wip")
        wip = bool(wip)
    out["wip"] = wip

    log_val = out.get("log", {})
    if not isinstance(log_val, dict):
        notes.append("normalized log")
        log_val = {}
    events = log_val.get("events", [])
    if not isinstance(events, list):
        notes.append("normalized log.events")
        events = []
    clean_events = [event for event in events if isinstance(event, dict)][-500:]
    if len(clean_events) != len(events):
        notes.append("normalized log.events entries")
    log_val["events"] = clean_events
    out["log"] = log_val

    return out, notes


def base_meta_schema_issues(
    raw: object,
    *,
    allowed_keys: set[str],
    warning_level: str = "warning",
) -> list[tuple[str, str, str]]:
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        return [(warning_level, "invalid_root", "root must be a mapping")]

    warns: list[str] = []
    tags = raw.get("tags", [])
    if not (isinstance(tags, list) or isinstance(tags, str) or tags is None):
        warns.append("tags has non-standard type")

    if "description" in raw and not isinstance(raw.get("description"), str):
        warns.append("description should be string")

    if "wip" in raw and not isinstance(raw.get("wip"), bool):
        warns.append("wip should be boolean")

    log_val = raw.get("log", {})
    if "log" in raw and not isinstance(log_val, Mapping):
        warns.append("log should be mapping")
    elif isinstance(log_val, Mapping):
        events = log_val.get("events", [])
        if "events" in log_val and not isinstance(events, list):
            warns.append("log.events should be list")

    extra_keys = sorted(key for key in raw.keys() if str(key) not in allowed_keys)
    if extra_keys:
        preview = ", ".join(str(key) for key in extra_keys[:4])
        if len(extra_keys) > 4:
            preview += f" (+{len(extra_keys) - 4} more)"
        warns.append(f"unknown key(s): {preview}")

    if warns:
        return [(warning_level, "schema_warn", "; ".join(warns[:3]))]
    return []
