from __future__ import annotations

import shutil
import subprocess

from ....metadata.api import append_base_log, ensure_base_marker, save_base_tags
from ....workspace.projects import cache_upsert_project_fast
from ...projects import scaffold_template_directory
from ..base import NewContext, NewOptions, NewPlan, NewResult, Source
from ..detect import classify_input
from ..name import resolve_final_name
from ..registry import register_source


@register_source
class EmptySource(Source):
    key = "empty"
    help_short = "Create an empty project (bare name)."
    default_options = {}
    default_config = {}

    def detects(self, raw_input, ctx: NewContext) -> bool:
        return classify_input(raw_input) == "bare"

    def infer_name(self, raw_input, ctx: NewContext) -> str | None:
        if not raw_input:
            return None
        return str(raw_input)

    def plan(
        self,
        raw_input,
        name: str,
        options: NewOptions,
        ctx: NewContext,
    ) -> NewPlan:
        final_name = resolve_final_name(
            ctx.base_dir,
            name,
            add_date_prefix=options.timestamp,
            add_tmp_suffix=options.tmp,
            ts_name=options.ts_name,
            alpha_name=options.alpha_name,
        )
        target = ctx.base_dir / final_name
        steps = [f"mkdir {target}", f"write {target}/.base.yaml"]
        if options.tags:
            steps.append(f"set tags {list(options.tags)}")
        if options.template:
            steps.append(f"apply template {options.template}")
        return NewPlan(
            source_key=self.key,
            name=final_name,
            target=target,
            steps=steps,
            tags=list(options.tags),
            template=options.template,
            post_commands=list(options.post),
            log_kind="creation",
            log_payload={"kind": "empty"},
            input=raw_input,
            open_shell=options.open,
        )

    def apply(self, plan: NewPlan, ctx: NewContext) -> NewResult:
        target = plan.target
        if target.exists():
            raise ValueError(f"target already exists: {target}")
        target.mkdir(parents=True)
        try:
            if plan.template:
                _apply_template(ctx.base_dir, plan.template, target)
            ensure_base_marker(target)
            if plan.tags:
                clean = sorted({t.strip() for t in plan.tags if t.strip()})
                if clean:
                    save_base_tags(ctx.base_dir, target, clean)
            append_base_log(target, plan.log_kind, plan.log_payload)
        except (OSError, ValueError):
            shutil.rmtree(target, ignore_errors=True)
            raise
        cache_upsert_project_fast(ctx.base_dir, target)
        return NewResult(target=target, open_shell=plan.open_shell)


def _apply_template(base_dir, template_key: str, target) -> None:
    template_dir = (base_dir / ".copier" / template_key).resolve()
    if not template_dir.is_dir():
        raise ValueError(f"template not found: {template_key}")
    copier_yml = template_dir / "copier.yml"
    copier_yaml = template_dir / "copier.yaml"
    if copier_yml.is_file() or copier_yaml.is_file():
        if shutil.which("copier") is None:
            raise ValueError("copier is not installed")
        try:
            subprocess.run(
                ["copier", "copy", "--trust", str(template_dir), str(target)],
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise ValueError(f"copier failed: exit {exc.returncode}") from exc
    else:
        scaffold_template_directory(template_dir, target)


__all__ = ["EmptySource"]
