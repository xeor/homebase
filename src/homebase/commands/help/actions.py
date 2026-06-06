from __future__ import annotations

from typing import Iterable


def cmd_help_actions(
    *,
    actions: dict[str, object],
    favorites: list[dict[str, object]],
    source_filter: str = "",
    bound_filter: str = "",
    view_filter: str = "",
    show_defaults: bool = False,
) -> int:
    _ = show_defaults
    fav_map: dict[str, list[str]] = {}
    key_map: dict[str, list[str]] = {}
    for idx, fav in enumerate(favorites, start=1):
        aid = str(fav.get("target", "")).strip()
        if not aid:
            continue
        if aid.startswith("action:"):
            aid = aid.split(":", 1)[1]
        if bool(fav.get("favorite", False)):
            fav_map.setdefault(aid, []).append(f"fav:{idx}")
        hotkey = str(fav.get("hotkey", "")).strip()
        if hotkey:
            key_map.setdefault(aid, []).append(hotkey)

    rows: list[tuple[str, str, str, str, str, str, str]] = []
    for aid, action in sorted(actions.items()):
        source = str(getattr(action, "source", "builtin"))
        label = str(getattr(action, "label", aid))
        kind = str(getattr(action, "kind", "-"))
        scope = str(getattr(action, "scope", "-"))
        multi = str(getattr(action, "multi", "-"))
        view_scope = tuple(getattr(action, "view_scope", ("active", "archive")))
        bound = fav_map.get(aid, []) + key_map.get(aid, [])
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
