from __future__ import annotations

import os
import sys
import time
from argparse import Namespace
from pathlib import Path
from typing import Callable

from ...core.logging import verbose_enabled
from ..projects import cmd_new as legacy_cmd_new
from .adapters import adapter_for_host, parse_url
from .archive_mod import apply_archive_modifier
from .base import NewContext, NewPlan, NewResult
from .config_loader import NewConfigError, load_new_sources
from .detect import classify_input
from .options import resolve_options
from .prompt import PromptError, ask_name, ask_source, confirm
from .registry import builtin_keys, construct_source, get_source_class

_BUILTIN_KEYS = {"empty", "local", "git", "download", "downloaded"}
_SHAPE_TO_SOURCE = {
    "bare": "empty",
    "path": "local",
}


def _debug_enabled() -> bool:
    if verbose_enabled(3):
        return True
    raw = str(os.environ.get("HOMEBASE_DEBUG", "")).strip().lower()
    return raw in {"1", "true", "yes", "on", "y"}


def _debug_log(message: str) -> None:
    if not _debug_enabled():
        return
    print(f"[debug] new: {message}", file=sys.stderr)


def _local_move_contains_cwd(plan: NewPlan, ctx: NewContext) -> bool:
    if plan.source_key != "local":
        return False
    if not isinstance(plan.log_payload, dict):
        return False
    source = plan.log_payload.get("source")
    if not isinstance(source, str) or not source.strip():
        return False
    src = Path(source)
    if src == ctx.cwd:
        return True
    try:
        ctx.cwd.relative_to(src)
        return True
    except ValueError:
        return False


def _local_move_handoff_target(plan: NewPlan, ctx: NewContext) -> Path | None:
    if plan.source_key != "local":
        return None
    if not isinstance(plan.log_payload, dict):
        return None
    source = plan.log_payload.get("source")
    if not isinstance(source, str) or not source.strip():
        return None
    src = Path(source)
    target = plan.target
    try:
        rel = ctx.cwd.relative_to(src)
    except ValueError:
        return target if ctx.cwd == src else None
    return (target / rel).resolve()


def _pick_url_source(url: str, git_hosts: dict[str, str]) -> str:
    parsed = parse_url(url)
    if parsed is not None:
        adapter = adapter_for_host(parsed.host, git_hosts)
        if adapter is not None:
            # Check download first so any file-shaped URL the adapter
            # recognises (github blob, gitlab/gitea raw, …) routes to
            # download even if a too-permissive ``to_clone_url`` would
            # also claim the URL. ``to_clone_url`` is reserved for
            # repo-root / branch-root shapes that the user clearly
            # wants to clone.
            if adapter.to_download_url(parsed):
                return "download"
            if adapter.to_clone_url(parsed):
                return "git"
        if parsed.is_ssh or parsed.path.endswith(".git") or ".git/" in parsed.path:
            return "git"
        return "download"
    # parse_url rejects scheme-only URLs (e.g. file:///path). Fall back
    # to a simple suffix probe so local bare repos work.
    if url.endswith(".git") or ".git/" in url:
        return "git"
    return "download"


def autodetect_source_key(
    raw_input: str | None,
    sources_cfg: dict[str, dict],
    *,
    cwd: Path | None = None,
) -> str | None:
    if raw_input is None:
        return None
    shape = classify_input(raw_input)
    if shape == "url":
        git_hosts = (
            sources_cfg.get("git", {}).get("config", {}).get("hosts") or {}
        )
        return _pick_url_source(raw_input, git_hosts)
    source_key = _SHAPE_TO_SOURCE.get(shape)
    if source_key != "local" or raw_input is None:
        return source_key
    raw_path = Path(str(raw_input)).expanduser()
    resolved = raw_path.resolve() if raw_path.is_absolute() else ((cwd or Path.cwd().resolve()) / raw_path).resolve()
    if resolved.exists():
        return "local"
    return "local" if raw_path.is_absolute() else "empty"


def _resolve_base_key(child_key: str, sources_cfg: dict[str, dict]) -> str | None:
    base_key = child_key
    walked: list[str] = []
    while base_key not in _BUILTIN_KEYS:
        if base_key in walked:
            return None  # cycle
        walked.append(base_key)
        entry = sources_cfg.get(base_key)
        if entry is None:
            return None
        parent = entry.get("parent")
        if not parent:
            return None
        base_key = parent
    return base_key


def format_summary(plan: NewPlan) -> str:
    """Multi-line human summary of a successful creation. Shared by
    the CLI dispatcher (``_process_item``) and the TUI bridge so both
    surfaces print exactly the same block after ``b new`` finishes."""
    lines = [
        f"created: {plan.target}",
        f"  source:   {plan.source_key}",
    ]
    if plan.tags:
        lines.append(f"  tags:     {', '.join(plan.tags)}")
    if plan.template:
        lines.append(f"  template: {plan.template}")
    if plan.steps:
        lines.append("  steps:")
        for step in plan.steps:
            lines.append(f"    - {step}")
    return "\n".join(lines)


