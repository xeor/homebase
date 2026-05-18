"""Heuristic date detection for an existing directory.

Used by ``b fix`` to figure out the canonical archive date for an
entry whose name doesn't already carry one, and by ``b archive
--autodate`` to pick a date without prompting.

Strategies (first hit wins):
  1. Canonical archive prefix ``YYYY-MM-DD<sep>*`` at the start of the
     name, where ``<sep>`` is ``_`` / space / ``-`` / ``.`` / end.
  2. ``parse_archive_timestamp`` applied to the full name and to the
     suffix after the last ``.`` (catches legacy ``foo.20240101T1200``
     style names).
  3. Any embedded ``YYYY-MM-DD`` (or ``YYYYMMDD``) substring in the
     name.
  4. Newest mtime among non-hidden, non-``.git`` files inside the
     folder, bounded by ``mtime_scan_limit`` to keep huge trees fast.

If the strict pass fails because a date prefix has ``00`` segments
(e.g. ``2003-00-00_x``), a loose retry maps month/day ``00`` to
``01`` and is reported with a ``-loose`` kind suffix.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Callable

# Name shaped like ``YYYY-MM-DD`` then either end-of-string or a
# separator followed by the stem. Separators accepted: ``_``, any
# whitespace, ``-``, ``.``.
_DATE_PREFIX_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?:[_\s\-.]+(.*))?$"
)
_EMBEDDED_DATE_RE = re.compile(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})")
_STRICT_YMD_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class DateDetection:
    ts: int
    source: str   # human description: "name prefix 2024-03-15", "mtime", ...
    kind: str     # short tag: name-prefix | name-prefix-loose |
                  # name-parse | name-suffix | name-embedded |
                  # name-embedded-loose | mtime


def _safe_make_ts(year: int, month: int, day: int, tz: tzinfo) -> int | None:
    try:
        dt = datetime(year, month, day, tzinfo=tz)
    except ValueError:
        return None
    return int(dt.timestamp())


def _normalize_zero(mo: int, d: int) -> tuple[int, int]:
    return (mo if mo > 0 else 1, d if d > 0 else 1)


def _try_prefix(
    name: str, tz: tzinfo, *, normalize_zeros: bool = False,
) -> DateDetection | None:
    m = _DATE_PREFIX_RE.match(name)
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups()[:3])
    if normalize_zeros:
        mo, d = _normalize_zero(mo, d)
    ts = _safe_make_ts(y, mo, d, tz)
    if ts is None:
        return None
    kind = "name-prefix-loose" if normalize_zeros else "name-prefix"
    label = f"{y:04d}-{mo:02d}-{d:02d}"
    return DateDetection(ts=ts, source=f"name prefix {label}", kind=kind)


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


def _try_embedded(
    name: str, tz: tzinfo, *, normalize_zeros: bool = False,
) -> DateDetection | None:
    for m in _EMBEDDED_DATE_RE.finditer(name):
        y, mo, d = (int(x) for x in m.groups())
        if normalize_zeros:
            mo, d = _normalize_zero(mo, d)
        ts = _safe_make_ts(y, mo, d, tz)
        if ts is None:
            continue
        kind = "name-embedded-loose" if normalize_zeros else "name-embedded"
        label = f"{y:04d}-{mo:02d}-{d:02d}"
        return DateDetection(ts=ts, source=f"name embedded {label}", kind=kind)
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
    if name.endswith(".tgz"):
        name = name[:-4]
    # Strict pass first.
    for fn in (
        lambda: _try_prefix(name, archive_tz),
        lambda: _try_parse(name, parse_timestamp),
        lambda: _try_embedded(name, archive_tz),
    ):
        found = fn()
        if found is not None:
            return found
    # Loose retry — accept ``00`` segments by mapping to ``01``. Matches
    # the old ``b archive reorganize`` semantics for legacy names like
    # ``2003-00-00_invisible``.
    for fn in (
        lambda: _try_prefix(name, archive_tz, normalize_zeros=True),
        lambda: _try_embedded(name, archive_tz, normalize_zeros=True),
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
    """Strip a leading ``YYYY-MM-DD`` plus its separator (one of
    ``_`` / space / ``-`` / ``.``) from ``name``. Returns the bare
    stem, or the original name if no date prefix is present, or an
    empty string if the name *is* just a date with no stem."""
    m = _DATE_PREFIX_RE.match(name)
    if not m:
        return name
    return m.group(4) or ""
