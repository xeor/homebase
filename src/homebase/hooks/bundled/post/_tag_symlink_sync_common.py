from __future__ import annotations

from ....metadata.api import sync_tag_symlinks
from ...api import HookContext


def run_tag_symlink_sync(ctx: HookContext) -> None:
    err = sync_tag_symlinks(ctx.base_dir)
    if err is not None:
        ctx.notify(f"tag symlink sync failed: {err}", "warn")
        ctx.log(f"tag symlink sync failed: {err}", "warn")
        return
    ctx.notify("tag symlink sync complete", "info")
