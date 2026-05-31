from __future__ import annotations

import re

from ..core.constants import reserved_hotkeys
from ..core.models import Action, BuiltinActionMeta, HotbarEntry, KeyEntry
from . import cache_profile as cache_profile_config

_VAR_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _allowed_vars_for_action(*, scope: str, multi: str, kind: str) -> set[str]:
    always = {
        "base_dir",
        "base_dir_q",
        "base_name",
        "archive_dir",
        "archive_dir_q",
        "active_count",
        "archive_count",
        "wip_count",
        "count",
        "view",
        "filter",
        "filter_q",
        "now",
        "now_iso",
        "now_ts",
        "today",
        "user",
        "home",
        "home_q",
    }
    per_row = {
        "path",
        "path_q",
        "rel_path",
        "rel_path_q",
        "name",
        "name_q",
        "parent_path",
        "parent_path_q",
        "branch",
        "branch_q",
        "dirty",
        "description",
        "description_q",
        "tags",
        "tags_space",
        "tags_space_q",
        "properties",
        "suffix",
        "wip",
        "archived",
        "packed",
        "created",
        "created_iso",
        "created_ts",
        "modified",
        "modified_iso",
        "modified_ts",
        "active",
        "active_iso",
        "active_ts",
        "archived_at",
        "archived_at_iso",
        "archived_at_ts",
        "size_bytes",
        "size_human",
        "note_path",
        "note_path_q",
    }
    listed = {"paths", "paths_q", "rel_paths", "rel_paths_q", "names", "names_q"}
    filepicker = {"selection", "selection_q"}
    out = set(always)
    if scope == "target" and multi == "per_row":
        out.update(per_row)
    if scope == "target" and multi == "joined":
        out.update(listed)
    if kind == "filepicker":
        out.update(per_row)
        out.update(filepicker)
    return out


def _validate_template_vars(template_text: str, *, allowed: set[str], field_name: str) -> None:
    unknown = sorted({name for name in _VAR_RE.findall(template_text) if name not in allowed})
    if unknown:
        missing = ", ".join(unknown)
        raise ValueError(f"{field_name} references unavailable template variable(s): {missing}")


