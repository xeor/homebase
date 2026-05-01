from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path
from typing import Any

from ...metadata.api import sync_tag_symlinks


def request_tag_sync(app: Any, *, base_dir: Path, reason: str) -> None:
    if app.fast_exit_requested:
        return
    if app.tag_sync_running:
        app.tag_sync_pending = True
        app.tag_sync_pending_reason = reason
        return
    app.tag_sync_running = True

    def worker() -> None:
        err = sync_tag_symlinks(base_dir)
        app.call_from_thread(app._on_tag_sync_done, reason, err)

    threading.Thread(target=worker, daemon=True).start()


def on_tag_sync_done(app: Any, *, reason: str, err: str | None) -> None:
    app.tag_sync_running = False
    if err:
        app._log_error_counted(
            "tag_sync",
            f"tag symlink sync failed ({reason}): {err}",
        )
        app._refresh_side()
    if app.tag_sync_pending:
        pending_reason = app.tag_sync_pending_reason or "pending"
        app.tag_sync_pending = False
        app.tag_sync_pending_reason = ""
        app._request_tag_sync(pending_reason)


def maybe_refresh_cache(app: Any) -> None:
    if app.cache_worker_running:
        return
    now = time.time()
    if now < app.workspace_sig_due_at:
        return
    app.workspace_sig_due_at = now + 10.0
    sig = app._workspace_quick_signature()
    if not app.workspace_sig_last:
        app.workspace_sig_last = sig
        app.workspace_sig_last_ts = now
        return
    if sig != app.workspace_sig_last:
        app.workspace_sig_last = sig
        app.workspace_sig_last_ts = now
        app._worker_debug(
            "workspace signature changed -> cache refresh (hard inconsistency)"
        )
        app._start_cache_refresh("hard inconsistency", force=True)


def workspace_quick_signature(
    *,
    base_dir: Path,
    archive_dir_name: str,
    packed_archive_suffix: str,
) -> str:
    parts: list[str] = []
    try:
        base_names = [
            p.name
            for p in base_dir.iterdir()
            if p.is_dir() and not p.name.startswith(".") and not p.name.startswith("_")
        ]
        base_names.sort()
        h = hashlib.sha1()
        for name in base_names:
            h.update(name.encode("utf-8", errors="ignore"))
            h.update(b"\0")
        parts.append(f"active:{len(base_names)}:{h.hexdigest()[:20]}")
    except (OSError, ValueError):
        parts.append("active:err")

    archive_root = base_dir / archive_dir_name
    try:
        if archive_root.is_dir():
            roots = [
                p.name
                for p in archive_root.iterdir()
                if p.is_dir() or p.name.endswith(packed_archive_suffix)
            ]
            roots.sort()
            h2 = hashlib.sha1()
            for name in roots:
                h2.update(name.encode("utf-8", errors="ignore"))
                h2.update(b"\0")
            parts.append(f"archive:{len(roots)}:{h2.hexdigest()[:20]}")
        else:
            parts.append("archive:0")
    except (OSError, ValueError):
        parts.append("archive:err")

    return "||".join(parts)
