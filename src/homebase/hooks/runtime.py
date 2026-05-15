from __future__ import annotations

import getpass
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import __version__ as homebase_version
from ..core.models import HookInfo, HookRuntime, HookTarget, PreOutcome
from ..core.utils import HOOK_RUN_ERRORS
from ..metadata.api import append_base_log
from .api import HookContext
from .loader import resolve_hook_module


@dataclass(frozen=True)
class HookRunRecord:
    timing: str
    event: str
    name: str
    duration_s: float
    ok: bool
    error: str


def dispatch_pre(
    app: Any,
    *,
    event: str,
    targets: list[HookTarget],
    change: dict[str, object],
    view: str,
) -> PreOutcome:
    return PreOutcome(cancelled=False, reason="", change=dict(change))


def dispatch_post(
    app: Any,
    *,
    event: str,
    targets: list[HookTarget],
    change: dict[str, object],
    view: str,
) -> None:
    hook_specs = getattr(getattr(app, "ctx", None), "hook_specs", {})
    specs = list(hook_specs.get(("post", event), []))
    selected = [
        spec
        for spec in specs
        if bool(spec.enabled) and (not spec.views or view in spec.views)
    ]
    if not selected:
        return None

    worker = threading.Thread(
        target=_run_post_chain,
        args=(app, event, list(targets), dict(change), view, selected),
        daemon=True,
    )
    worker.start()
    return None


def _run_post_chain(
    app: Any,
    event: str,
    targets: list[HookTarget],
    change: dict[str, object],
    view: str,
    specs: list[Any],
) -> None:
    for spec in specs:
        spec_id = f"post/{event}/{spec.name}"
        started_ts = time.time()
        slow_timer: threading.Timer | None = None
        still_running = threading.Event()
        still_running.set()
        hook_error = ""

        def _log_on_main(text: str, level: str = "info") -> None:
            app.call_from_thread(app._log, text, level)

        def _notify_on_main(text: str, level: str = "info") -> None:
            app.call_from_thread(app._set_runtime_status, text, level, 6.0)

        def _add_event_on_main(path: Path, kind: str, payload: dict[str, object]) -> None:
            app.call_from_thread(append_base_log, path, kind, payload)

        def _ask_noop(*_args: object, **_kwargs: object) -> str | None:
            return None

        def _warn_slow() -> None:
            if not still_running.is_set():
                return
            elapsed = max(0.0, time.time() - started_ts)
            _notify_on_main(
                f"hook {spec_id} still running ({elapsed:.1f}s)",
                "warn",
            )
            nonlocal slow_timer
            slow_timer = threading.Timer(max(0.05, float(spec.slow_warn_s)), _warn_slow)
            slow_timer.daemon = True
            slow_timer.start()

        runtime = HookRuntime(
            invoker="tui",
            homebase_version=homebase_version,
            now_iso=datetime.now(timezone.utc).isoformat(),
            now_ts=int(time.time()),
            user=str(getpass.getuser() or ""),
        )
        info = HookInfo(
            name=str(spec.name),
            source=str(spec.source),
            timing="post",
            event=event,
            config=dict(spec.config),
        )
        context = HookContext(
            event=event,
            timing="post",
            view=view,
            base_dir=Path(app.base_dir),
            targets=tuple(targets),
            change=dict(change),
            runtime=runtime,
            hook=info,
            add_event=_add_event_on_main,
            notify=_notify_on_main,
            log=_log_on_main,
            ask=_ask_noop,
        )

        if len(targets) == 1:
            _add_event_on_main(
                targets[0].path,
                "hook_started",
                {"hook": spec.name, "timing": "post", "event": event},
            )
        else:
            _notify_on_main(f"hook {spec_id} running on {len(targets)} target(s)", "info")
        app.call_from_thread(app._busy_start, f"hook: {spec_id}")
        app.hook_running[spec_id] = started_ts

        try:
            module = resolve_hook_module(spec, Path(app.base_dir))
            slow_timer = threading.Timer(max(0.05, float(spec.slow_warn_s)), _warn_slow)
            slow_timer.daemon = True
            slow_timer.start()
            module.run(context)
        except HOOK_RUN_ERRORS as exc:
            hook_error = str(exc)
            tb_tail = "\n".join(traceback.format_exception(type(exc), exc, exc.__traceback__)[-6:])
            app.call_from_thread(app._show_runtime_error, f"hook {spec.name}", exc, tb_tail)
        finally:
            still_running.clear()
            if slow_timer is not None:
                slow_timer.cancel()
            ended = time.time()
            duration = max(0.0, ended - started_ts)
            if len(targets) == 1:
                _add_event_on_main(
                    targets[0].path,
                    "hook_done",
                    {
                        "hook": spec.name,
                        "timing": "post",
                        "event": event,
                        "duration_s": round(duration, 3),
                        "error": hook_error,
                    },
                )
            else:
                status = "ok" if not hook_error else f"error={hook_error}"
                _notify_on_main(
                    f"hook {spec_id} done in {duration:.1f}s ({status})",
                    "warn" if hook_error else "info",
                )
            app.call_from_thread(app._busy_stop)
            app.hook_running.pop(spec_id, None)
            records = app.hook_recent.setdefault(("post", event), [])
            records.append(
                HookRunRecord(
                    timing="post",
                    event=event,
                    name=str(spec.name),
                    duration_s=duration,
                    ok=not bool(hook_error),
                    error=hook_error,
                )
            )
            if len(records) > 20:
                del records[:-20]
