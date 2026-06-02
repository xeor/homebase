"""Tests for ``ui/table/rows_view.py`` — the pure row-list helpers
that back the main project table."""
from __future__ import annotations

from pathlib import Path

from homebase.core.models import ProjectRow
from homebase.ui.table import rows_view


def _row(name: str, *, wip: bool = False, archived: bool = False, tags=None) -> ProjectRow:
    return ProjectRow(
        path=Path(f"/tmp/{name}"),
        name=name,
        branch="-",
        dirty="",
        last="",
        src="fs",
        created="",
        tags=list(tags or []),
        properties=[],
        description="",
        created_ts=0,
        last_ts=0,
        git_ts=0,
        opened_ts=0,
        is_fork=False,
        is_tmp=False,
        archived=archived,
        packed=False,
        pack_format=None,
        restore_target=None,
        archived_ts=0,
        wip=wip,
        suffix=None,
        size_bytes=0,
        size_refresh_count=0,
        worktree_of="",
        repo_dir="",
    )


# ---- all_tags -------------------------------------------------------


class _ViewApp:
    def __init__(self, view_mode: str = "active") -> None:
        self.view_mode = view_mode
        self.active_rows: list[ProjectRow] = []
        self.archived_rows: list[ProjectRow] = []


def test_all_tags_collects_unique_sorted_from_active_rows() -> None:
    app = _ViewApp()
    app.active_rows = [
        _row("a", tags=["x", "z"]),
        _row("b", tags=["y", "x"]),
    ]
    assert rows_view.all_tags(app) == ["x", "y", "z"]


def test_all_tags_uses_archived_when_view_is_archive() -> None:
    app = _ViewApp(view_mode="archive")
    app.active_rows = [_row("a", tags=["never"])]
    app.archived_rows = [_row("z", tags=["archived"])]
    assert rows_view.all_tags(app) == ["archived"]


def test_all_tags_empty_when_no_rows() -> None:
    assert rows_view.all_tags(_ViewApp()) == []


# ---- current_rows ---------------------------------------------------


class _RowsApp:
    def __init__(self) -> None:
        self.view_mode = "active"
        self.sort_mode = "last"
        self.query = ""
        self.active_rows: list[ProjectRow] = []
        self.archived_rows: list[ProjectRow] = []
        self._rows_state_token = 1
        self._rows_cache_token = 0
        self._rows_cache_view = ""
        self._rows_cache_sort = ""
        self._rows_cache_query = ""
        self._rows_cache: list[ProjectRow] = []
        self._rows_index_by_path: dict[Path, int] = {}
        self.query_last_rows_count = 0
        self.pin_wip_top = False

    # ``current_rows`` calls these helpers on the app — stub them.

    def _query_eval(self, expr: str):
        # ``query_expr_mode = False`` → fall back to substring matching.
        return (False, None, None, lambda _row: True, None)

    def _match_query_lower(self, row: ProjectRow, q_lower: str) -> bool:
        return q_lower in row.name.lower()

    def _table_pin_wip_top_enabled(self) -> bool:
        return self.pin_wip_top


def test_current_rows_returns_unfiltered_active_when_no_query() -> None:
    app = _RowsApp()
    app.active_rows = [_row("alpha"), _row("beta")]
    out = rows_view.current_rows(app, mode_active="active")
    assert [r.name for r in out] == ["alpha", "beta"]
    # Cache populated for next call.
    assert app._rows_cache_token == app._rows_state_token


def test_current_rows_caches_when_state_token_matches() -> None:
    """A second call with unchanged state returns the cached list
    object directly rather than re-sorting."""
    app = _RowsApp()
    app.active_rows = [_row("a")]
    first = rows_view.current_rows(app, mode_active="active")
    # Mutate the underlying rows; the cache must shield us until the
    # state token advances.
    app.active_rows = [_row("b")]
    second = rows_view.current_rows(app, mode_active="active")
    assert second is first
    # Bump the token — now the helper recomputes from the new rows.
    app._rows_state_token += 1
    third = rows_view.current_rows(app, mode_active="active")
    assert [r.name for r in third] == ["b"]


def test_current_rows_substring_filter(monkeypatch) -> None:
    app = _RowsApp()
    app.active_rows = [_row("alpha"), _row("beta"), _row("alphabet")]
    app.query = "alpha"
    out = rows_view.current_rows(app, mode_active="active")
    assert sorted(r.name for r in out) == ["alpha", "alphabet"]


def test_current_rows_archive_view_uses_archived_rows() -> None:
    app = _RowsApp()
    app.view_mode = "archive"
    app.archived_rows = [_row("old", archived=True)]
    out = rows_view.current_rows(app, mode_active="active")
    assert [r.name for r in out] == ["old"]


def test_current_rows_pins_wip_to_top_in_active_view() -> None:
    app = _RowsApp()
    app.pin_wip_top = True
    app.active_rows = [
        _row("aaa"),
        _row("bbb", wip=True),
        _row("ccc"),
    ]
    out = rows_view.current_rows(app, mode_active="active")
    # WIP rows come first; the rest preserve their relative order.
    assert [r.name for r in out] == ["bbb", "aaa", "ccc"]


