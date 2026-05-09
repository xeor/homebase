from __future__ import annotations

from typing import Iterable


def cmd_help_actions(
    *,
    actions: dict[str, object],
    hotbar: list[object],
    keys: dict[str, object],
    source_filter: str = "",
    bound_filter: str = "",
    view_filter: str = "",
    show_defaults: bool = False,
) -> int:
    _ = show_defaults
    hotbar_map: dict[str, list[str]] = {}
    for idx, entry in enumerate(hotbar, start=1):
        aid = str(getattr(entry, "action", "")).strip()
        if aid:
            hotbar_map.setdefault(aid, []).append(f"hotbar:{idx}")
    key_map: dict[str, list[str]] = {}
    for key, entry in keys.items():
        aid = str(getattr(entry, "action", "")).strip()
        if aid:
            key_map.setdefault(aid, []).append(str(key))

    rows: list[tuple[str, str, str, str, str, str, str]] = []
    for aid, action in sorted(actions.items()):
        source = str(getattr(action, "source", "builtin"))
        label = str(getattr(action, "label", aid))
        kind = str(getattr(action, "kind", "-"))
        scope = str(getattr(action, "scope", "-"))
        multi = str(getattr(action, "multi", "-"))
        view_scope = tuple(getattr(action, "view_scope", ("active", "archive")))
        bound = hotbar_map.get(aid, []) + key_map.get(aid, [])
        bound_text = " ".join(bound) if bound else "-"

        if source_filter and source != source_filter:
            continue
        if bound_filter == "bound" and not bound:
            continue
        if bound_filter == "unbound" and bound:
            continue
        if view_filter and view_filter not in view_scope:
            continue
        rows.append((source, aid, label, kind, scope, multi, bound_text))

    headers = ("SOURCE", "ID", "LABEL", "KIND", "SCOPE", "MULTI", "BOUND")
    widths = [len(h) for h in headers]
    for row in rows:
        for i, col in enumerate(row):
            widths[i] = max(widths[i], len(col))

    def fmt(cols: Iterable[str]) -> str:
        return "  ".join(str(col).ljust(widths[i]) for i, col in enumerate(cols))

    print(fmt(headers))
    print(fmt("-" * w for w in widths))
    for row in rows:
        print(fmt(row))
    return 0
