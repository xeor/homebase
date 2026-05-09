from __future__ import annotations

import shlex
from pathlib import Path
from types import SimpleNamespace

from homebase.core.models import ProjectRow
from homebase.ui.actions import template


def _row(path: str) -> ProjectRow:
    p = Path(path)
    return ProjectRow(
        path=p,
        name=p.name,
        branch="main",
        dirty="*",
        last="2026-05-10",
        src="fs",
        created="2026-05-01",
        tags=["a", "b"],
        properties=["git"],
        description="desc",
        created_ts=1715299200,
        last_ts=1715385600,
        git_ts=0,
        opened_ts=1715472000,
        is_fork=False,
        is_tmp=False,
        archived=False,
        restore_target=None,
        archived_ts=0,
        wip=True,
        suffix="tmp",
        size_bytes=2048,
    )


def test_template_var_families_resolve() -> None:
    app = SimpleNamespace(
        _resolve_notes_path_for_row=lambda r: r.path / "NOTES.md",
        active_rows=[_row("/p/a")],
        archived_rows=[_row("/p/z")],
        _target_rows=lambda: [_row("/p/a")],
        view_mode="active",
        query="#python",
    )
    base_dir = Path("/p")
    per_row = template.build_per_row_context(app, _row("/p/a"), base_dir)
    listed = template.build_list_context(app, [_row("/p/a"), _row("/p/b")], base_dir)
    always = template.build_always_context(app, base_dir)
    picker = template.build_filepicker_context("/p/a/README.md")

    assert per_row["path"] == "/p/a"
    assert listed["paths"] == "/p/a /p/b"
    assert always["base_dir"] == "/p"
    assert picker["selection"] == "/p/a/README.md"


def test_template_q_quoting_uses_shlex_quote() -> None:
    app = SimpleNamespace(_resolve_notes_path_for_row=lambda r: r.path / "NOTES.md")
    ctx = template.build_per_row_context(app, _row("/tmp/a b"), Path("/tmp"))
    assert ctx["path_q"] == shlex.quote("/tmp/a b")


def test_validate_template_reports_unknown_and_unquoted() -> None:
    allowed = {"path", "path_q"}
    msgs = template.validate_template("cmd {{ path }} {{ bad }} {{ path_q }}", allowed)
    assert "unknown template variable: bad" in msgs
    assert "warning: unquoted template variable in command: path" in msgs


def test_list_context_paths_q_supports_single_and_multiple_rows() -> None:
    app = SimpleNamespace()
    one = template.build_list_context(app, [_row("/p/a")], Path("/p"))
    two = template.build_list_context(app, [_row("/p/a"), _row("/p/b")], Path("/p"))
    assert one["paths_q"] == shlex.quote("/p/a")
    assert two["paths_q"] == f"{shlex.quote('/p/a')} {shlex.quote('/p/b')}"
