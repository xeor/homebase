from __future__ import annotations

from datetime import datetime
from typing import Any

from textual.widgets import Static

from ...cache import concurrency as cache_concurrency
from ...core.utils import WIDGET_API_ERRORS

BANNER_ID = "#cache_concurrency_banner"


def check_cache_concurrency(app: Any) -> None:
    snap = cache_concurrency.snapshot()
    prev = int(getattr(app, "cache_concurrency_drift_seen", 0) or 0)
    if snap.drift_count > prev:
        app.cache_concurrency_drift_seen = snap.drift_count
        app.cache_concurrency_last_event = snap.last_event
        app.cache_concurrency_dismissed = False
        if snap.last_event is not None:
            ts = datetime.fromtimestamp(snap.last_event.ts).astimezone().strftime(
                "%H:%M:%S"
            )
            app._log_error_counted(
                "cache_concurrency",
                f"cache schema drift [{snap.last_event.kind}] @ {ts}: "
                f"{snap.last_event.detail}",
                level="error",
            )
    paint_banner(app)


def paint_banner(app: Any) -> None:
    try:
        banner = app.query_one(BANNER_ID, Static)
    except WIDGET_API_ERRORS:
        return
    drift_count = int(getattr(app, "cache_concurrency_drift_seen", 0) or 0)
    dismissed = bool(getattr(app, "cache_concurrency_dismissed", False))
    last_event = getattr(app, "cache_concurrency_last_event", None)
    if drift_count <= 0 or dismissed or last_event is None:
        banner.update("")
        banner.remove_class("visible")
        return
    kind = str(getattr(last_event, "kind", "unknown"))
    observed = int(getattr(last_event, "observed_version", 0) or 0)
    expected = int(getattr(last_event, "expected_version", 0) or 0)
    banner.update(
        f"⚠ cache schema drift detected ({drift_count}x): "
        f"on-disk v{observed} vs expected v{expected} [{kind}] — "
        f"another b process is fighting over the cache; "
        f"see Info → Cache tab  ·  ctrl+y to dismiss"
    )
    banner.add_class("visible")


def dismiss(app: Any) -> None:
    app.cache_concurrency_dismissed = True
    paint_banner(app)


__all__ = [
    "BANNER_ID",
    "check_cache_concurrency",
    "dismiss",
    "paint_banner",
]