def _print_plan(plan: NewPlan) -> None:
    print(f"source:   {plan.source_key}")
    print(f"name:     {plan.name}")
    print(f"target:   {plan.target}")
    if plan.tags:
        print(f"tags:     {list(plan.tags)}")
    if plan.template:
        print(f"template: {plan.template}")
    print("steps:")
    for step in plan.steps:
        print(f"  - {step}")
    if plan.post_commands:
        print("post:")
        for cmd in plan.post_commands:
            print(f"  $ {cmd}")


def plan_and_apply_one(
    ns: Namespace,
    raw_input: str | None,
    explicit_name: str | None,
    sources_cfg: dict[str, dict],
    ctx: NewContext,
) -> tuple[int, NewResult | None, NewPlan | None]:
    """Single-item pipeline shared by the CLI dispatcher and the TUI.

    Returns ``(rc, result, plan)`` where ``rc`` is the exit code,
    ``result`` is the apply result on success (or ``None``), and
    ``plan`` is the resolved plan (also returned on dry-run). The
    function never spawns shells — that's the caller's job.
    """
    started = time.time()
    _debug_log(f"start raw_input={raw_input!r} explicit_name={explicit_name!r}")
    mode = getattr(ns, "mode", None)
    child_key = getattr(ns, "child_key", None)
    if mode == "auto":
        mode = None
    if child_key == "auto":
        child_key = None
    forced = bool(mode) or bool(child_key)

    if child_key:
        source_key = str(child_key)
    elif mode:
        source_key = str(mode)
    else:
        source_key = autodetect_source_key(raw_input, sources_cfg, cwd=ctx.cwd) or ""

    if getattr(ns, "ask_source", False) and not forced:
        try:
            available = sorted(set(_BUILTIN_KEYS) | set(sources_cfg.keys()))
            source_key = ask_source(available, default=source_key or None)
        except PromptError as exc:
            print(f"b new: {exc}", file=sys.stderr)
            return 2, None, None

    if not source_key:
        print(
            f"b new: cannot determine source for input: {raw_input!r}",
            file=sys.stderr,
        )
        return 2, None, None

    base_key = _resolve_base_key(source_key, sources_cfg)
    _debug_log(f"resolved source source_key={source_key!r} base_key={base_key!r}")
    if base_key is None:
        print(f"b new: invalid source: {source_key}", file=sys.stderr)
        return 2, None, None

    try:
        get_source_class(base_key)
    except KeyError as exc:
        print(f"b new: {exc}", file=sys.stderr)
        return 2, None, None

    child_cfg = sources_cfg.get(source_key, {}) if source_key != base_key else (
        sources_cfg.get(base_key, {})
    )
    source_config = dict(child_cfg.get("config") or {}) if isinstance(child_cfg, dict) else {}
    if base_key == "download":
        git_hosts = (
            sources_cfg.get("git", {}).get("config", {}).get("hosts") or {}
        )
        source_config.setdefault("hosts", git_hosts)
    source = construct_source(base_key, source_config)
    options = resolve_options(base_key, ns, source_cfg=child_cfg)

    # Interactive setup hook (DownloadedSource uses this to prompt
    # for which recent file to use). Most sources are no-ops.
    try:
        source.prepare(ns, ctx)
    except ValueError as exc:
        print(f"b new: {exc}", file=sys.stderr)
        return 2, None, None

    if not source.accepts_input:
        if raw_input is not None and explicit_name is not None:
            print(
                f"b new: source '{base_key}' takes no <input> positional",
                file=sys.stderr,
            )
            return 2, None, None
        explicit_name = explicit_name if explicit_name is not None else raw_input
        raw_input = None

    if base_key == "empty" and raw_input and classify_input(raw_input) == "path":
        explicit_name = explicit_name or Path(str(raw_input).rstrip("/\\")).name
        raw_input = None

    if options.ask_name:
        if explicit_name is not None:
            print(
                "b new: --ask-name conflicts with <name> positional",
                file=sys.stderr,
            )
            return 2, None, None
        suggested = source.infer_name(raw_input, ctx)
        if raw_input:
            print(f"\nitem: {raw_input}  (source: {base_key})")
        else:
            print(f"\nitem: (source: {base_key})")
        try:
            explicit_name = ask_name(default=suggested)
        except PromptError as exc:
            print(f"b new: {exc}", file=sys.stderr)
            return 2, None, None

    name = explicit_name or source.infer_name(raw_input, ctx) or ""
    if not name and not (options.ts_name or options.alpha_name):
        print("b new: cannot determine project name", file=sys.stderr)
        return 2, None, None

    try:
        _debug_log(f"plan start source={base_key}")
        plan = source.plan(raw_input, name, options, ctx)
        _debug_log(f"plan done target={plan.target}")
    except ValueError as exc:
        print(f"b new: {exc}", file=sys.stderr)
        return 1, None, None

    if options.archive:
        plan = apply_archive_modifier(plan, ctx)

    if options.dry_run:
        _print_plan(plan)
        return 0, None, plan

    if options.confirm and not options.yes:
        _print_plan(plan)
        try:
            ok = confirm()
        except PromptError as exc:
            print(f"b new: {exc}", file=sys.stderr)
            return 2, None, plan
        if not ok:
            print("aborted")
            return 1, None, plan

    try:
        _debug_log(f"apply start source={base_key} target={plan.target}")
        result = source.apply(plan, ctx)
        elapsed = max(0.0, time.time() - started)
        _debug_log(f"apply done target={result.target} elapsed={elapsed:.3f}s")
    except ValueError as exc:
        print(f"b new: {exc}", file=sys.stderr)
        return 1, None, plan

    return 0, result, plan


