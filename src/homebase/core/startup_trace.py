"""Timestamped start-up marks, for finding out where ``b``'s start-up goes.

Off by default. Turn it on with ``b --startup-trace`` or by exporting
``HOMEBASE_STARTUP_TRACE``: ``1`` writes to
``~/.local/state/homebase/startup-trace.log``, any other value is taken as the
log path. Whoever launches ``b`` (a shell, a herdr pane, a hotkey script) can
export ``HOMEBASE_STARTUP_EPOCH`` with the unix time it started, and the marks
are then measured from that moment, so the time spent before Python was even
running shows up as the first mark.

Marks are always buffered in memory (a tuple per mark), so a trace enabled from
the command line still contains the marks recorded while the arguments were
being parsed.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from pathlib import Path

from .constants import ENV_STARTUP_EPOCH, ENV_STARTUP_TRACE

DEFAULT_TRACE_PATH = Path("~/.local/state/homebase/startup-trace.log")

# Imported as the first homebase module in the CLI entry point, so this is as
# close to "python finished booting" as the process can observe itself.
_import_time = time.time()

_marks: list[tuple[str, float]] = []
_path: Path | None = None
_resolved = False
_header_written = False
# Marks are written as they happen, so the previous one has to survive a flush
# for the per-step delta to stay correct.
_previous: float | None = None


def _origin() -> float:
    raw = os.environ.get(ENV_STARTUP_EPOCH, "").strip()
    if raw:
        try:
            epoch = float(raw)
        except ValueError:
            return _import_time
        # A clock skew or a stale value from an earlier run would make every
        # mark meaningless, so only accept an epoch this process can follow.
        if 0.0 < epoch <= _import_time:
            return epoch
    return _import_time


def _resolve_path(value: str) -> Path:
    text = value.strip()
    if text in ("1", "true", "yes", "on"):
        return DEFAULT_TRACE_PATH.expanduser()
    return Path(text).expanduser()


def enable(value: str = "1") -> None:
    """Turn tracing on and write everything marked so far."""
    global _path, _resolved
    _path = _resolve_path(value)
    _resolved = True
    _flush()


def _active_path() -> Path | None:
    global _path, _resolved
    if not _resolved:
        _resolved = True
        raw = os.environ.get(ENV_STARTUP_TRACE, "").strip()
        _path = _resolve_path(raw) if raw not in ("", "0", "false", "no", "off") else None
    return _path


def mark(label: str) -> None:
    """Record ``label`` with the time since the start of the run."""
    _marks.append((label, time.time()))
    if _active_path() is not None:
        _flush()


def _format(lines: list[str]) -> str:
    return "".join(line + "\n" for line in lines)


def _flush() -> None:
    global _header_written, _marks, _previous
    path = _active_path()
    if path is None or not _marks:
        return
    origin = _origin()
    if _previous is None:
        _previous = origin
    lines: list[str] = []
    if not _header_written:
        started = datetime.fromtimestamp(origin).isoformat(timespec="milliseconds")
        argv = " ".join(sys.argv[1:])
        lines.append(f"--- pid={os.getpid()} start={started} args={argv or '(none)'}")
    previous = _previous
    for label, stamp in _marks:
        lines.append(f"    +{stamp - origin:7.3f}s  ({stamp - previous:+6.3f}s)  {label}")
        previous = stamp
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(_format(lines))
    except OSError:
        # Tracing must never break a start-up it is only supposed to measure.
        return
    _header_written = True
    _previous = previous
    _marks = []


def reset() -> None:
    """Forget the resolved path and buffered marks (tests)."""
    global _path, _resolved, _header_written, _marks, _previous
    _path = None
    _resolved = False
    _header_written = False
    _previous = None
    _marks = []


__all__ = ["DEFAULT_TRACE_PATH", "enable", "mark", "reset"]
