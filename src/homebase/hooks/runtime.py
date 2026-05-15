from __future__ import annotations

import getpass
import io
import os
import threading
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

from .. import __version__ as homebase_version
from ..core import prompting
from ..core.models import HookInfo, HookRuntime, HookTarget, PreOutcome, PreResult
from ..core.utils import HOOK_RUN_ERRORS
from ..metadata.api import append_base_log
from .api import HookContext
from .loader import resolve_hook_module

_PRE_MUTATION_ALLOWLIST: dict[str, frozenset[str]] = {
    "rename": frozenset({"new_path", "new_name"}),
    "tag_change": frozenset({"plan"}),
    "new_project": frozenset({"initial_tags", "template", "post_commands", "after_create"}),
    "delete": frozenset(),
}

_NOTIFY_SEVERITY = {"info": "information", "warn": "warning", "error": "error"}


def _tui_notify(app: Any, text: str, level: str) -> None:
    severity = _NOTIFY_SEVERITY.get(level, "information")
    app.call_from_thread(app.notify, text, severity=severity, timeout=6.0)


def _tui_status_update(app: Any, text: str, level: str) -> None:
    app.call_from_thread(app._set_runtime_status, text, level, 6.0)


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
    hook_specs = getattr(getattr(app, "ctx", None), "hook_specs", {})
    specs = list(hook_specs.get(("pre", event), []))
    selected = [
        spec
        for spec in specs
        if bool(spec.enabled) and (not spec.views or view in spec.views)
    ]
    if not selected:
        return PreOutcome(cancelled=False, reason="", change=dict(change))

    done = threading.Event()
    out = PreOutcome(cancelled=False, reason="", change=dict(change))

    def _run() -> None:
        nonlocal out
        out = _run_pre_chain(app, event, list(targets), dict(change), view, selected)
        done.set()

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    done.wait()
    return out


def _run_pre_chain(
    app: Any,
    event: str,
    targets: list[HookTarget],
    change: dict[str, object],
    view: str,
    specs: list[Any],
) -> PreOutcome:
    running_change = dict(change)
    for spec in specs:
        spec_id = f"pre/{event}/{spec.name}"
        app.call_from_thread(app._busy_start, f"hook: {spec_id}")
        app.hook_running[spec_id] = time.time()
        try:
            module = resolve_hook_module(spec, Path(app.base_dir))
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
                timing="pre",
                event=event,
                config=dict(spec.config),
            )

            def _add_event(path: Path, kind: str, payload: dict[str, object]) -> None:
                app.call_from_thread(append_base_log, path, kind, payload)

            def _notify(text: str, level: str = "info") -> None:
                _tui_notify(app, text, level)

            def _status_update(text: str, level: str = "info") -> None:
                _tui_status_update(app, text, level)

            def _log(text: str, level: str = "info") -> None:
                app.call_from_thread(app._log, text, level)

            context = HookContext(
                event=event,
                timing="pre",
                view=view,
                base_dir=Path(app.base_dir),
                targets=tuple(targets),
                change=running_change,
                runtime=runtime,
                hook=info,
                add_event=_add_event,
                notify=_notify,
                status_update=_status_update,
                log=_log,
                ask=_build_tui_ask(app),
            )
            result = module.run(context)
            if isinstance(result, PreResult):
                if result.decision == "cancel":
                    return PreOutcome(cancelled=True, reason=str(result.reason), change=running_change)
                if result.decision == "mutate" and isinstance(result.mutated_change, dict):
                    _apply_pre_mutation(
                        event=event,
                        running_change=running_change,
                        mutated=result.mutated_change,
                        notify=lambda text: _notify(text, "warn"),
                    )
        except HOOK_RUN_ERRORS as exc:
            tb_tail = "\n".join(traceback.format_exception(type(exc), exc, exc.__traceback__)[-6:])
            app.call_from_thread(app._show_runtime_error, f"hook {spec.name}", exc, tb_tail)
            return PreOutcome(cancelled=True, reason=str(exc), change=running_change)
        finally:
            app.call_from_thread(app._busy_stop)
            app.hook_running.pop(spec_id, None)
    return PreOutcome(cancelled=False, reason="", change=running_change)


