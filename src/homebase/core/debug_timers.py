from __future__ import annotations

import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .constants import DEBUG_TIMERS_LOG_FILE_NAME, HOMEBASE_DIR_NAME

enabled = False


def set_enabled(value: bool) -> None:
    global enabled
    enabled = value


def debug_timers_log_path(base_dir: Path) -> Path:
    return base_dir / HOMEBASE_DIR_NAME / DEBUG_TIMERS_LOG_FILE_NAME


def record_timing(base_dir: Path, label: str, seconds: float, **extra: object) -> None:
    if not enabled:
        return
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "label": label,
        "seconds": round(seconds, 4),
        **extra,
    }
    path = debug_timers_log_path(base_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        return


@contextmanager
def timed_step(base_dir: Path, label: str, **extra: object) -> Iterator[dict[str, object]]:
    """Time a block and append it to ``.homebase/debug-timers.jsonl``.

    No-op (no timer, no I/O) unless module-level ``enabled`` is set via
    ``set_enabled()`` (wired to ``b --debug-timers`` / HOMEBASE_DEBUG_TIMERS
    at CLI startup). Use the yielded dict to attach fields known only
    inside the block (e.g. ``info["ok"] = True``).
    """
    if not enabled:
        yield {}
        return
    start = time.monotonic()
    info: dict[str, object] = {}
    try:
        yield info
    finally:
        merged = dict(extra)
        merged.update(info)
        record_timing(base_dir, label, time.monotonic() - start, **merged)
