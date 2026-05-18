"""Heuristic date detection for an existing directory.

Used by ``b fix`` to figure out the canonical archive date for an
entry whose name doesn't already carry one, and by ``b archive
--autodate`` to pick a date without prompting.

Strategies (first hit wins):
  1. Canonical archive prefix ``YYYY-MM-DD_*`` in the folder name.
  2. ``parse_archive_timestamp`` applied to the full name and to the
     suffix after the last ``.`` (catches legacy ``foo.20240101T1200``
     style names).
  3. Any embedded ``YYYY-MM-DD`` (or ``YYYYMMDD``) substring in the
     name.
  4. Newest mtime among non-hidden, non-``.git`` files inside the
     folder, bounded by ``mtime_scan_limit`` to keep huge trees fast.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Callable

_CANONICAL_PREFIX_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:_|$|\.)")
_EMBEDDED_DATE_RE = re.compile(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})")
_STRICT_YMD_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class DateDetection:
    ts: int
    source: str   # human description: "name prefix 2024-03-15", "mtime", ...
    kind: str     # short tag: name-prefix | name-parse | name-suffix |
                  # name-embedded | mtime


def _safe_make_ts(year: int, month: int, day: int, tz: tzinfo) -> int | None:
    try:
        dt = datetime(year, month, day, tzinfo=tz)
    except ValueError:
        return None
    return int(dt.timestamp())


def _try_prefix(name: str, tz: tzinfo) -> DateDetection | None:
    m = _CANONICAL_PREFIX_RE.match(name)
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    ts = _safe_make_ts(y, mo, d, tz)
    if ts is None:
        return None
    return DateDetection(
        ts=ts,
        source=f"name prefix {m.group(1)}-{m.group(2)}-{m.group(3)}",
        kind="name-prefix",
    )


def _try_parse(name: str, parse_timestamp: Callable[[str], int]) -> DateDetection | None:
    ts = parse_timestamp(name)
    if ts > 0:
        return DateDetection(ts=ts, source=f"name parsed ({name})", kind="name-parse")
    if "." in name:
        suffix = name.rsplit(".", 1)[-1]
        ts = parse_timestamp(suffix)
        if ts > 0:
            return DateDetection(
                ts=ts,
                source=f"name suffix .{suffix}",
                kind="name-suffix",
            )
    return None


def _try_embedded(name: str, tz: tzinfo) -> DateDetection | None:
    for m in _EMBEDDED_DATE_RE.finditer(name):
        y, mo, d = (int(x) for x in m.groups())
        ts = _safe_make_ts(y, mo, d, tz)
        if ts is None:
            continue
        return DateDetection(
            ts=ts,
            source=f"name embedded {m.group(1)}-{m.group(2)}-{m.group(3)}",
            kind="name-embedded",
        )
    return None


def _walk_mtimes(folder: Path, limit: int) -> int | None:
    """Return the newest mtime among non-hidden, non-.git regular
    files inside folder. Stops after scanning ``limit`` files."""
    newest: float | None = None
    seen = 0
    try:
        iterator = folder.rglob("*")
    except OSError:
        return None
    for entry in iterator:
        if seen >= limit:
            break
        try:
            rel_parts = entry.relative_to(folder).parts
        except ValueError:
            continue
        if any(part.startswith(".") for part in rel_parts):
            continue
        try:
            if not entry.is_file():
                continue
            mt = entry.stat().st_mtime
        except OSError:
            continue
        seen += 1
        if newest is None or mt > newest:
            newest = mt
    if newest is None:
        return None
    return int(newest)


def detect_folder_date(
    folder: Path,
    *,
    parse_timestamp: Callable[[str], int],
    archive_tz: tzinfo,
    mtime_scan_limit: int = 2000,
) -> DateDetection | None:
    name = folder.name
    for fn in (
        lambda: _try_prefix(name, archive_tz),
        lambda: _try_parse(name, parse_timestamp),
        lambda: _try_embedded(name, archive_tz),
    ):
        found = fn()
        if found is not None:
            return found
    if folder.is_dir():
        ts = _walk_mtimes(folder, mtime_scan_limit)
        if ts is not None:
            return DateDetection(ts=ts, source="newest mtime in tree", kind="mtime")
    return None


def parse_user_date(raw: str, archive_tz: tzinfo) -> int | None:
    """Strict YYYY-MM-DD parse. Returns epoch seconds or None."""
    s = raw.strip()
    if not _STRICT_YMD_RE.match(s):
        return None
    try:
        dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=archive_tz)
    except ValueError:
        return None
    return int(dt.timestamp())


def strip_date_prefix(name: str) -> str:
    """Remove a leading ``YYYY-MM-DD_`` if present, otherwise return
    the name unchanged."""
    m = re.match(r"^\d{4}-\d{2}-\d{2}_(.*)$", name)
    if not m:
        return name
    return m.group(1)
