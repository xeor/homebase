from __future__ import annotations

from pathlib import Path

from homebase.core.models import ProjectRow
from homebase.ui.query.notes_paths import notes_template_context


class _App:
    view_mode = "archive"


def test_notes_template_context_archived_name_is_date_prefixed() -> None:
    row = ProjectRow(
        path=Path("/tmp/base/_archive/2026/2026-05-11_demo.tgz"),
        name="demo",
        branch="main",
        dirty="",
        last="",
        src="git",
        created="",
        tags=[],
        properties=[],
        description="",
        created_ts=0,
        last_ts=0,
        git_ts=0,
        opened_ts=0,
        is_fork=False,
        is_tmp=False,
        archived=True,
        restore_target=Path("/tmp/base/demo"),
        archived_ts=1_746_921_600,
        wip=False,
        suffix=None,
    )

    context = notes_template_context(
        _App(),
        row,
        base_dir=Path("/tmp/base"),
        fmt_ymd=lambda ts: "2025-05-08" if ts > 0 else "",
    )

    assert context["NAME_WITH_ARCHIVE_PREFIX"] == "_archive/2025/2025-05-08_demo"
