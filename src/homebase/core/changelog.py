from __future__ import annotations

import re
from dataclasses import dataclass

from .version import REPO_ROOT

CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"

_ENTRY_HEADER_RE = re.compile(
    r"^## (?P<version>\d+\.\d+\.\d+(?:[+\-][\w.]+)?) "
    r"\((?P<commit>[0-9a-f]+|unknown)\) - (?P<date>\d{4}-\d{2}-\d{2})$"
)
_SEMVER_PREFIX_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


@dataclass(frozen=True)
class ChangelogEntry:
    version: str
    commit: str
    date: str
    body: str


def parse_changelog(text: str) -> list[ChangelogEntry]:
    entries: list[ChangelogEntry] = []
    current: dict[str, str] | None = None
    body_lines: list[str] = []

    def flush() -> None:
        if current is not None:
            entries.append(
                ChangelogEntry(
                    version=current["version"],
                    commit=current["commit"],
                    date=current["date"],
                    body="\n".join(body_lines).strip("\n"),
                )
            )

    for line in text.splitlines():
        match = _ENTRY_HEADER_RE.match(line.strip())
        if match:
            flush()
            current = match.groupdict()
            body_lines = []
            continue
        if current is not None:
            body_lines.append(line)
    flush()
    return entries


def load_changelog_entries() -> list[ChangelogEntry]:
    if not CHANGELOG_PATH.is_file():
        return []
    try:
        text = CHANGELOG_PATH.read_text()
    except OSError:
        return []
    return parse_changelog(text)


def semver_tuple(version: str) -> tuple[int, int, int]:
    match = _SEMVER_PREFIX_RE.match(version)
    if not match:
        return (0, 0, 0)
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def entries_since(
    entries: list[ChangelogEntry], since_version: str | None
) -> list[ChangelogEntry]:
    """Entries strictly newer than ``since_version``, newest first.

    ``entries`` must already be newest-first, matching how they're
    written to CHANGELOG.md. When ``since_version`` is ``None`` (never
    tracked before), only the latest entry is returned so a first-time
    upgrade doesn't dump the whole history."""
    if not entries:
        return []
    if since_version is None:
        return entries[:1]
    since = semver_tuple(since_version)
    out: list[ChangelogEntry] = []
    for entry in entries:
        if semver_tuple(entry.version) <= since:
            break
        out.append(entry)
    return out
