from __future__ import annotations

import os
import sys
from typing import Iterable

from .setup_model import (
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    STATUS_WARN,
    SetupCheck,
    SetupSummary,
)

_COLOR_RESET = "\x1b[0m"
_COLOR_DIM = "\x1b[2m"
_COLOR_GREEN = "\x1b[32m"
_COLOR_YELLOW = "\x1b[33m"
_COLOR_RED = "\x1b[31m"
_COLOR_CYAN = "\x1b[36m"


def color_enabled() -> bool:
    if str(os.environ.get("NO_COLOR", "")).strip():
        return False
    return bool(sys.stdout.isatty())


def format_status_label(status: str) -> str:
    value = str(status).strip().upper()
    if not color_enabled():
        return value
    if value == STATUS_PASS:
        return f"{_COLOR_GREEN}{value}{_COLOR_RESET}"
    if value == STATUS_WARN:
        return f"{_COLOR_YELLOW}{value}{_COLOR_RESET}"
    if value == STATUS_FAIL:
        return f"{_COLOR_RED}{value}{_COLOR_RESET}"
    if value == STATUS_SKIP:
        return f"{_COLOR_CYAN}{value}{_COLOR_RESET}"
    return f"{_COLOR_DIM}{value}{_COLOR_RESET}"


def format_check_row(check: SetupCheck) -> str:
    label = format_status_label(check.status)
    return f"- [{label}] {check.name}: {check.detail}"


def render_checks(checks: Iterable[SetupCheck]) -> None:
    for check in checks:
        print(format_check_row(check))
        for line in check.extra_lines:
            print(line)


def render_summary(summary: SetupSummary) -> None:
    status = STATUS_PASS if not summary.hard_fail else STATUS_FAIL
    label = format_status_label(status)
    msg = "ready" if not summary.hard_fail else "incomplete; resolve FAIL checks"
    print(f"- [{label}] setup: {msg}")
    print(
        f"- summary: PASS={summary.pass_count} "
        f"WARN={summary.warn_count} FAIL={summary.fail_count}"
    )


__all__ = [
    "color_enabled",
    "format_check_row",
    "format_status_label",
    "render_checks",
    "render_summary",
]
