from __future__ import annotations

from pathlib import Path

from homebase.core.models import ProjectRow
from homebase.ui.table.render import _tag_color, refresh_table


class _FakeSize:
    width = 120


class _FakeRowKey:
    def __init__(self, value: str) -> None:
        self.value = value


class _FakeDataTable:
    def __init__(self) -> None:
        self.scroll_x = 0
        self.scroll_y = 0
        self.row_count = 0
        self.cursor_row = 0
        self.fixed_rows = 0
        self.cell_padding = 1
        self.size = _FakeSize()
        self.cursor_coordinate = (0, 0)
        self._rows: list[tuple[str, list[object]]] = []
        self.clear_calls = 0
        self.update_calls = 0

    def clear(self, *, columns: bool = False) -> None:
        self.clear_calls += 1
        self._rows = []
        self.row_count = 0

    def add_row(self, *values: object, key: str) -> None:
        self._rows.append((key, list(values)))
        self.row_count = len(self._rows)

    def coordinate_to_cell_key(self, coord: tuple[int, int]) -> tuple[_FakeRowKey, object]:
        row, _col = coord
        return _FakeRowKey(self._rows[row][0]), object()

    def update_cell_at(self, coord: tuple[int, int], value: object) -> None:
        row, col = coord
        self._rows[row][1][col] = value
        self.update_calls += 1

    def scroll_to(self, *, x: int, y: int, animate: bool = False) -> None:
        self.scroll_x = x
        self.scroll_y = y


def _row(path: Path, name: str, description: str = "") -> ProjectRow:
    return ProjectRow(
        path=path,
        name=name,
        branch="main",
        dirty="",
        last="-",
        src="fs",
        created="-",
        tags=[],
        properties=[],
        description=description,
        created_ts=0,
        last_ts=0,
        git_ts=0,
        opened_ts=0,
        is_fork=False,
        is_tmp=False,
        archived=False,
        restore_target=None,
        archived_ts=0,
        wip=False,
        suffix=None,
    )


class _FakeApp:
    def __init__(self, rows: list[ProjectRow]) -> None:
        self._rows = rows
        self._table = _FakeDataTable()
        self._table_render_signature: tuple[object, ...] | None = None
        self._property_cell_cache: dict[tuple[str, ...], object] = {}
        self._property_cell_cache_sig: int = -1
        self.view_mode = "active"
        self.multi_selected: set[Path] = set()
        self.pending_tag_updates: set[Path] = set()
        self.git_refresh_paths: set[Path] = set()
        self.open_pane_count_by_project: dict[Path, int] = {}
        self.open_pane_overflow_projects: set[Path] = set()
        self._busy_frame_index = 0
        self._busy_frames = [".", "o"]
        self._restore_pending = {"active": False, "archive": False}
        self._restore_apply_scroll = {"active": False, "archive": False}
        self._view_row_offset = {"active": 0, "archive": 0}
        self._suspend_project_row_highlight = False
        self.selected_path: Path | None = rows[0].path if rows else None
        self._view_selected_path = {"active": self.selected_path, "archive": None}
        self._restore_target_path = {"active": self.selected_path, "archive": None}
        self._state_cursor_row = 0
        self.cache_last_refresh_ts = 1
        self.cache_worker_running = False

    def query_one(self, _selector: str, _typ: object = None) -> _FakeDataTable:
        return self._table

    def _current_rows(self) -> list[ProjectRow]:
        return self._rows

    def _table_visible_columns_for_view(self, _view: str) -> list[dict[str, object]]:
        return [{"id": "name", "label": "NAME", "enabled": True, "width": 20}]

    def _wip_rows_sorted(self) -> list[ProjectRow]:
        return []

    def _table_pin_wip_top_enabled(self) -> bool:
        return False

    def _same_path(self, a: Path | None, b: Path | None) -> bool:
        return a == b

    def _clear_project_row_highlight_suspend(self) -> None:
        self._suspend_project_row_highlight = False

    def call_after_refresh(self, cb) -> None:
        cb()


def _run_refresh(app: _FakeApp) -> None:
    refresh_table(
        app,
        widget_projects="#projects",
        mode_active="active",
        base_dir=Path("/tmp"),
        color_error_hex="#f00",
        color_success_hex="#0f0",
        color_archive_hex="#666",
        color_accent_hex="#0ff",
        color_warn_hex="#ff0",
        color_interactive_hex="#00f",
        fmt_ymd=lambda _x: "-",
        fmt_size_human=lambda _x: "0B",
        property_tokens_text=lambda _x: "",
    )


def test_refresh_table_skips_noop_rebuild() -> None:
    app = _FakeApp([_row(Path("/tmp/a"), "a")])
    _run_refresh(app)
    assert app._table.clear_calls == 1

    _run_refresh(app)
    assert app._table.clear_calls == 1


def test_render_signature_ignores_busy_frame_when_no_rows_refreshing() -> None:
    app = _FakeApp([_row(Path("/tmp/a"), "a")])
    _run_refresh(app)
    sig_quiet = app._table_render_signature

    app._busy_frame_index = (app._busy_frame_index + 1) % len(app._busy_frames)
    _run_refresh(app)
    assert app._table_render_signature == sig_quiet

    app.git_refresh_paths = {Path("/tmp/a")}
    _run_refresh(app)
    sig_refreshing = app._table_render_signature
    assert sig_refreshing != sig_quiet

    app._busy_frame_index = (app._busy_frame_index + 1) % len(app._busy_frames)
    _run_refresh(app)
    assert app._table_render_signature != sig_refreshing


def test_property_cell_cache_persists_across_renders_and_clears_on_sig_change() -> None:
    row_a = _row(Path("/tmp/a"), "a")
    row_a.properties = ["act", "doc"]
    app = _FakeApp([row_a])

    calls: list[tuple[str, ...]] = []

    def _tokens(props: list[str]) -> str:
        calls.append(tuple(props))
        return "+".join(props) or "-"

    def _refresh(sig: int) -> None:
        refresh_table(
            app,
            widget_projects="#projects",
            mode_active="active",
            base_dir=Path("/tmp"),
            color_error_hex="#f00",
            color_success_hex="#0f0",
            color_archive_hex="#666",
            color_accent_hex="#0ff",
            color_warn_hex="#ff0",
            color_interactive_hex="#00f",
            fmt_ymd=lambda _x: "-",
            fmt_size_human=lambda _x: "0B",
            property_tokens_text=_tokens,
            property_defs_signature=sig,
        )

    _refresh(7)
    first_calls = len(calls)
    assert first_calls == 1

    app._table_render_signature = None
    _refresh(7)
    assert len(calls) == first_calls

    app._table_render_signature = None
    _refresh(8)
    assert len(calls) == first_calls + 1


def test_tag_color_is_deterministic_and_cached() -> None:
    _tag_color.cache_clear()
    color_a = _tag_color("cli")
    color_b = _tag_color("cli")
    color_c = _tag_color("web")
    assert color_a == color_b
    assert color_a != color_c
    info = _tag_color.cache_info()
    assert info.hits >= 1


def test_refresh_table_updates_cells_in_place_when_row_keys_match() -> None:
    app = _FakeApp([_row(Path("/tmp/a"), "a", description="one")])
    _run_refresh(app)
    assert app._table.clear_calls == 1

    app._rows[0].description = "two"
    _run_refresh(app)

    assert app._table.clear_calls == 1
    assert app._table.update_calls > 0
