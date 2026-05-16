from __future__ import annotations

import sys
from pathlib import Path

from ..core.models import HookSpec, HookTarget
from ..hooks.refresh import dispatch_refresh_cli
from ..hooks.snapshot import snapshot_target
from ..workspace.filter_compile import compile_filter_expr
from ..workspace.rows import collect_workspace_rows


def _filter_specs(
    hook_specs: dict[tuple[str, str], list[HookSpec]],
    *,
    hook_filter: tuple[str, ...] | None,
    event_filter: tuple[str, ...] | None,
) -> list[HookSpec]:
    matched: list[HookSpec] = []
    for (timing, _evt), specs in hook_specs.items():
        if timing != "post":
            continue
        for spec in specs:
            if not spec.enabled:
                continue
            if hook_filter and spec.name not in hook_filter:
                continue
            if event_filter and spec.event not in event_filter:
                continue
            matched.append(spec)
    return matched


def _select_projects(
    base_dir: Path,
    *,
    project_filters: list[str],
    tag_filters: list[str],
    filter_expr: str,
    select_all: bool,
    show_archived: bool,
) -> tuple[list[HookTarget], str]:
    if not (project_filters or tag_filters or filter_expr or select_all):
        return [], "no selectors given (use --all, --project, --tag, or --filter)"

    active, archived = collect_workspace_rows(base_dir, include_git_dirty=False)
    rows = archived if show_archived else active

    explicit_paths = {Path(p).expanduser().resolve() for p in project_filters}
    if explicit_paths:
        rows = [r for r in rows if r.path.resolve() in explicit_paths]

    if tag_filters:
        wanted = {t.strip() for t in tag_filters if t.strip()}
        rows = [r for r in rows if wanted.issubset(set(r.tags))]

    if filter_expr.strip():
        predicate, err = compile_filter_expr(filter_expr.strip())
        if err:
            return [], f"invalid filter expression: {err}"
        rows = [r for r in rows if predicate(r)]

    targets = [snapshot_target(r, {}) for r in rows]
    return targets, ""


def cmd_hooks_refresh(
    base_dir: Path,
    *,
    hook_specs: dict[tuple[str, str], list[HookSpec]],
    project_filters: list[str],
    tag_filters: list[str],
    filter_expr: str,
    hook_filter: list[str],
    event_filter: list[str],
    select_all: bool,
    show_archived: bool,
    dry_run: bool,
) -> int:
    hooks_tuple = tuple(hook_filter) if hook_filter else None
    events_tuple = tuple(event_filter) if event_filter else None
    specs = _filter_specs(hook_specs, hook_filter=hooks_tuple, event_filter=events_tuple)
    if not specs:
        print("no matching hook specs (post-only, must be enabled)", file=sys.stderr)
        return 1

    targets, err = _select_projects(
        base_dir,
        project_filters=project_filters,
        tag_filters=tag_filters,
        filter_expr=filter_expr,
        select_all=select_all,
        show_archived=show_archived,
    )
    if err:
        print(err, file=sys.stderr)
        return 2
    if not targets:
        print("no projects matched selectors", file=sys.stderr)
        return 0

    if dry_run:
        specs_with_dry_run = [
            _spec_with_dry_run(spec) for spec in specs
        ]
        hook_specs_overlay: dict[tuple[str, str], list[HookSpec]] = {}
        for spec in specs_with_dry_run:
            hook_specs_overlay.setdefault((spec.timing, spec.event), []).append(spec)
    else:
        hook_specs_overlay = {}
        for spec in specs:
            hook_specs_overlay.setdefault((spec.timing, spec.event), []).append(spec)

    view = "archive" if show_archived else "active"
    dispatch_refresh_cli(
        base_dir=base_dir,
        hook_specs=hook_specs_overlay,
        targets=targets,
        view=view,
        event_filter=events_tuple,
        hook_filter=hooks_tuple,
        source="cli",
    )
    return 0


def _spec_with_dry_run(spec: HookSpec) -> HookSpec:
    cfg = dict(spec.config)
    cfg["dry_run"] = True
    return HookSpec(
        timing=spec.timing,
        event=spec.event,
        name=spec.name,
        source=spec.source,
        enabled=spec.enabled,
        views=spec.views,
        config=cfg,
        slow_warn_s=spec.slow_warn_s,
        refresh_enabled=spec.refresh_enabled,
        refresh_min_interval_s=spec.refresh_min_interval_s,
    )
