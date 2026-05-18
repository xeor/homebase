"""Heuristic date detection for an existing directory.

Used by ``b fix`` to figure out the canonical archive date for an
entry whose name doesn't already carry one, and by ``b archive
--autodate`` to pick a date without prompting.

Priorities (first hit wins):

  P1. ``.git/`` HEAD commit date — run when the folder contains a
      ``.git/`` directory. A fast ``git log -1 --format=%ct``.
  P2. Folder name — canonical ``YYYY-MM-DD`` prefix, legacy ISO suffix
      (``foo.20240101T1200``), embedded full date anywhere, a loose
      retry mapping ``00`` segments to ``01``, and finally a year-only
      fallback (e.g. ``something 2022`` → ``2022-01-01``). When the
      name contains multiple years, the largest one wins.
  P3. Newest mtime among regular files. Top level first (skipping
      directories, dotfiles, and ``_``-prefixed entries); if the top
      level has no eligible files, descend exactly one level and try
      again. The folder's own mtime is never used.
"""

from __future__ import annotations

import re
import shutil
import subprocess
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
# 4-digit year not adjacent to other digits (so it doesn't claim a
# slice out of a longer date-shaped run).
_YEAR_ONLY_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")


@dataclass(frozen=True)
class DateDetection:
    ts: int
    source: str   # human description shown in fix output
    kind: str     # short tag: git | name-prefix | name-prefix-loose |
                  # name-parse | name-suffix | name-embedded |
                  # name-embedded-loose | name-year | mtime


def _safe_make_ts(year: int, month: int, day: int, tz: tzinfo) -> int | None:
    try:
        dt = datetime(year, month, day, tzinfo=tz)
    except ValueError:
        return None
    return int(dt.timestamp())


def _normalize_zero(mo: int, d: int) -> tuple[int, int]:
    return (mo if mo > 0 else 1, d if d > 0 else 1)


def _try_git_head(folder: Path) -> DateDetection | None:
    """If ``.git/`` exists, ask git for the HEAD commit's committer
    timestamp. Bounded with a short timeout so a slow/broken repo
    can't hang the fix sweep."""
    git_marker = folder / ".git"
    if not git_marker.exists():
        return None
    if shutil.which("git") is None:
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", str(folder), "log", "-1", "--format=%ct"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    raw = (proc.stdout or "").strip()
    if not raw:
        return None
    try:
        ts = int(raw)
    except ValueError:
        return None
    if ts <= 0:
        return None
    iso_day = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    return DateDetection(ts=ts, source=f"git HEAD ({iso_day})", kind="git")


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


def _try_year_only(name: str, tz: tzinfo) -> DateDetection | None:
    """Pick a plausible year embedded in the name and map it to
    ``YYYY-01-01``. If multiple candidates exist, the largest (most
    recent) wins — that's usually 'the year the work stopped'."""
    candidates: list[int] = []
    for m in _YEAR_ONLY_RE.finditer(name):
        y = int(m.group(1))
        if 1900 <= y <= 2100:
            candidates.append(y)
    if not candidates:
        return None
    y = max(candidates)
    ts = _safe_make_ts(y, 1, 1, tz)
    if ts is None:
        return None
    return DateDetection(ts=ts, source=f"name year {y}", kind="name-year")


def _newest_regular_file_mtime(folder: Path) -> float | None:
    """Newest mtime among direct children of ``folder`` that are:
      - regular files (no directories)
      - name does not start with ``.`` or ``_``

    The folder's own mtime is never consulted.
    """
    newest: float | None = None
    try:
        entries = list(folder.iterdir())
    except OSError:
        return None
    for entry in entries:
        if entry.name.startswith(".") or entry.name.startswith("_"):
            continue
        try:
            if not entry.is_file():
                continue
            mt = entry.stat().st_mtime
        except OSError:
            continue
        if newest is None or mt > newest:
            newest = mt
    return newest


def _try_mtime(folder: Path) -> DateDetection | None:
    """Top-level pass first; if nothing eligible at the top, descend
    one level into each non-hidden, non-``_`` subdir and try there.
    Anything deeper is intentionally ignored."""
    if not folder.is_dir():
        return None
    top = _newest_regular_file_mtime(folder)
    if top is not None:
        return DateDetection(
            ts=int(top),
            source="newest file mtime",
            kind="mtime",
        )
    try:
        subdirs = [
            entry for entry in folder.iterdir()
            if entry.is_dir()
            and not entry.name.startswith(".")
            and not entry.name.startswith("_")
        ]
    except OSError:
        return None
    newest: float | None = None
    for subdir in sorted(subdirs):
        sub_newest = _newest_regular_file_mtime(subdir)
        if sub_newest is None:
            continue
        if newest is None or sub_newest > newest:
            newest = sub_newest
    if newest is None:
        return None
    return DateDetection(
        ts=int(newest),
        source="newest file mtime (one level deep)",
        kind="mtime",
    )


def detect_folder_date(
    folder: Path,
    *,
    parse_timestamp: Callable[[str], int],
    archive_tz: tzinfo,
    mtime_scan_limit: int = 2000,  # retained for API compatibility
) -> DateDetection | None:
    _ = mtime_scan_limit  # no longer applicable; left for callers.

    # P1 — git HEAD wins outright when available.
    git_hit = _try_git_head(folder)
    if git_hit is not None:
        return git_hit

    # P2 — name parsing.
    name = folder.name
    if name.endswith(".tgz"):
        name = name[:-4]
    for fn in (
        lambda: _try_prefix(name, archive_tz),
        lambda: _try_parse(name, parse_timestamp),
        lambda: _try_embedded(name, archive_tz),
        lambda: _try_prefix(name, archive_tz, normalize_zeros=True),
        lambda: _try_embedded(name, archive_tz, normalize_zeros=True),
        lambda: _try_year_only(name, archive_tz),
    ):
        found = fn()
        if found is not None:
            return found

    # P3 — file mtime, regular files only, top-level then one deep.
    return _try_mtime(folder)


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
