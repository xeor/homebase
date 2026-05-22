from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class CacheConcurrencyEvent:
    ts: int
    expected_version: int
    observed_version: int
    kind: str
    detail: str


class _State:
    __slots__ = ("lock", "last_set_version", "events", "drift_count")

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.last_set_version: int = 0
        self.events: list[CacheConcurrencyEvent] = []
        self.drift_count: int = 0


_STATE = _State()
_EVENT_LIMIT = 32


def record_set(expected_version: int) -> None:
    with _STATE.lock:
        _STATE.last_set_version = int(expected_version)


def record_observation(
    *, observed_version: int, expected_version: int
) -> CacheConcurrencyEvent | None:
    if observed_version == expected_version:
        return None
    if observed_version <= 0:
        return None
    with _STATE.lock:
        last_set = int(_STATE.last_set_version)
    # Only flag drift once we have previously written the schema and
    # something has changed it underneath us. A bare migration on first
    # startup (observed=5, expected=6, last_set=0) is legitimate, not
    # drift.
    if last_set != expected_version:
        return None
    if observed_version < expected_version:
        kind = "older_present"
        detail = (
            f"on-disk schema={observed_version} < expected={expected_version}: "
            "another process is running an older b version and overwriting "
            "the cache schema; restart the older instance to stop the thrash"
        )
    else:
        kind = "newer_present"
        detail = (
            f"on-disk schema={observed_version} > expected={expected_version}: "
            "another process is running a newer b version; restart this "
            "instance once the rollout settles"
        )
    ev = CacheConcurrencyEvent(
        ts=int(time.time()),
        expected_version=int(expected_version),
        observed_version=int(observed_version),
        kind=kind,
        detail=detail,
    )
    with _STATE.lock:
        _STATE.events.append(ev)
        if len(_STATE.events) > _EVENT_LIMIT:
            _STATE.events = _STATE.events[-_EVENT_LIMIT:]
        _STATE.drift_count += 1
    return ev


@dataclass(frozen=True)
class CacheConcurrencySnapshot:
    drift_count: int
    last_set_version: int
    last_event: CacheConcurrencyEvent | None
    events: tuple[CacheConcurrencyEvent, ...]


def snapshot() -> CacheConcurrencySnapshot:
    with _STATE.lock:
        events = tuple(_STATE.events)
        last = events[-1] if events else None
        return CacheConcurrencySnapshot(
            drift_count=int(_STATE.drift_count),
            last_set_version=int(_STATE.last_set_version),
            last_event=last,
            events=events,
        )


def reset() -> None:
    with _STATE.lock:
        _STATE.last_set_version = 0
        _STATE.events.clear()
        _STATE.drift_count = 0
