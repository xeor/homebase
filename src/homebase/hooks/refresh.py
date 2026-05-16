from __future__ import annotations

import getpass
import io
import os
import threading
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .. import __version__ as homebase_version
from ..core.models import HookInfo, HookRuntime, HookSpec, HookTarget
from ..core.utils import HOOK_RUN_ERRORS
from ..metadata.api import append_base_log
from .api import HookContext
from .loader import resolve_hook_module
from .runtime import _tui_notify, _tui_status_update


def _build_refresh_change(event: str, target: HookTarget) -> dict[str, object]:
    if event == "tag_change":
        return {
            "per_target": {
                target.path: {"current_tags": list(target.tags)},
            }
        }
    return {}


def _module_supports_refresh(module: object) -> bool:
    return callable(getattr(module, "refresh", None))


def _spec_filter(
    spec: HookSpec,
    *,
    view: str,
    event_filter: tuple[str, ...] | None,
    hook_filter: tuple[str, ...] | None,
    require_refresh_enabled: bool,
) -> bool:
    if not spec.enabled:
        return False
    if event_filter and spec.event not in event_filter:
        return False
    if hook_filter and spec.name not in hook_filter:
        return False
    if spec.views and view not in spec.views:
        return False
    if require_refresh_enabled and not spec.refresh_enabled:
        return False
    return True


def _select_specs(
    hook_specs: dict[tuple[str, str], list[HookSpec]],
    *,
    view: str,
    event_filter: tuple[str, ...] | None,
    hook_filter: tuple[str, ...] | None,
    require_refresh_enabled: bool,
) -> list[HookSpec]:
    selected: list[HookSpec] = []
    for (timing, _event), specs in hook_specs.items():
        if timing != "post":
            continue
        for spec in specs:
            if _spec_filter(
                spec,
                view=view,
                event_filter=event_filter,
                hook_filter=hook_filter,
                require_refresh_enabled=require_refresh_enabled,
            ):
                selected.append(spec)
    return selected


def dispatch_refresh_tui(
    app: Any,
    *,
    targets: list[HookTarget],
    view: str,
    event_filter: tuple[str, ...] | None = None,
    hook_filter: tuple[str, ...] | None = None,
    source: str = "manual",
    require_refresh_enabled: bool = False,
) -> None:
    hook_specs = getattr(getattr(app, "ctx", None), "hook_specs", {})
    specs = _select_specs(
        hook_specs,
        view=view,
        event_filter=event_filter,
        hook_filter=hook_filter,
        require_refresh_enabled=require_refresh_enabled,
    )
    if not specs or not targets:
        return
    worker = threading.Thread(
        target=_run_refresh_chain_tui,
        args=(app, list(targets), specs, view, source),
        daemon=True,
    )
    worker.start()


def dispatch_refresh_cli(
    *,
    base_dir: Path,
    hook_specs: dict[tuple[str, str], list[HookSpec]],
    targets: list[HookTarget],
    view: str,
    event_filter: tuple[str, ...] | None = None,
    hook_filter: tuple[str, ...] | None = None,
    source: str = "cli",
    require_refresh_enabled: bool = False,
) -> None:
    specs = _select_specs(
        hook_specs,
        view=view,
        event_filter=event_filter,
        hook_filter=hook_filter,
        require_refresh_enabled=require_refresh_enabled,
    )
    if not specs or not targets:
        return
    for spec in specs:
        module = resolve_hook_module(spec, base_dir)
        if not _module_supports_refresh(module):
            continue
        for target in targets:
            _run_refresh_one_cli(
                base_dir=base_dir,
                spec=spec,
                module=module,
                target=target,
                view=view,
                source=source,
            )


def _run_refresh_chain_tui(
    app: Any,
    targets: list[HookTarget],
    specs: list[HookSpec],
    view: str,
    source: str,
) -> None:
    for spec in specs:
        try:
            module = resolve_hook_module(spec, Path(app.base_dir))
        except HOOK_RUN_ERRORS as exc:
            app.call_from_thread(app._log, f"refresh: cannot load {spec.name}: {exc}", "warn")
            continue
        if not _module_supports_refresh(module):
            continue
        for target in targets:
            _run_refresh_one_tui(
                app=app,
                spec=spec,
                module=module,
                target=target,
                view=view,
                source=source,
            )


def _build_context(
    *,
    spec: HookSpec,
    target: HookTarget,
    base_dir: Path,
    view: str,
    invoker: str,
    add_event: Callable[[Path, str, dict[str, object]], None],
    notify: Callable[[str, str], None],
    status_update: Callable[[str, str], None],
    log: Callable[[str, str], None],
) -> HookContext:
    runtime = HookRuntime(
        invoker=invoker,
        homebase_version=homebase_version,
        now_iso=datetime.now(timezone.utc).isoformat(),
        now_ts=int(time.time()),
        user=str(getpass.getuser() or ""),
    )
    info = HookInfo(
        name=str(spec.name),
        source=str(spec.source),
        timing="post",
        event=spec.event,
        config=dict(spec.config),
    )
    return HookContext(
        event=spec.event,
        timing="post",
        view=view,
        base_dir=base_dir,
        targets=(target,),
        change=_build_refresh_change(spec.event, target),
        runtime=runtime,
        hook=info,
        add_event=add_event,
        notify=notify,
        status_update=status_update,
        log=log,
        ask=lambda *_a, **_k: None,
        mode="refresh",
    )


