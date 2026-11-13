"""Keep the files a ``b`` start-up reads warm, so the TUI appears quickly.

Starting the TUI opens roughly 750 module files (Python, textual, rich). On a
machine with real-time anti-virus scanning every one of those files is checked
again once it has fallen out of the file cache, which is why the first start
after an idle period spends seconds on imports while a start right after it is
fast: measured on a work Mac, module loading took 3.35 s cold and 0.54 s warm.

The repetitive work therefore belongs in ``b daemon``: it re-reads the same
files on an interval, which keeps both the file cache and the scanner's verdict
for each file warm. The daemon never imports the TUI itself, so it cannot know
the list from its own ``sys.modules``; instead each TUI start records what it
loaded, and the daemon warms that list.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import sys
from collections.abc import Iterable
from pathlib import Path

DEFAULT_LIST_PATH = Path("~/.local/state/homebase/startup-files.txt")

_READ_CHUNK = 1 << 20


def module_files() -> list[Path]:
    """Every file this process imported, plus its compiled counterpart."""
    found: dict[str, None] = {}
    for module in list(sys.modules.values()):
        name = getattr(module, "__file__", None)
        if not name:
            continue
        found.setdefault(name, None)
        if name.endswith(".py"):
            try:
                found.setdefault(importlib.util.cache_from_source(name), None)
            except (NotImplementedError, ValueError):
                continue
    return [Path(name) for name in sorted(found)]


def record_module_files(path: Path | None = None) -> int:
    """Write this process' module files for the daemon to warm later."""
    target = (path or DEFAULT_LIST_PATH).expanduser()
    paths = module_files()
    body = "".join(f"{item}\n" for item in paths)
    tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(target)
    except OSError:
        # Warming is an optimisation; failing to record must not break a start.
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        return 0
    return len(paths)


def read_module_files(path: Path | None = None) -> list[Path]:
    """The list recorded by the last TUI start; empty when there is none."""
    target = (path or DEFAULT_LIST_PATH).expanduser()
    try:
        body = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return [Path(line) for line in body.splitlines() if line.strip()]


def warm_files(paths: Iterable[Path]) -> tuple[int, int]:
    """Read every file through; returns how many were read and their size."""
    files = 0
    total = 0
    for path in paths:
        try:
            with path.open("rb") as handle:
                while chunk := handle.read(_READ_CHUNK):
                    total += len(chunk)
        except OSError:
            continue
        files += 1
    return files, total


__all__ = [
    "DEFAULT_LIST_PATH",
    "module_files",
    "read_module_files",
    "record_module_files",
    "warm_files",
]
