from __future__ import annotations

import string
from typing import Iterable, Sequence

from ...core.constants import BUILTIN_HOTKEYS, CONTEXT_RESERVED_HOTKEYS
from ...core.models import KeyEntry

LETTERS = string.ascii_lowercase
FUNCTION_KEYS = tuple(f"f{i}" for i in range(1, 13))
RECOMMENDED_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("function keys", FUNCTION_KEYS),
    ("alt+<letter>", tuple(f"alt+{c}" for c in LETTERS)),
    ("ctrl+alt+<letter>", tuple(f"ctrl+alt+{c}" for c in LETTERS)),
    ("ctrl+shift+<letter>", tuple(f"ctrl+shift+{c}" for c in LETTERS)),
)


def _fmt_rows(rows: Sequence[tuple[str, ...]], headers: tuple[str, ...]) -> Iterable[str]:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, col in enumerate(row):
            widths[i] = max(widths[i], len(col))

    def line(cols: Iterable[str]) -> str:
        return "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(cols))

    yield line(headers)
    yield line("-" * w for w in widths)
    for row in rows:
        yield line(row)


def _free_keys(taken: set[str], candidates: tuple[str, ...]) -> list[str]:
    return [k for k in candidates if k not in taken]


def cmd_help_hotkeys(
    *,
    keys: dict[str, KeyEntry] | dict[str, object],
) -> int:
    user_map: dict[str, tuple[str, str]] = {}
    for key, entry in keys.items():
        action = str(getattr(entry, "action", "")).strip()
        label = str(getattr(entry, "label", "")).strip()
        user_map[str(key).strip().lower()] = (action, label)

    print("BUILT-IN (cannot be overridden)\n")
    builtin_rows = [
        (hk.key, hk.action, hk.label) for hk in BUILTIN_HOTKEYS
    ]
    for line in _fmt_rows(builtin_rows, ("KEY", "ACTION", "LABEL")):
        print(line)

    print("\nCONTEXT-RESERVED (active in filter input / select mode)\n")
    ctx_rows = [
        (key, mode, label) for key, mode, label in CONTEXT_RESERVED_HOTKEYS
    ]
    for line in _fmt_rows(ctx_rows, ("KEY", "MODE", "LABEL")):
        print(line)

    print("\nUSER (from `keys:` in .homebase/config.yaml)\n")
    if user_map:
        user_rows = [
            (key, action, label if label else "-")
            for key, (action, label) in sorted(user_map.items())
        ]
        for line in _fmt_rows(user_rows, ("KEY", "ACTION", "LABEL")):
            print(line)
    else:
        print("(none)")

    taken: set[str] = set(user_map.keys())
    for hk in BUILTIN_HOTKEYS:
        taken.add(hk.key)
    for key, _mode, _label in CONTEXT_RESERVED_HOTKEYS:
        taken.add(key)

    print("\nRECOMMENDED FREE KEYS (good slots for `keys:` overrides)\n")
    for name, candidates in RECOMMENDED_PATTERNS:
        free = _free_keys(taken, candidates)
        if not free:
            continue
        print(f"  {name}: {', '.join(free)}")
    return 0