def _process_item(
    ns: Namespace,
    raw_input: str | None,
    explicit_name: str | None,
    sources_cfg: dict[str, dict],
    ctx: NewContext,
    pre_create_hook: Callable[[Namespace, str | None, str | None], tuple[bool, str, Namespace, str | None, str | None]] | None = None,
    post_create_hook: Callable[[NewResult, NewPlan | None, str | None, str | None], None] | None = None,
) -> int:
    if callable(pre_create_hook):
        proceed, reason, ns, raw_input, explicit_name = pre_create_hook(
            ns,
            raw_input,
            explicit_name,
        )
        if not proceed:
            print(f"b new: cancelled by hook: {reason}", file=sys.stderr)
            return 1
    rc, result, plan = plan_and_apply_one(
        ns,
        raw_input,
        explicit_name,
        sources_cfg,
        ctx,
    )
    if result is not None:
        if callable(post_create_hook):
            post_create_hook(result, plan, raw_input, explicit_name)
        if plan is not None:
            print(format_summary(plan))
            moved_cwd = _local_move_contains_cwd(plan, ctx)
            if moved_cwd:
                suggested_cd = _local_move_handoff_target(plan, ctx) or result.target
                wrapper_handoff = bool(os.environ.get("HOMEBASE_CD_FILE", "")) and not bool(result.open_shell)
                if wrapper_handoff:
                    from ...tmux.flow import open_shell_in_dir

                    _debug_log("moved cwd detected; writing wrapper cd handoff")
                    _ = open_shell_in_dir(suggested_cd)
                else:
                    print(
                        f"warning: moved current working directory; run `cd {suggested_cd}` (or use `b shell-init`)",
                        file=sys.stderr,
                    )
        else:
            print(f"created: {result.target}")
        if result.open_shell:
            from ...tmux.flow import open_shell_in_dir

            _debug_log("opening shell in target")
            return open_shell_in_dir(result.target)
    return rc


def cmd_new(
    ns: Namespace,
    base_dir: Path,
    cwd: Path,
    pre_create_hook: Callable[[Namespace, str | None, str | None], tuple[bool, str, Namespace, str | None, str | None]] | None = None,
    post_create_hook: Callable[[NewResult, NewPlan | None, str | None, str | None], None] | None = None,
) -> int:
    _ = builtin_keys()  # ensure sources are registered
    raw_inputs: list[str] = list(getattr(ns, "inputs", []) or [])
    multi = bool(getattr(ns, "multi", False))

    if not raw_inputs and not getattr(ns, "mode", None) and not getattr(ns, "child_key", None):
        return legacy_cmd_new(base_dir)

    try:
        sources_cfg = load_new_sources(base_dir)
    except NewConfigError as exc:
        print(f"b new: {exc}", file=sys.stderr)
        return 2

    ctx = NewContext(base_dir=base_dir, cwd=cwd)

    if multi:
        if not raw_inputs:
            # Allow --multi with --downloaded (zero positionals OK).
            return _process_item(
                ns,
                None,
                None,
                sources_cfg,
                ctx,
                pre_create_hook,
                post_create_hook,
            )
        worst = 0
        for raw in raw_inputs:
            rc = _process_item(
                ns,
                raw,
                None,
                sources_cfg,
                ctx,
                pre_create_hook,
                post_create_hook,
            )
            if rc != 0:
                worst = rc if worst == 0 or rc > worst else worst
                print(f"item failed: {raw}", file=sys.stderr)
        return worst

    # Single-item mode
    if len(raw_inputs) > 2:
        print(
            "b new: too many positionals (use --multi)",
            file=sys.stderr,
        )
        return 2
    raw_input = raw_inputs[0] if raw_inputs else None
    explicit_name = raw_inputs[1] if len(raw_inputs) > 1 else None
    return _process_item(
        ns,
        raw_input,
        explicit_name,
        sources_cfg,
        ctx,
        pre_create_hook,
        post_create_hook,
    )
