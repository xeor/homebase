from __future__ import annotations

import shutil
from pathlib import Path

from ....cache.api import cache_upsert_project_fast
from ....core.utils import is_under
from ....metadata.api import (
    append_base_log,
    ensure_base_marker,
    save_base_tags,
    sync_tag_symlinks,
)
from ..base import NewContext, NewOptions, NewPlan, NewResult, Source
from ..detect import classify_input
from ..name import resolve_final_name
from ..registry import register_source


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
        cleaned = str(raw_input).rstrip("/\\")
        return Path(cleaned).name or None

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
            raise ValueError(f"already under base: {src}")

        final_name = resolve_final_name(
            ctx.base_dir,
            name,
            add_date_prefix=options.timestamp,
            add_tmp_suffix=options.tmp,
            ts_name=options.ts_name,
            alpha_name=options.alpha_name,
        )
        target = ctx.base_dir / final_name
        steps = [
            f"move {src} -> {target}",
            f"write {target}/.base.yaml",
        ]
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
                "destination": str(target),
            },
            input=raw_input,
            open_shell=options.open,
            signals=[str(src)],
        )

    def apply(self, plan: NewPlan, ctx: NewContext) -> NewResult:
        target = plan.target
        if target.exists():
            raise ValueError(f"target already exists: {target}")
        src = Path(plan.log_payload["source"])
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(src), str(target))
        except (OSError, shutil.Error) as exc:
            raise ValueError(f"move failed: {exc}") from exc
        try:
            ensure_base_marker(target)
            if plan.tags:
                clean = sorted({t.strip() for t in plan.tags if t.strip()})
                if clean:
                    save_base_tags(ctx.base_dir, target, clean)
            append_base_log(target, plan.log_kind, plan.log_payload)
        except (OSError, ValueError):
            # If marker/log fails, attempt to put src back.
            try:
                shutil.move(str(target), str(src))
            except (OSError, shutil.Error):
                pass
            raise
        sync_tag_symlinks(ctx.base_dir)
        cache_upsert_project_fast(ctx.base_dir, target)
        return NewResult(target=target, open_shell=plan.open_shell)
