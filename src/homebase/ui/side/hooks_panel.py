from __future__ import annotations

from typing import Any


def render_hooks_panel(app: Any) -> str:
    lines: list[str] = ["[cyan]configured hooks[/]:"]
    specs = getattr(getattr(app, "ctx", None), "hook_specs", {})
    if not specs:
        lines.append("[dim]none[/]")
    else:
        for (timing, event), spec_list in sorted(specs.items()):
            if not spec_list:
                continue
            lines.append(f"[bold]{timing}/{event}[/]")
            for spec in spec_list:
                status = "enabled" if spec.enabled else "disabled"
                views = ",".join(spec.views) if spec.views else "active,archive"
                lines.append(
                    f"- {spec.name} [{spec.source}] {status} views={views} slow_warn_s={spec.slow_warn_s:g}"
                )
    lines.append("[dim]----------------------------------------[/]")
    lines.append("[cyan]recent runs[/]:")
    has_runs = False
    for key in sorted(getattr(app, "hook_recent", {}).keys()):
        timing, event = key
        runs = getattr(app, "hook_recent", {}).get(key, [])
        for run in runs[-20:]:
            has_runs = True
            state = "ok" if run.ok else "fail"
            err = f" err={run.error}" if run.error else ""
            lines.append(
                f"- {timing}/{event}/{run.name} {state} {run.duration_s:.2f}s{err}"
            )
    if not has_runs:
        lines.append("[dim]no hook runs yet[/]")
    return "\n".join(lines)
