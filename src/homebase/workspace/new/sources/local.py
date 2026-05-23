from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

from ....cache.api import cache_upsert_project_fast
from ....core.constants import BASE_MARKER_FILE, LEGACY_BASE_MARKER_FILE
from ....core.logging import verbose_enabled
from ....core.utils import is_under
from ....metadata.api import (
    append_base_log,
    ensure_base_marker,
    save_base_repo_dir,
    save_base_tags,
)
from ..base import NewContext, NewOptions, NewPlan, NewResult, Source
from ..detect import classify_input
from ..name import resolve_final_name
from ..prompt import PromptError, confirm
from ..registry import register_source


def _debug_enabled() -> bool:
    if verbose_enabled(3):
        return True
    raw = str(os.environ.get("HOMEBASE_DEBUG", "")).strip().lower()
    return raw in {"1", "true", "yes", "on", "y"}


def _debug_log(message: str) -> None:
    if not _debug_enabled():
        return
    print(f"[debug] local: {message}", file=os.sys.stderr)


def _decide_repo_wrap(src: Path, options: NewOptions) -> bool:
    """If `src` contains a `.git/`, decide whether to wrap the move
    under `<target>/repo/` (matching the git-clone layout). Interactive
    TTYs get a prompt (default yes); non-interactive contexts wrap
    unconditionally."""
    if not (src / ".git").exists():
        return False
    if options.yes or not sys.stdin.isatty():
        return True
    try:
        return confirm(
            f"'{src.name}' contains .git — place under '<project>/repo/'?",
            default=True,
        )
    except PromptError:
        return True


@register_source
class LocalDirSource(Source):
    key = "local"
    help_short = "Move an existing directory into base."
    default_options = {}
    default_config = {}

    def detects(self, raw_input, ctx: NewContext) -> bool:
        return classify_input(raw_input) == "path"

    def infer_name(self, raw_input, ctx: NewContext) -> str | None:
        if not raw_input:
            return None
        raw = Path(str(raw_input)).expanduser()
        src = raw.resolve() if raw.is_absolute() else (ctx.cwd / raw).resolve()
        return src.name or None

    def plan(
        self,
        raw_input,
        name: str,
        options: NewOptions,
        ctx: NewContext,
    ) -> NewPlan:
        if not raw_input:
            raise ValueError("local source requires a path")
        raw = Path(str(raw_input)).expanduser()
        if raw.is_absolute():
            src = raw.resolve()
        else:
            src = (ctx.cwd / raw).resolve()
        if not src.exists():
            raise ValueError(f"path not found: {src}")
        if not src.is_dir():
            raise ValueError(f"not a directory: {src}")
        if is_under(src, ctx.base_dir):
            # Reshuffling an existing base project via `b new` is wrong
            # — `b mv` is the right tool. But a non-project subfolder
            # inside a project's working tree (e.g. `b new featx/` from
            # inside `<base>/foo/repo/`) is the user's documented way
            # to spin a working-copy folder out as its own sibling
            # project.
            if src == ctx.base_dir.resolve():
                raise ValueError(f"cannot move base dir itself: {src}")
            if (src / BASE_MARKER_FILE).exists() or (src / LEGACY_BASE_MARKER_FILE).exists():
                raise ValueError(f"already a base project: {src}")

        final_name = resolve_final_name(
            ctx.base_dir,
            name,
            add_date_prefix=options.timestamp,
            add_tmp_suffix=options.tmp,
            ts_name=options.ts_name,
            alpha_name=options.alpha_name,
        )
        open_shell = options.open and not is_under(ctx.cwd.resolve(), src)
        target = ctx.base_dir / final_name
        wrap_in_repo = _decide_repo_wrap(src, options)
        dest = (target / "repo") if wrap_in_repo else target
        steps: list[str] = []
        if wrap_in_repo:
            steps.append(f"mkdir {target}")
        steps.append(f"move {src} -> {dest}")
        steps.append(f"write {target}/.base.yaml")
        if options.tags:
            steps.append(f"set tags {list(options.tags)}")
        return NewPlan(
            source_key=self.key,
            name=final_name,
            target=target,
            steps=steps,
            tags=list(options.tags),
            template=options.template,
            post_commands=list(options.post),
            log_kind="migration",
            log_payload={
                "kind": "local-move",
                "source": str(src),
                "destination": str(dest),
            },
            input=raw_input,
            open_shell=open_shell,
            signals=[str(src)],
        )

    def apply(self, plan: NewPlan, ctx: NewContext) -> NewResult:
        started = time.time()
        target = plan.target
        if target.exists():
            raise ValueError(f"target already exists: {target}")
        src = Path(plan.log_payload["source"])
        dest_str = plan.log_payload.get("destination")
        dest = Path(dest_str) if dest_str else target
        wrapped = dest != target
        _debug_log(f"apply start src={src} target={target} dest={dest} wrapped={wrapped}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            t0 = time.time()
            shutil.move(str(src), str(dest))
            _debug_log(f"move done elapsed={max(0.0, time.time() - t0):.3f}s")
        except (OSError, shutil.Error) as exc:
            if wrapped and target.exists():
                try:
                    target.rmdir()
                except OSError:
                    pass
            raise ValueError(f"move failed: {exc}") from exc
        try:
            t0 = time.time()
            ensure_base_marker(target)
            _debug_log(f"marker done elapsed={max(0.0, time.time() - t0):.3f}s")
            # Record where the moved-in repo actually lives if the
            # source carried one. Without .git there's nothing to
            # pin, so we leave repo_dir unset.
            if (dest / ".git").exists():
                save_base_repo_dir(target, "repo" if wrapped else ".")
            if plan.tags:
                clean = sorted({t.strip() for t in plan.tags if t.strip()})
                if clean:
                    t0 = time.time()
                    save_base_tags(ctx.base_dir, target, clean)
                    _debug_log(f"save tags done elapsed={max(0.0, time.time() - t0):.3f}s")
            t0 = time.time()
            append_base_log(target, plan.log_kind, plan.log_payload)
            _debug_log(f"append log done elapsed={max(0.0, time.time() - t0):.3f}s")
        except (OSError, ValueError):
            try:
                shutil.move(str(dest), str(src))
            except (OSError, shutil.Error):
                pass
            if wrapped and target.exists():
                try:
                    shutil.rmtree(target)
                except OSError:
                    pass
            raise
        t0 = time.time()
        cache_upsert_project_fast(ctx.base_dir, target)
        _debug_log(f"cache upsert done elapsed={max(0.0, time.time() - t0):.3f}s")
        _debug_log(f"apply done total_elapsed={max(0.0, time.time() - started):.3f}s")
        return NewResult(target=target, open_shell=plan.open_shell)
