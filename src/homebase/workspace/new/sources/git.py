from __future__ import annotations

import shutil
import subprocess

from ....cache.api import cache_upsert_project_fast
from ....metadata.api import append_base_log, ensure_base_marker, save_base_tags
from ..adapters import adapter_for_host, parse_url
from ..base import NewContext, NewOptions, NewPlan, NewResult, Source
from ..name import resolve_final_name
from ..registry import register_source


def detect_git_url(raw_input: str | None, user_hosts: dict[str, str]) -> str | None:
    """Return the canonical clone URL if `raw_input` looks like a clone
    target, otherwise None."""
    if not raw_input:
        return None
    parsed = parse_url(raw_input)
    if parsed is not None:
        adapter = adapter_for_host(parsed.host, user_hosts)
        if adapter is not None:
            clone = adapter.to_clone_url(parsed)
            if clone:
                return clone
        if parsed.is_ssh:
            return raw_input
        if parsed.path.endswith(".git"):
            return raw_input
        return None
    # Scheme-only URLs like file:///path/to/repo.git
    if raw_input.endswith(".git") or ".git/" in raw_input:
        return raw_input
    return None


@register_source
class GitSource(Source):
    key = "git"
    help_short = "Clone a git repository into a new project."
    default_options = {}
    default_config = {"hosts": {}}

    def _user_hosts(self) -> dict[str, str]:
        hosts = self.config.get("hosts") or {}
        if not isinstance(hosts, dict):
            return {}
        return {str(k): str(v) for k, v in hosts.items()}

    def detects(self, raw_input, ctx: NewContext) -> bool:
        return detect_git_url(raw_input, self._user_hosts()) is not None

    def infer_name(self, raw_input, ctx: NewContext) -> str | None:
        if not raw_input:
            return None
        parsed = parse_url(raw_input)
        if parsed is not None:
            adapter = adapter_for_host(parsed.host, self._user_hosts())
            if adapter is not None:
                name = adapter.project_name(parsed)
                if name:
                    return name
            segs = parsed.segments
            if segs:
                tail = segs[-1]
                if tail.endswith(".git"):
                    tail = tail[:-4]
                return tail or None
        # Scheme-only URL (e.g. file:///path/to/foo.git). Take the basename.
        tail = raw_input.rstrip("/").rsplit("/", 1)[-1]
        if tail.endswith(".git"):
            tail = tail[:-4]
        return tail or None

    def plan(
        self,
        raw_input,
        name: str,
        options: NewOptions,
        ctx: NewContext,
    ) -> NewPlan:
        clone_url = detect_git_url(raw_input, self._user_hosts())
        if not clone_url:
            raise ValueError(f"not a git URL: {raw_input}")
        final_name = resolve_final_name(
            ctx.base_dir,
            name,
            add_date_prefix=options.timestamp,
            add_tmp_suffix=options.tmp,
            ts_name=options.ts_name,
            alpha_name=options.alpha_name,
        )
        target = ctx.base_dir / final_name
        repo_dir = target / "repo"
        steps = [
            f"mkdir {target}",
            f"git clone {clone_url} {repo_dir}",
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
            log_kind="creation",
            log_payload={
                "kind": "git-clone",
                "source": clone_url,
                "repo_dir": str(repo_dir),
            },
            input=raw_input,
            open_shell=options.open,
        )

    def apply(self, plan: NewPlan, ctx: NewContext) -> NewResult:
        target = plan.target
        if target.exists():
            raise ValueError(f"target already exists: {target}")
        clone_url = plan.log_payload["source"]
        repo_dir = target / "repo"
        target.mkdir(parents=True)
        try:
            proc = subprocess.run(
                ["git", "clone", str(clone_url), str(repo_dir)],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                msg = (proc.stderr or proc.stdout or "git clone failed").strip()
                raise ValueError(f"git clone failed: {msg}")
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
