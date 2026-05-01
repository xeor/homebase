from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from rich.text import Text


def detect_properties(path: Path, *, property_defs: list[Any], normalize_keys: Callable[[list[str]], list[str]]) -> list[str]:
    props: list[str] = []
    for pdef in property_defs:
        try:
            if pdef.matches(path):
                props.append(str(pdef.key))
        except (OSError, TypeError, ValueError, AttributeError):
            continue
    return normalize_keys(props)


def all_property_defs(dynamic_property_defs: list[Any], property_defs: list[Any]) -> list[Any]:
    out: list[Any] = []
    seen: set[str] = set()
    for pdef in dynamic_property_defs + property_defs:
        key = str(pdef.key)
        if key in seen:
            continue
        seen.add(key)
        out.append(pdef)
    return out


def normalize_property_keys(
    keys: list[str],
    *,
    dynamic_property_defs: list[Any],
    property_defs: list[Any],
) -> list[str]:
    dynamic_order = {str(p.key): i for i, p in enumerate(dynamic_property_defs)}
    static_order = {str(p.key): i for i, p in enumerate(property_defs)}

    uniq: list[str] = []
    seen: set[str] = set()
    for key in keys:
        clean = str(key).strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        uniq.append(clean)

    def sort_key(key: str) -> tuple[int, int, str]:
        if key in dynamic_order:
            return (0, dynamic_order[key], key)
        if key in static_order:
            return (1, static_order[key], key)
        return (2, 9999, key)

    return sorted(uniq, key=sort_key)


def property_tokens(keys: list[str], *, all_defs: list[Any], normalize_keys: Callable[[list[str]], list[str]]) -> str:
    token_by_key = {str(p.key): str(p.token) for p in all_defs}
    ordered = normalize_keys(keys)
    return " ".join(token_by_key[key] for key in ordered if key in token_by_key)


def property_tokens_text(
    keys: list[str],
    *,
    all_defs: list[Any],
    dynamic_property_defs: list[Any],
    normalize_keys: Callable[[list[str]], list[str]],
    property_key_err: str,
    property_key_warn: str,
    color_error_hex: str,
    color_warn_hex: str,
    color_dynamic_env_hex: str,
    color_dynamic_file_hex: str,
    color_dynamic_state_hex: str,
    color_info_hex: str,
) -> Text:
    by_key = {str(p.key): p for p in all_defs}
    dynamic_keys = {str(p.key) for p in dynamic_property_defs}
    out = Text()
    first = True
    for key in normalize_keys(keys):
        pdef = by_key.get(key)
        if pdef is None:
            continue
        if not first:
            out.append(" ")
        first = False
        style = ""
        if key == property_key_err:
            style = color_error_hex
        elif key == property_key_warn:
            style = color_warn_hex
        elif key == "act":
            style = color_dynamic_env_hex
        elif key in {"rm", "n"}:
            style = color_dynamic_file_hex
        elif key == "pkg":
            style = color_dynamic_state_hex
        elif key in dynamic_keys:
            style = color_info_hex
        out.append(str(pdef.token), style=style)
    if not out.plain:
        out.append("-")
    return out


def property_display_lines(
    keys: list[str],
    *,
    all_defs: list[Any],
    dynamic_property_defs: list[Any],
    normalize_keys: Callable[[list[str]], list[str]],
    property_key_err: str,
    property_key_warn: str,
    color_error_hex: str,
    color_warn_hex: str,
    color_dynamic_env_hex: str,
    color_dynamic_file_hex: str,
    color_dynamic_state_hex: str,
    color_info_hex: str,
) -> list[str]:
    by_key = {str(p.key): p for p in all_defs}
    dynamic_keys = {str(p.key) for p in dynamic_property_defs}
    lines: list[str] = []
    for key in normalize_keys(keys):
        pdef = by_key.get(key)
        if pdef is None:
            continue
        token = str(pdef.token)
        label = str(pdef.label)
        if key == property_key_err:
            lines.append(f"[{color_error_hex}]{token}[/] ({label})")
        elif key == property_key_warn:
            lines.append(f"[{color_warn_hex}]{token}[/] ({label})")
        elif key == "act":
            lines.append(f"[{color_dynamic_env_hex}]{token}[/] ({label})")
        elif key in {"rm", "n"}:
            lines.append(f"[{color_dynamic_file_hex}]{token}[/] ({label})")
        elif key == "pkg":
            lines.append(f"[{color_dynamic_state_hex}]{token}[/] ({label})")
        elif key in dynamic_keys:
            lines.append(f"[{color_info_hex}]{token}[/] ({label})")
        else:
            lines.append(f"{token} ({label})")
    return lines


def property_alias_set(key: str, *, all_defs: list[Any]) -> set[str]:
    out = {key.lower()}
    pdef = next((x for x in all_defs if str(x.key) == key), None)
    if pdef is None:
        return out
    out.add(str(pdef.label).lower())
    out.add(str(pdef.token).lower())
    return out