def _build_tui_ask(app: Any):
    def _ask(*_args: object, **kwargs: object) -> str | None:
        prompt_text = str(kwargs.get("prompt", "confirm?"))
        kind = str(kwargs.get("kind", "yes_no") or "yes_no")
        default = kwargs.get("default")
        response_ready = threading.Event()
        response: dict[str, str | None] = {"value": None}

        def _set_response(value: str | None) -> None:
            response["value"] = value
            response_ready.set()

        def _present() -> None:
            if kind == "yes_no":
                confirm_cls = getattr(app, "_confirm_screen_cls", None)
                if confirm_cls is None:
                    _set_response(None)
                    return
                app.push_screen(confirm_cls(prompt_text), lambda ok: _set_response("yes" if bool(ok) else None))
                return
            if kind == "text":
                input_cls = getattr(app, "_input_screen_cls", None)
                if input_cls is None:
                    _set_response(None)
                    return
                seed = str(default) if default is not None else ""
                app.push_screen(input_cls(prompt_text, "value", seed), lambda value: _set_response(value))
                return
            if kind == "choice":
                choices = kwargs.get("choices", [])
                options = [str(item) for item in choices if str(item).strip()]
                choice_cls = getattr(app, "_single_choice_screen_cls", None)
                if choice_cls is None:
                    _set_response(None)
                    return
                entries = [(opt, opt) for opt in options]
                app.push_screen(choice_cls(prompt_text, entries), lambda value: _set_response(value))
                return
            _set_response(None)

        app.call_from_thread(_present)
        response_ready.wait()
        return response["value"]

    return _ask


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