def load_actions(data: object, *, builtins: dict[str, BuiltinActionMeta]) -> dict[str, Action]:
    if not isinstance(data, dict):
        data = {}
    raw = data.get("actions", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("`actions` must be a map of action id -> action definition")

    merged: dict[str, Action] = {}
    for action_id, meta in builtins.items():
        merged[action_id] = Action(
            id=action_id,
            label=meta.default_label,
            kind="builtin",
            scope=meta.scope,
            multi="joined",
            confirm=meta.default_confirm_prompt,
            hidden=False,
            view_scope=meta.view_scope,
            source="builtin",
        )

    seen_note_ops: dict[str, str] = {}
    for action_id, item in raw.items():
        aid = str(action_id).strip()
        if not aid:
            continue
        if not isinstance(item, dict):
            raise ValueError(f"action {aid!r} must be a mapping")

        if aid in builtins:
            allowed_keys = {"label", "confirm"}
            extra = sorted(set(item) - allowed_keys)
            if extra:
                raise ValueError(
                    f"{aid!r} is built-in; only `label` and `confirm` are overridable"
                )
            if "confirm" in item and not isinstance(item.get("confirm"), str):
                raise ValueError(f"{aid!r} built-in `confirm` must be a string")
            existing = merged[aid]
            merged[aid] = Action(
                id=aid,
                label=str(item.get("label", existing.label)).strip() or existing.label,
                kind=existing.kind,
                scope=existing.scope,
                multi=existing.multi,
                command=existing.command,
                list_command=existing.list_command,
                op=existing.op,
                confirm=str(item["confirm"]) if "confirm" in item else existing.confirm,
                hidden=existing.hidden,
                view_scope=existing.view_scope,
                source="overridden",
            )
            continue

        kind = str(item.get("kind", "")).strip().lower()
        if kind not in {"shell", "filepicker", "note"}:
            raise ValueError(f"action {aid!r} must define valid `kind` (shell|filepicker|note)")
        scope = str(item.get("scope", "target")).strip().lower() or "target"
        if scope not in {"target", "workspace"}:
            raise ValueError(f"action {aid!r} has invalid scope {scope!r}")
        multi = str(item.get("multi", "joined")).strip().lower() or "joined"
        if multi not in {"joined", "per_row"}:
            raise ValueError(f"action {aid!r} has invalid multi {multi!r}")

        label = str(item.get("label", aid)).strip() or aid
        confirm: bool | str | None = item.get("confirm")
        hidden = bool(item.get("hidden", False))
        view_scope_raw = item.get("view_scope", ["active", "archive"])
        if isinstance(view_scope_raw, list):
            view_scope = tuple(
                v for v in [str(x).strip() for x in view_scope_raw] if v in {"active", "archive"}
            )
            if not view_scope:
                view_scope = ("active", "archive")
        else:
            view_scope = ("active", "archive")

        command = str(item.get("command", "")).strip()
        list_command = str(item.get("list", "")).strip() or str(item.get("list_command", "")).strip()
        op = str(item.get("op", "")).strip() or str(item.get("note_command", "")).strip()

        if kind == "shell":
            if not command:
                raise ValueError(f"action {aid!r} kind=shell requires `command`")
            _validate_template_vars(
                command,
                allowed=_allowed_vars_for_action(scope=scope, multi=multi, kind=kind),
                field_name=f"action {aid!r} command",
            )
        elif kind == "filepicker":
            if scope != "target":
                raise ValueError(f"action {aid!r} kind=filepicker requires scope=target")
            if not list_command or not command:
                raise ValueError(f"action {aid!r} kind=filepicker requires `list` and `command`")
            _validate_template_vars(
                list_command,
                allowed=_allowed_vars_for_action(scope="target", multi="per_row", kind=kind),
                field_name=f"action {aid!r} list",
            )
            _validate_template_vars(
                command,
                allowed=_allowed_vars_for_action(scope="target", multi="per_row", kind=kind),
                field_name=f"action {aid!r} command",
            )
            multi = "joined"
        elif kind == "note":
            if scope != "target":
                raise ValueError(f"action {aid!r} kind=note requires scope=target")
            if op != "add_log":
                raise ValueError(f"action {aid!r} note `op` must be `add_log`")
            previous = seen_note_ops.get(op)
            if previous is not None:
                raise ValueError(
                    f"duplicate note op {op!r}: defined on both {previous!r} and {aid!r}"
                )
            seen_note_ops[op] = aid
            multi = "joined"

        merged[aid] = Action(
            id=aid,
            label=label,
            kind=kind,
            scope="workspace" if scope == "workspace" else "target",
            multi="per_row" if multi == "per_row" else "joined",
            command=command or None,
            list_command=list_command or None,
            op=op or None,
            confirm=confirm,
            hidden=hidden,
            view_scope=view_scope,
            source="config",
        )
    return merged


def load_hotbar(data: object, *, actions: dict[str, Action]) -> list[HotbarEntry]:
    if not isinstance(data, dict):
        return []
    raw = data.get("hotbar", [])
    if not isinstance(raw, list):
        raise ValueError("`hotbar` must be a list")
    out: list[HotbarEntry] = []
    for item in raw:
        action_id = ""
        label = ""
        style_rules: list[dict[str, str]] = []
        if isinstance(item, str):
            action_id = item.strip()
        elif isinstance(item, dict):
            action_id = str(item.get("action", "")).strip()
            label = str(item.get("label", "")).strip()
            if "key" in item:
                raise ValueError("hotbar entries cannot contain `key` field")
            raw_style = item.get("style", [])
            if raw_style not in (None, ""):
                if not isinstance(raw_style, list):
                    raise ValueError("hotbar style must be a list")
                for idx, raw_rule in enumerate(raw_style, start=1):
                    if not isinstance(raw_rule, dict):
                        raise ValueError(f"hotbar style rule #{idx} must be a map")
                    bg_color = str(raw_rule.get("bg_color", "")).strip()
                    fg_color = str(raw_rule.get("fg_color", "")).strip()
                    when = str(raw_rule.get("when", "")).strip()
                    bold = bool(raw_rule.get("bold", False))
                    underline = bool(raw_rule.get("underline", False))
                    italic = bool(raw_rule.get("italic", False))
                    if not bg_color and not fg_color and not (bold or underline or italic):
                        raise ValueError(
                            f"hotbar style rule #{idx} must set at least one style field"
                        )
                    if bg_color and not _HEX_COLOR_RE.fullmatch(bg_color):
                        raise ValueError(
                            f"hotbar style rule #{idx} bg_color must be #RRGGBB"
                        )
                    if fg_color and not _HEX_COLOR_RE.fullmatch(fg_color):
                        raise ValueError(
                            f"hotbar style rule #{idx} fg_color must be #RRGGBB"
                        )
                    if not when:
                        raise ValueError(f"hotbar style rule #{idx} missing when")
                    style_rule: dict[str, str] = {"when": when}
                    if bg_color:
                        style_rule["bg_color"] = bg_color
                    if fg_color:
                        style_rule["fg_color"] = fg_color
                    if bold:
                        style_rule["bold"] = "1"
                    if underline:
                        style_rule["underline"] = "1"
                    if italic:
                        style_rule["italic"] = "1"
                    style_rules.append(style_rule)
        if not action_id:
            continue
        action = actions.get(action_id)
        if action is None:
            raise ValueError(f"hotbar action not found: {action_id!r}")
        if action.scope != "target":
            raise ValueError(
                f"{action_id!r} cannot be on the hotbar — only target-scope actions are eligible. Bind it via `keys:` instead."
            )
        out.append(HotbarEntry(action=action_id, label=label, style=tuple(style_rules)))
    return out


def load_keys(data: object, *, actions: dict[str, Action]) -> dict[str, KeyEntry]:
    if not isinstance(data, dict):
        return {}
    raw = data.get("keys", {})
    if not isinstance(raw, dict):
        raise ValueError("`keys` must be a map")
    reserved = reserved_hotkeys()
    out: dict[str, KeyEntry] = {}
    for key_name, value in raw.items():
        hotkey = str(key_name).strip().lower()
        if not hotkey:
            continue
        if hotkey in out:
            raise ValueError(f"duplicate key binding: {hotkey!r}")
        if hotkey in reserved:
            raise ValueError(
                f"key binding collision: {hotkey!r} is reserved by {reserved[hotkey]}. "
                f"Run `b help hotkeys` to see all bindings and free slots."
            )
        if isinstance(value, str):
            action_id = value.strip()
            label = ""
        elif isinstance(value, dict):
            action_id = str(value.get("action", "")).strip()
            label = str(value.get("label", "")).strip()
        else:
            raise ValueError(f"key binding {hotkey!r} must be string or map")
        if not action_id:
            continue
        if action_id not in actions:
            raise ValueError(f"key binding action not found: {action_id!r}")
        out[hotkey] = KeyEntry(action=action_id, label=label)
    return out


def merge_actions(
    builtins: dict[str, BuiltinActionMeta],
    user_actions: dict[str, dict[str, object]] | None,
    custom_actions_legacy: list[dict[str, str]],
) -> dict[str, Action]:
    merged: dict[str, Action] = {}
    override_map = user_actions or {}
    for action_id, meta in builtins.items():
        override = override_map.get(action_id, {})
        label = str(override.get("label", meta.default_label)).strip() or meta.default_label
        source = "overridden" if "label" in override else "builtin"
        merged[action_id] = Action(
            id=action_id,
            label=label,
            kind="builtin",
            scope=meta.scope,
            multi="joined",
            confirm=meta.default_confirm_prompt,
            hidden=False,
            view_scope=meta.view_scope,
            source=source,
        )

    for legacy in custom_actions_legacy:
        cid = str(legacy.get("id", "")).strip()
        if not cid:
            continue
        label = str(legacy.get("label", cid)).strip() or cid
        scope_raw = str(legacy.get("scope", "target")).strip().lower()
        scope = "workspace" if scope_raw == "global" else "target"
        if cid in merged:
            current = merged[cid]
            merged[cid] = Action(
                id=current.id,
                label=label,
                kind=current.kind,
                scope=current.scope,
                multi=current.multi,
                command=current.command,
                list_command=current.list_command,
                op=current.op,
                confirm=current.confirm,
                hidden=current.hidden,
                view_scope=current.view_scope,
                source="overridden",
            )
            continue

        command = str(legacy.get("command", "")).strip()
        list_command = str(legacy.get("list_command", "")).strip()
        run_command = str(legacy.get("run_command", "")).strip()
        note_command = str(legacy.get("note_command", "")).strip()
        loop_on_multi = str(legacy.get("loop_on_multi", "")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if list_command and run_command:
            merged[cid] = Action(
                id=cid,
                label=label,
                kind="filepicker",
                scope="target",
                multi="joined",
                command=run_command,
                list_command=list_command,
                source="config",
            )
            continue
        if note_command:
            merged[cid] = Action(
                id=cid,
                label=label,
                kind="note",
                scope="target",
                multi="joined",
                op=note_command,
                source="config",
            )
            continue
        if command:
            merged[cid] = Action(
                id=cid,
                label=label,
                kind="shell",
                scope=scope,
                multi="per_row" if loop_on_multi else "joined",
                command=command,
                source="config",
            )
    return merged


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


def load_notes_config(data: object, *, defaults: dict[str, object]) -> dict[str, object]:
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

    raw_log = raw.get("log", {})
    default_log = out.get("log", {}) if isinstance(out.get("log", {}), dict) else {}
    log_out = dict(default_log) if isinstance(default_log, dict) else {}
    if isinstance(raw_log, dict):
        raw_section = raw_log.get("section", {})
        default_section = (
            log_out.get("section", {}) if isinstance(log_out.get("section", {}), dict) else {}
        )
        section_out = dict(default_section) if isinstance(default_section, dict) else {}
        if isinstance(raw_section, dict):
            title = str(raw_section.get("title", section_out.get("title", "Log")) or "").strip()
            if title:
                section_out["title"] = title
            try:
                level = int(raw_section.get("level", section_out.get("level", 2)) or 2)
            except (TypeError, ValueError):
                level = int(section_out.get("level", 2) or 2)
            section_out["level"] = max(1, min(6, level))
        if section_out:
            log_out["section"] = section_out

        raw_entry = raw_log.get("entry", {})
        default_entry = (
            log_out.get("entry", {}) if isinstance(log_out.get("entry", {}), dict) else {}
        )
        entry_out = dict(default_entry) if isinstance(default_entry, dict) else {}
        if isinstance(raw_entry, dict):
            timestamp_format = str(
                raw_entry.get("timestamp_format", entry_out.get("timestamp_format", "iso-seconds"))
                or ""
            ).strip()
            if timestamp_format:
                entry_out["timestamp_format"] = timestamp_format
        if entry_out:
            log_out["entry"] = entry_out
    if log_out:
        out["log"] = log_out

    raw_rename = raw.get("rename", {})
    default_rename = out.get("rename", {}) if isinstance(out.get("rename", {}), dict) else {}
    rename_out = dict(default_rename) if isinstance(default_rename, dict) else {}
    if isinstance(raw_rename, dict):
        if "enabled" in raw_rename:
            rename_out["enabled"] = bool(raw_rename.get("enabled"))
        command = str(raw_rename.get("command", rename_out.get("command", "")) or "").strip()
        rename_out["command"] = command
    if rename_out:
        out["rename"] = rename_out

    for key in ("archive", "restore"):
        if key not in raw:
            continue
        raw_sync = raw.get(key, {})
        default_sync = out.get(key, {}) if isinstance(out.get(key, {}), dict) else {}
        sync_out = dict(default_sync) if isinstance(default_sync, dict) else {}
        if isinstance(raw_sync, dict):
            if "enabled" in raw_sync:
                sync_out["enabled"] = bool(raw_sync.get("enabled"))
            command = str(raw_sync.get("command", sync_out.get("command", "")) or "").strip()
            sync_out["command"] = command
        if sync_out:
            out[key] = sync_out
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