def _run_refresh_one_tui(
    *,
    app: Any,
    spec: HookSpec,
    module: object,
    target: HookTarget,
    view: str,
    source: str,
) -> None:
    spec_id = f"refresh/{spec.event}/{spec.name}"
    started_ts = time.time()
    hook_error = ""

    def _log_on_main(text: str, level: str = "info") -> None:
        app.call_from_thread(app._log, text, level)

    def _notify_on_main(text: str, level: str = "info") -> None:
        _tui_notify(app, text, level)

    def _status_update_on_main(text: str, level: str = "info") -> None:
        _tui_status_update(app, text, level)

    def _add_event_on_main(path: Path, kind: str, payload: dict[str, object]) -> None:
        app.call_from_thread(append_base_log, path, kind, payload)

    context = _build_context(
        spec=spec,
        target=target,
        base_dir=Path(app.base_dir),
        view=view,
        invoker="tui",
        add_event=_add_event_on_main,
        notify=_notify_on_main,
        status_update=_status_update_on_main,
        log=_log_on_main,
    )

    _add_event_on_main(
        target.path,
        "hook_refresh_started",
        {"hook": spec.name, "event": spec.event, "source": source},
    )
    app.call_from_thread(app._busy_start, f"hook: {spec_id}")
    app.hook_running[spec_id] = started_ts

    try:
        captured_out = io.StringIO()
        captured_err = io.StringIO()
        with redirect_stdout(captured_out), redirect_stderr(captured_err):
            module.refresh(context)
        out_text = captured_out.getvalue().strip()
        err_text = captured_err.getvalue().strip()
        if out_text:
            _log_on_main(f"hook {spec_id} stdout: {out_text}", "info")
        if err_text:
            _log_on_main(f"hook {spec_id} stderr: {err_text}", "warn")
    except HOOK_RUN_ERRORS as exc:
        hook_error = str(exc)
        tb_tail = "\n".join(traceback.format_exception(type(exc), exc, exc.__traceback__)[-6:])
        app.call_from_thread(app._show_runtime_error, f"hook {spec.name} (refresh)", exc, tb_tail)
    finally:
        duration = max(0.0, time.time() - started_ts)
        _add_event_on_main(
            target.path,
            "hook_refresh_done",
            {
                "hook": spec.name,
                "event": spec.event,
                "duration_s": round(duration, 3),
                "error": hook_error,
                "source": source,
            },
        )
        app.call_from_thread(app._busy_stop)
        app.hook_running.pop(spec_id, None)


def _run_refresh_one_cli(
    *,
    base_dir: Path,
    spec: HookSpec,
    module: object,
    target: HookTarget,
    view: str,
    source: str,
) -> None:
    spec_id = f"refresh/{spec.event}/{spec.name}"
    started = time.time()
    hook_error = ""

    def _add_event(path: Path, kind: str, payload: dict[str, object]) -> None:
        append_base_log(path, kind, payload)

    def _notify(text: str, level: str = "info") -> None:
        print(f"[hook] {level}: {text}", file=os.sys.stderr)

    def _status_update(text: str, level: str = "info") -> None:
        print(f"[hook] status {level}: {text}", file=os.sys.stderr)

    def _log(text: str, level: str = "info") -> None:
        print(f"[hook] {level}: {text}")

    context = _build_context(
        spec=spec,
        target=target,
        base_dir=base_dir,
        view=view,
        invoker="cli",
        add_event=_add_event,
        notify=_notify,
        status_update=_status_update,
        log=_log,
    )

    print(f"[hook] {spec_id} on {target.path.name} ... running", file=os.sys.stderr)
    _add_event(
        target.path,
        "hook_refresh_started",
        {"hook": spec.name, "event": spec.event, "source": source},
    )

    try:
        captured_out = io.StringIO()
        captured_err = io.StringIO()
        with redirect_stdout(captured_out), redirect_stderr(captured_err):
            module.refresh(context)
        out_text = captured_out.getvalue().strip()
        err_text = captured_err.getvalue().strip()
        if out_text:
            _log(f"hook {spec.name} stdout: {out_text}", "info")
        if err_text:
            _notify(f"hook {spec.name} stderr: {err_text}", "warn")
    except HOOK_RUN_ERRORS as exc:
        hook_error = str(exc)
        print(f"[hook] {spec_id} failed: {hook_error}", file=os.sys.stderr)
    finally:
        duration = max(0.0, time.time() - started)
        _add_event(
            target.path,
            "hook_refresh_done",
            {
                "hook": spec.name,
                "event": spec.event,
                "duration_s": round(duration, 3),
                "error": hook_error,
                "source": source,
            },
        )
        if not hook_error:
            print(f"[hook] {spec_id} on {target.path.name} done in {duration:.1f}s", file=os.sys.stderr)