def test_current_rows_pin_wip_disabled_in_archive_view() -> None:
    """The WIP pin only fires in the active view — archive view keeps
    sort order regardless of the flag."""
    app = _RowsApp()
    app.view_mode = "archive"
    app.pin_wip_top = True
    app.archived_rows = [_row("a", archived=True), _row("b", wip=True, archived=True)]
    out = rows_view.current_rows(app, mode_active="active")
    assert [r.name for r in out] == [
        r.name for r in app.archived_rows
    ] or out == app.archived_rows


def test_current_rows_uses_query_predicate_when_expr_mode() -> None:
    """When the query parser returns ``query_expr_mode=True``, the
    helper trusts the predicate rather than substring matching."""
    app = _RowsApp()
    app.active_rows = [_row("alpha"), _row("beta"), _row("gamma")]
    app.query = "anything"
    app._query_eval = lambda _q: (True, None, None, lambda row: row.name.startswith("b"), None)
    out = rows_view.current_rows(app, mode_active="active")
    assert [r.name for r in out] == ["beta"]


def test_current_rows_populates_index_by_path() -> None:
    app = _RowsApp()
    app.active_rows = [_row("a"), _row("b")]
    rows_view.current_rows(app, mode_active="active")
    assert app._rows_index_by_path[Path("/tmp/a")] == 0
    assert app._rows_index_by_path[Path("/tmp/b")] == 1


def test_current_rows_records_query_last_rows_count() -> None:
    app = _RowsApp()
    app.active_rows = [_row("a"), _row("b")]
    rows_view.current_rows(app, mode_active="active")
    assert app.query_last_rows_count == 2


# ---- selected_row ---------------------------------------------------


class _SelectedApp:
    def __init__(self, rows) -> None:
        self.selected_path = None
        self._rows_index_by_path: dict[Path, int] = {row.path: i for i, row in enumerate(rows)}
        self._rows_cache = list(rows)

    def _current_rows(self):
        return self._rows_cache

    def _same_path(self, a: Path, b: Path) -> bool:
        return a == b


def test_selected_row_none_when_no_selection() -> None:
    app = _SelectedApp([_row("a")])
    assert rows_view.selected_row(app) is None


def test_selected_row_uses_path_index() -> None:
    rows = [_row("a"), _row("b")]
    app = _SelectedApp(rows)
    app.selected_path = rows[1].path
    assert rows_view.selected_row(app) is rows[1]


def test_selected_row_falls_back_to_linear_scan_and_caches() -> None:
    """When the cached index is stale (path not in the dict), the
    helper scans for the row and refreshes the index."""
    rows = [_row("a"), _row("b")]
    app = _SelectedApp(rows)
    # Drop the index entry to force the fallback.
    app._rows_index_by_path.pop(rows[1].path)
    app.selected_path = rows[1].path
    assert rows_view.selected_row(app) is rows[1]
    # Fallback path repopulates the index.
    assert app._rows_index_by_path[rows[1].path] == 1


def test_selected_row_returns_none_when_path_unknown() -> None:
    app = _SelectedApp([_row("a")])
    app.selected_path = Path("/tmp/missing")
    assert rows_view.selected_row(app) is None


# ---- target_rows ----------------------------------------------------


class _TargetsApp:
    def __init__(self, rows) -> None:
        self._rows_cache = list(rows)
        self.multi_selected: set[Path] = set()
        self.selected_row_obj = None

    def _current_rows(self):
        return self._rows_cache

    def _selected_row(self):
        return self.selected_row_obj


def test_target_rows_returns_multi_selection_when_set() -> None:
    rows = [_row("a"), _row("b"), _row("c")]
    app = _TargetsApp(rows)
    app.multi_selected = {rows[0].path, rows[2].path}
    out = rows_view.target_rows(app)
    assert {r.name for r in out} == {"a", "c"}


def test_target_rows_falls_back_to_selected_row() -> None:
    rows = [_row("a")]
    app = _TargetsApp(rows)
    app.selected_row_obj = rows[0]
    assert rows_view.target_rows(app) == [rows[0]]


def test_target_rows_empty_when_no_selection() -> None:
    app = _TargetsApp([_row("a")])
    assert rows_view.target_rows(app) == []


# ---- wip_rows_sorted ------------------------------------------------


def test_wip_rows_sorted_case_insensitive_name_order() -> None:
    app = _ViewApp()
    app.active_rows = [
        _row("Charlie", wip=True),
        _row("alpha", wip=True),
        _row("Bravo", wip=False),
        _row("bravo-wip", wip=True),
    ]
    out = rows_view.wip_rows_sorted(app)
    assert [r.name for r in out] == ["alpha", "bravo-wip", "Charlie"]


def test_wip_rows_sorted_excludes_archived_rows() -> None:
    """Only the active rows are scanned; archived rows are never
    surfaced as WIP — they would have lost the bit on archive."""
    app = _ViewApp()
    app.archived_rows = [_row("archived", wip=True, archived=True)]
    assert rows_view.wip_rows_sorted(app) == []