def dispatch_post_cli(
    *,
    base_dir: Path,
    hook_specs: dict[tuple[str, str], list[Any]],
    event: str,
    targets: list[HookTarget],
    change: dict[str, object],
    view: str,
) -> None:
    specs = list(hook_specs.get(("post", event), []))
    selected = [
        spec
        for spec in specs
        if bool(spec.enabled) and (not spec.views or view in spec.views)
    ]
    if not selected:
        return
    for spec in selected:
        spec_id = f"post/{event}/{spec.name}"
        started = time.time()
        slow_timer: threading.Timer | None = None
        running = threading.Event()
        running.set()
        print(f"[hook] {spec_id} ... running", file=os.sys.stderr)
        hook_error = ""

        def _warn_slow() -> None:
            if not running.is_set():
                return
            elapsed = max(0.0, time.time() - started)
            print(
                f"[hook] {spec_id} still running ({elapsed:.1f}s)",
                file=os.sys.stderr,
            )
            nonlocal slow_timer
            slow_timer = threading.Timer(max(0.05, float(spec.slow_warn_s)), _warn_slow)
            slow_timer.daemon = True
            slow_timer.start()

        try:
            module = resolve_hook_module(spec, base_dir)
            if len(targets) == 1:
                append_base_log(
                    targets[0].path,
                    "hook_started",
                    {"hook": spec.name, "timing": "post", "event": event},
                )
            slow_timer = threading.Timer(max(0.05, float(spec.slow_warn_s)), _warn_slow)
            slow_timer.daemon = True
            slow_timer.start()
            _run_cli_module(
                module,
                base_dir=base_dir,
                event=event,
                view=view,
                targets=targets,
                change=change,
                spec=spec,
            )
        except HOOK_RUN_ERRORS as exc:
            hook_error = str(exc)
            print(f"[hook] {spec_id} failed: {hook_error}", file=os.sys.stderr)
        finally:
            running.clear()
            if slow_timer is not None:
                slow_timer.cancel()
            duration = max(0.0, time.time() - started)
            if len(targets) == 1:
                append_base_log(
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
            if not hook_error:
                print(f"[hook] {spec_id} done in {duration:.1f}s", file=os.sys.stderr)


def _run_cli_module(
    module: ModuleType,
    *,
    base_dir: Path,
    event: str,
    view: str,
    targets: list[HookTarget],
    change: dict[str, object],
    spec: Any,
) -> None:
    runtime = HookRuntime(
        invoker="cli",
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

    def _add_event(path: Path, kind: str, payload: dict[str, object]) -> None:
        append_base_log(path, kind, payload)

    def _notify(text: str, level: str = "info") -> None:
        print(f"[hook] {level}: {text}", file=os.sys.stderr)

    def _status_update(text: str, level: str = "info") -> None:
        print(f"[hook] status {level}: {text}", file=os.sys.stderr)

    def _log(text: str, level: str = "info") -> None:
        print(f"[hook] {level}: {text}")

    context = HookContext(
        event=event,
        timing="post",
        view=view,
        base_dir=base_dir,
        targets=tuple(targets),
        change=dict(change),
        runtime=runtime,
        hook=info,
        add_event=_add_event,
        notify=_notify,
        status_update=_status_update,
        log=_log,
        ask=lambda *_args, **_kwargs: None,
    )
    captured_out = io.StringIO()
    captured_err = io.StringIO()
    with redirect_stdout(captured_out), redirect_stderr(captured_err):
        module.run(context)
    out_text = captured_out.getvalue().strip()
    err_text = captured_err.getvalue().strip()
    if out_text:
        _log(f"hook {spec.name} stdout: {out_text}", "info")
    if err_text:
        _notify(f"hook {spec.name} stderr: {err_text}", "warn")


def dispatch_pre_cli(
    *,
    base_dir: Path,
    hook_specs: dict[tuple[str, str], list[Any]],
    event: str,
    targets: list[HookTarget],
    change: dict[str, object],
    view: str,
) -> PreOutcome:
    specs = list(hook_specs.get(("pre", event), []))
    selected = [
        spec
        for spec in specs
        if bool(spec.enabled) and (not spec.views or view in spec.views)
    ]
    running_change = dict(change)
    if not selected:
        return PreOutcome(cancelled=False, reason="", change=running_change)
    for spec in selected:
        spec_id = f"pre/{event}/{spec.name}"
        print(f"[hook] {spec_id} ... running", file=os.sys.stderr)
        try:
            module = resolve_hook_module(spec, base_dir)
            result = _run_cli_pre_module(
                module,
                base_dir=base_dir,
                event=event,
                view=view,
                targets=targets,
                change=running_change,
                spec=spec,
            )
            if isinstance(result, PreResult):
                if result.decision == "cancel":
                    reason = str(result.reason or "cancelled by hook")
                    print(f"[hook] {spec_id} cancelled: {reason}", file=os.sys.stderr)
                    return PreOutcome(cancelled=True, reason=reason, change=running_change)
                if result.decision == "mutate" and isinstance(result.mutated_change, dict):
                    _apply_pre_mutation(
                        event=event,
                        running_change=running_change,
                        mutated=result.mutated_change,
                        notify=lambda text: print(f"[hook] warn: {text}", file=os.sys.stderr),
                    )
        except HOOK_RUN_ERRORS as exc:
            reason = str(exc)
            print(f"[hook] {spec_id} failed: {reason}", file=os.sys.stderr)
            return PreOutcome(cancelled=True, reason=reason, change=running_change)
        print(f"[hook] {spec_id} done", file=os.sys.stderr)
    return PreOutcome(cancelled=False, reason="", change=running_change)


def _run_cli_pre_module(
    module: ModuleType,
    *,
    base_dir: Path,
    event: str,
    view: str,
    targets: list[HookTarget],
    change: dict[str, object],
    spec: Any,
) -> object:
    runtime = HookRuntime(
        invoker="cli",
        homebase_version=homebase_version,
        now_iso=datetime.now(timezone.utc).isoformat(),
        now_ts=int(time.time()),
        user=str(getpass.getuser() or ""),
    )
    info = HookInfo(
        name=str(spec.name),
        source=str(spec.source),
        timing="pre",
        event=event,
        config=dict(spec.config),
    )

    def _add_event(path: Path, kind: str, payload: dict[str, object]) -> None:
        append_base_log(path, kind, payload)

    def _notify(text: str, level: str = "info") -> None:
        print(f"[hook] {level}: {text}", file=os.sys.stderr)

    def _status_update(text: str, level: str = "info") -> None:
        print(f"[hook] status {level}: {text}", file=os.sys.stderr)

    def _log(text: str, level: str = "info") -> None:
        print(f"[hook] {level}: {text}")

    def _ask(*_args: object, **kwargs: object) -> str | None:
        prompt_text = str(kwargs.get("prompt", "confirm?"))
        kind = str(kwargs.get("kind", "yes_no") or "yes_no")
        default = kwargs.get("default")
        if kind == "yes_no":
            default_bool = bool(default) if isinstance(default, bool) else False
            ok = prompting.prompt_yes_no(prompt_text, default=default_bool)
            return "yes" if ok else None
        if kind == "text":
            response = input(f"{prompt_text} ")
            text = str(response).strip()
            if not text and default is not None:
                return str(default)
            return text or None
        if kind == "choice":
            choices = kwargs.get("choices", [])
            options = [str(item) for item in choices if str(item).strip()]
            if not options:
                return None
            print(f"{prompt_text}: {', '.join(options)}")
            response = input("> ").strip()
            if not response and default is not None:
                return str(default)
            return response or None
        return None

    context = HookContext(
        event=event,
        timing="pre",
        view=view,
        base_dir=base_dir,
        targets=tuple(targets),
        change=dict(change),
        runtime=runtime,
        hook=info,
        add_event=_add_event,
        notify=_notify,
        status_update=_status_update,
        log=_log,
        ask=_ask,
    )
    captured_out = io.StringIO()
    captured_err = io.StringIO()
    with redirect_stdout(captured_out), redirect_stderr(captured_err):
        result = module.run(context)
    out_text = captured_out.getvalue().strip()
    err_text = captured_err.getvalue().strip()
    if out_text:
        _log(f"hook {spec.name} stdout: {out_text}", "info")
    if err_text:
        _notify(f"hook {spec.name} stderr: {err_text}", "warn")
    return result


def _apply_pre_mutation(
    *,
    event: str,
    running_change: dict[str, object],
    mutated: dict[str, object],
    notify,
) -> None:
    allowed = _PRE_MUTATION_ALLOWLIST.get(event, frozenset())
    for key, value in mutated.items():
        if key not in allowed:
            notify(f"pre-hook mutation ignored for {event}: key {key!r} is not allowed")
            continue
        running_change[key] = value


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
            _tui_notify(app, text, level)

        def _status_update_on_main(text: str, level: str = "info") -> None:
            _tui_status_update(app, text, level)

        def _add_event_on_main(path: Path, kind: str, payload: dict[str, object]) -> None:
            app.call_from_thread(append_base_log, path, kind, payload)

        def _ask_noop(*_args: object, **_kwargs: object) -> str | None:
            return None

        def _warn_slow() -> None:
            if not still_running.is_set():
                return
            elapsed = max(0.0, time.time() - started_ts)
            _status_update_on_main(
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
            status_update=_status_update_on_main,
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
            _status_update_on_main(f"hook {spec_id} running on {len(targets)} target(s)", "info")
        app.call_from_thread(app._busy_start, f"hook: {spec_id}")
        app.hook_running[spec_id] = started_ts

        try:
            module = resolve_hook_module(spec, Path(app.base_dir))
            slow_timer = threading.Timer(max(0.05, float(spec.slow_warn_s)), _warn_slow)
            slow_timer.daemon = True
            slow_timer.start()
            captured_out = io.StringIO()
            captured_err = io.StringIO()
            with redirect_stdout(captured_out), redirect_stderr(captured_err):
                module.run(context)
            out_text = captured_out.getvalue().strip()
            err_text = captured_err.getvalue().strip()
            if out_text:
                _log_on_main(f"hook {spec_id} stdout: {out_text}", "info")
            if err_text:
                _log_on_main(f"hook {spec_id} stderr: {err_text}", "warn")
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
                _status_update_on_main(
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
