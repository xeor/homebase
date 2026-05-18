from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..core.constants import ARCHIVE_DIR_NAME, ARCHIVE_YEAR_DIR_RE


@dataclass(frozen=True)
class StartupValidationIssue:
    key: str
    message: str
    path: Path | None = None


_VALID_DATE_PREFIX_RE = re.compile(
    r"^(\d{4})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])_(.+)$"
)


def _is_valid_archive_entry_name(stem: str) -> bool:
    match = _VALID_DATE_PREFIX_RE.match(stem)
    if match is None:
        return False
    return bool(match.group(4).strip())


def _check_archive_layout(base_dir: Path) -> list[StartupValidationIssue]:
    issues: list[StartupValidationIssue] = []
    archive_root = base_dir / ARCHIVE_DIR_NAME
    if not archive_root.is_dir():
        return issues

    for entry in archive_root.iterdir():
        if not ARCHIVE_YEAR_DIR_RE.match(entry.name):
            issues.append(
                StartupValidationIssue(
                    key="archive.layout",
                    message=(
                        "unexpected entry directly under _archive; expected only "
                        "YYYY/ subdirectories"
                    ),
                    path=entry,
                )
            )
            continue
        if not entry.is_dir():
            issues.append(
                StartupValidationIssue(
                    key="archive.layout",
                    message="year entry under _archive must be a directory",
                    path=entry,
                )
            )
            continue
        year = entry.name
        for child in entry.iterdir():
            name = child.name
            stem = name[:-4] if name.endswith(".tgz") else name
            if not _is_valid_archive_entry_name(stem):
                issues.append(
                    StartupValidationIssue(
                        key="archive.entry_name",
                        message=(
                            "invalid archive entry name; expected "
                            "YYYY-MM-DD_<name> with valid date (no 00 segments)"
                        ),
                        path=child,
                    )
                )
                continue
            if not stem.startswith(f"{year}-"):
                issues.append(
                    StartupValidationIssue(
                        key="archive.year_mismatch",
                        message=(
                            f"entry year prefix does not match parent year directory ({year})"
                        ),
                        path=child,
                    )
                )
    return issues


def run_startup_validations(base_dir: Path) -> list[StartupValidationIssue]:
    checks: tuple[Callable[[Path], list[StartupValidationIssue]], ...] = (
        _check_archive_layout,
    )
    issues: list[StartupValidationIssue] = []
    for check in checks:
        issues.extend(check(base_dir))
    return issues
