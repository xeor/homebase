from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rich.text import Text


def _render_template(text: str, context: dict[str, str]) -> str:
    pattern = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
    return pattern.sub(lambda m: str(context.get(m.group(1), "")), text)


def _strip_wrapping_quotes(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def _resolve_check_path(raw: str, *, root: Path, template_context: dict[str, str] | None) -> Path:
    rendered = _render_template(raw, template_context or {}).strip()
    rendered = _strip_wrapping_quotes(rendered)
    expanded = os.path.expandvars(rendered)
    candidate = Path(expanded).expanduser()
    if candidate.is_absolute():
        return candidate
    return root / candidate


def detect_properties(
    path: Path,
    *,
    property_defs: list[Any],
    normalize_keys: Callable[[list[str]], list[str]],
    template_context: dict[str, str] | None = None,
) -> list[str]:
    props: list[str] = []
    for pdef in property_defs:
        try:
            if getattr(pdef, "matcher", None) is not None and pdef.matches(path):
                props.append(str(pdef.key))
                continue
            matched = False
            for rel in getattr(pdef, "file_exists", ()):
                target = _resolve_check_path(str(rel), root=path, template_context=template_context)
                if target.is_file():
                    matched = True
                    break
            if not matched:
                for rel in getattr(pdef, "dir_exists", ()):
                    target = _resolve_check_path(str(rel), root=path, template_context=template_context)
                    if target.is_dir():
                        matched = True
                        break
            if not matched:
                for rel in getattr(pdef, "path_exists", ()):
                    target = _resolve_check_path(str(rel), root=path, template_context=template_context)
                    if target.exists():
                        matched = True
                        break
            if matched:
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
    normalize_keys: Callable[[list[str]], list[str]],
) -> Text:
    by_key = {str(p.key): p for p in all_defs}
    out = Text()
    first = True
    for key in normalize_keys(keys):
        pdef = by_key.get(key)
        if pdef is None:
            continue
        if not first:
            out.append(" ")
        first = False
        style = str(getattr(pdef, "color", "") or "").strip()
        if style:
            out.append(str(pdef.token), style=style)
            continue
        out.append(str(pdef.token), style=style)
    if not out.plain:
        out.append("-")
    return out


def property_display_lines(
    keys: list[str],
    *,
    all_defs: list[Any],
    normalize_keys: Callable[[list[str]], list[str]],
) -> list[str]:
    by_key = {str(p.key): p for p in all_defs}
    lines: list[str] = []
    for key in normalize_keys(keys):
        pdef = by_key.get(key)
        if pdef is None:
            continue
        token = str(pdef.token)
        label = str(pdef.label)
        style = str(getattr(pdef, "color", "") or "").strip()
        if style:
            lines.append(f"[{style}]{token}[/] ({label})")
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
