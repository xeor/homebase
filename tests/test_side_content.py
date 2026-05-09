from __future__ import annotations

from pathlib import Path

from homebase.core.models import ProjectRow
from homebase.ui.side import content


def _row(name: str) -> ProjectRow:
    return ProjectRow(
        path=Path(f"/tmp/{name}"),
        name=name,
        branch="main",
        dirty="",
        last="2026-01-01",
        src="git",
        created="2026-01-01",
        tags=[],
        properties=[],
        description="",
        created_ts=1,
        last_ts=1,
        git_ts=1,
        opened_ts=1,
        is_fork=False,
        is_tmp=False,
        archived=False,
        restore_target=None,
        archived_ts=0,
        wip=False,
        suffix=None,
    )


class _AppStub:
    def __init__(self) -> None:
        self.base_dir = Path("/tmp/base")
        self.view_mode = "active"
        self.sort_mode = "last"
        self.query = "tag:demo"
        self.multi_selected = {Path("/tmp/a"), Path("/tmp/b")}
        self.open_pane_count_by_project = {Path("/tmp/a"): 2, Path("/tmp/b"): 1}
        self._rows = [_row("a"), _row("b")]
        self.active_rows = list(self._rows)
        self.archived_rows = []

    def _current_rows(self) -> list[ProjectRow]:
        return self._rows

    def _selected_row(self) -> ProjectRow | None:
        return self._rows[0]

    def _target_rows(self) -> list[ProjectRow]:
        return self._rows

    def _resolve_notes_path_for_row(self, row: ProjectRow) -> Path:
        return row.path / "NOTES.md"

    @staticmethod
    def _esc(value: object) -> str:
        return str(value)


def test_global_info_lines_contains_runtime_overview() -> None:
    app = _AppStub()
    lines = content.global_info_lines(app)
    assert any(line == "view: active" for line in lines)
    assert any(line == "sort: last" for line in lines)
    assert any(line == "rows visible: 2" for line in lines)
    assert any(line == "focused: a" for line in lines)
    assert any(line == "multi-selected: 2" for line in lines)
    assert any(line == "open panes: 3" for line in lines)


def test_global_info_lines_handles_empty_query_and_no_selection() -> None:
    app = _AppStub()
    app.query = "  "
    app._selected_row = lambda: None  # type: ignore[method-assign]
    lines = content.global_info_lines(app)
    assert any(line == "query: -" for line in lines)
    assert any(line == "focused: -" for line in lines)


def test_action_context_lines_contains_groups() -> None:
    app = _AppStub()
    lines = content.action_context_lines(app, base_dir=Path("/tmp"))
    assert any("always" in line for line in lines)
    assert any("per_row" in line for line in lines)
    assert any("joined" in line for line in lines)
    assert any("filepicker" in line for line in lines)
