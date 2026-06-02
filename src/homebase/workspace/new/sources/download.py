from __future__ import annotations

import re
import shutil
import urllib.error
import urllib.request
from pathlib import Path

from ....metadata.api import append_base_log, ensure_base_marker, save_base_tags
from ....workspace.projects import cache_upsert_project_fast
from ..adapters import adapter_for_host, parse_url
from ..base import NewContext, NewOptions, NewPlan, NewResult, Source
from ..name import resolve_final_name
from ..registry import register_source


def _apply_url_rewrites(url: str, rewrites: list[dict]) -> str:
    for entry in rewrites:
        match = entry.get("match")
        rewrite = entry.get("rewrite")
        if not isinstance(match, str) or not isinstance(rewrite, str):
            continue
        try:
            new_url, count = re.subn(match, rewrite, url, count=1)
        except re.error:
            continue
        if count:
            return new_url
    return url


def resolve_download_url(
    raw_input: str,
    user_hosts: dict[str, str],
    rewrites: list[dict],
) -> str:
    parsed = parse_url(raw_input)
    if parsed is not None:
        adapter = adapter_for_host(parsed.host, user_hosts)
        if adapter is not None:
            mapped = adapter.to_download_url(parsed)
            if mapped:
                return mapped
    return _apply_url_rewrites(raw_input, rewrites)


def _filename_from(url: str, response: object) -> str:
    headers = getattr(response, "headers", None)
    if headers is not None:
        disp = headers.get("Content-Disposition") or ""
        m = re.search(r'filename="?([^";]+)"?', disp)
        if m:
            return m.group(1)
    tail = url.rstrip("/").rsplit("/", 1)[-1] or "download"
    return tail.split("?", 1)[0]


@register_source
class DownloadSource(Source):
    key = "download"
    help_short = "Download a URL into a new project."
    default_options = {}
    default_config = {"url_rewrites": []}

    def _user_hosts(self) -> dict[str, str]:
        # GitSource owns the host map; DownloadSource consults it via
        # the resolved config that the dispatcher injected. When called
        # directly (not via cmd.py) the map is empty.
        hosts = self.config.get("hosts") or {}
        if not isinstance(hosts, dict):
            return {}
        return {str(k): str(v) for k, v in hosts.items()}

    def _rewrites(self) -> list[dict]:
        rewrites = self.config.get("url_rewrites") or []
        if not isinstance(rewrites, list):
            return []
        return [r for r in rewrites if isinstance(r, dict)]

    def detects(self, raw_input, ctx: NewContext) -> bool:
        if not raw_input:
            return False
        return parse_url(raw_input) is not None

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
            tail = parsed.segments[-1] if parsed.segments else ""
            if tail:
                stem = Path(tail).stem
                return stem or tail
            return parsed.host or None
        tail = raw_input.rstrip("/").rsplit("/", 1)[-1]
        return Path(tail).stem or tail or None

    def plan(
        self,
        raw_input,
        name: str,
        options: NewOptions,
        ctx: NewContext,
    ) -> NewPlan:
        if not raw_input:
            raise ValueError("download source requires a URL")
        final_name = resolve_final_name(
            ctx.base_dir,
            name,
            add_date_prefix=options.timestamp,
            add_tmp_suffix=options.tmp,
            ts_name=options.ts_name,
            alpha_name=options.alpha_name,
        )
        target = ctx.base_dir / final_name
        resolved_url = resolve_download_url(
            raw_input,
            self._user_hosts(),
            self._rewrites(),
        )
        steps = [
            f"mkdir {target}",
            f"fetch {resolved_url}",
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
                "kind": "download",
                "source": raw_input,
                "resolved_url": resolved_url,
            },
            input=raw_input,
            open_shell=options.open,
        )

    def apply(self, plan: NewPlan, ctx: NewContext) -> NewResult:
        target = plan.target
        if target.exists():
            raise ValueError(f"target already exists: {target}")
        url = plan.log_payload["resolved_url"]
        target.mkdir(parents=True)
        try:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "homebase/b-new"})
                with urllib.request.urlopen(req) as resp:  # noqa: S310 (user URL)
                    filename = _filename_from(url, resp)
                    dest = target / filename
                    with open(dest, "wb") as fh:
                        shutil.copyfileobj(resp, fh)
            except urllib.error.URLError as exc:
                raise ValueError(f"download failed: {exc}") from exc
            ensure_base_marker(target)
            if plan.tags:
                clean = sorted({t.strip() for t in plan.tags if t.strip()})
                if clean:
                    save_base_tags(ctx.base_dir, target, clean)
            payload = dict(plan.log_payload)
            payload["filename"] = filename
            append_base_log(target, plan.log_kind, payload)
        except (OSError, ValueError):
            shutil.rmtree(target, ignore_errors=True)
            raise
        cache_upsert_project_fast(ctx.base_dir, target)
        return NewResult(target=target, open_shell=plan.open_shell)
