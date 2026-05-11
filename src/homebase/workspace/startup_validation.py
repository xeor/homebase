from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..core.constants import ARCHIVE_DIR_NAME


@dataclass(frozen=True)
class StartupValidationIssue:
    key: str
    message: str
    path: Path | None = None


_PACKED_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+)\.tgz$")


def _is_valid_new_packed_archive_name(name: str) -> bool:
    match = _PACKED_NAME_RE.match(name)
    if match is None:
        return False
    return bool(match.group(2).strip())


def _check_archive_packed_names(base_dir: Path) -> list[StartupValidationIssue]:
    issues: list[StartupValidationIssue] = []
    archive_root = base_dir / ARCHIVE_DIR_NAME
    if not archive_root.is_dir():
        return issues
    candidates: list[Path] = []
    for entry in archive_root.iterdir():
        if entry.is_file() and entry.suffix == ".tgz":
            candidates.append(entry)
    for path in candidates:
        if _is_valid_new_packed_archive_name(path.name):
            continue
        issues.append(
            StartupValidationIssue(
                key="archive.packed_name",
                message=(
                    "invalid packed archive name under _archive; expected "
                    "YYYY-MM-DD_<name>.tgz"
                ),
                path=path,
            )
        )
    return issues


def run_startup_validations(base_dir: Path) -> list[StartupValidationIssue]:
    checks: tuple[Callable[[Path], list[StartupValidationIssue]], ...] = (
        _check_archive_packed_names,
    )
    issues: list[StartupValidationIssue] = []
    for check in checks:
        issues.extend(check(base_dir))
    return issues
