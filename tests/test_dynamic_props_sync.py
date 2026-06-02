from __future__ import annotations

from pathlib import Path

from homebase.ui.sync import dynamic_props


class _FakeApp:
    def __init__(self, rows: list[object]) -> None:
        self.dynamic_property_refresh_queue: list[Path] = []
        self.dynamic_indicator_cache = {"x": (1.0, set())}
        self.dynamic_indicator_row_cache: dict[tuple[str, Path], tuple[float, bool]] = {}
        self._rows = {row.path: row for row in rows}
        self.refreshed = 0
        self.invalidated = 0
        self.touched: list[Path] = []

    def _find_row(self, path: Path):
        row = self._rows.get(path)
        if row is None:
            return None
        return (list(self._rows.values()), list(self._rows.keys()).index(path))

    def _apply_dynamic_properties_to_row(self, row: object) -> None:
        self.touched.append(row.path)

    def _invalidate_current_rows_cache(self) -> None:
        self.invalidated += 1

    def _refresh_table(self) -> None:
        self.refreshed += 1

    def _refresh_side(self) -> None:
        self.refreshed += 1


class _Row:
    def __init__(self, path: Path) -> None:
        self.path = path


def test_queue_dynamic_property_refresh_deduplicates_and_clears_shared_cache() -> None:
    row_path = Path("/tmp/a")
    app = _FakeApp([_Row(row_path)])
    dynamic_props.queue_dynamic_property_refresh(app, [row_path, row_path])
    assert app.dynamic_property_refresh_queue == [row_path]
    assert app.dynamic_indicator_cache == {}


def test_run_dynamic_property_refresh_tick_processes_chunk() -> None:
    rows = [_Row(Path("/tmp/a")), _Row(Path("/tmp/b"))]
    app = _FakeApp(rows)
    app.dynamic_property_refresh_queue = [rows[0].path, rows[1].path]
    dynamic_props.run_dynamic_property_refresh_tick(app, batch_size=1)
    assert app.dynamic_property_refresh_queue == [rows[1].path]
    assert app.touched == [rows[0].path]
    assert app.invalidated == 1
    assert app.refreshed == 2


def test_queue_dynamic_property_refresh_noop_for_empty_input() -> None:
    """An empty queue request preserves any pre-existing shared cache
    (no spurious invalidation)."""
    app = _FakeApp([])
    app.dynamic_indicator_cache = {"keep": (1.0, set())}
    dynamic_props.queue_dynamic_property_refresh(app, [])
    assert app.dynamic_property_refresh_queue == []
    assert app.dynamic_indicator_cache == {"keep": (1.0, set())}


def test_queue_dynamic_property_refresh_preserves_existing_queue_order() -> None:
    a = Path("/tmp/a")
    b = Path("/tmp/b")
    c = Path("/tmp/c")
    app = _FakeApp([_Row(a), _Row(b), _Row(c)])
    app.dynamic_property_refresh_queue = [a]
    dynamic_props.queue_dynamic_property_refresh(app, [b, a, c])
    # ``a`` was already queued; ``b`` and ``c`` get appended in order.
    assert app.dynamic_property_refresh_queue == [a, b, c]


def test_tick_skips_when_queue_empty() -> None:
    app = _FakeApp([])
    dynamic_props.run_dynamic_property_refresh_tick(app)
    assert app.touched == []
    assert app.refreshed == 0


def test_tick_clamps_negative_batch_size_to_one() -> None:
    rows = [_Row(Path("/tmp/a")), _Row(Path("/tmp/b"))]
    app = _FakeApp(rows)
    app.dynamic_property_refresh_queue = [rows[0].path, rows[1].path]
    dynamic_props.run_dynamic_property_refresh_tick(app, batch_size=0)
    # Floor: at least one is processed even when 0 is passed.
    assert app.dynamic_property_refresh_queue == [rows[1].path]


def test_tick_prunes_only_in_chunk_indicator_entries() -> None:
    a = Path("/tmp/a")
    b = Path("/tmp/b")
    other = Path("/tmp/keep")
    app = _FakeApp([_Row(a), _Row(b)])
    app.dynamic_indicator_row_cache = {
        ("k1", a): (1.0, True),
        ("k2", b): (1.0, True),
        ("k3", other): (1.0, True),
    }
    app.dynamic_property_refresh_queue = [a, b]
    dynamic_props.run_dynamic_property_refresh_tick(app, batch_size=10)
    assert ("k3", other) in app.dynamic_indicator_row_cache
    assert ("k1", a) not in app.dynamic_indicator_row_cache
    assert ("k2", b) not in app.dynamic_indicator_row_cache


def test_tick_no_refresh_when_no_rows_matched() -> None:
    """Only ghost paths in the queue → nothing to refresh → no
    refresh_table/_side calls."""
    app = _FakeApp([])  # zero rows mounted
    app.dynamic_property_refresh_queue = [Path("/tmp/ghost")]
    dynamic_props.run_dynamic_property_refresh_tick(app, batch_size=10)
    assert app.touched == []
    assert app.refreshed == 0
    assert app.invalidated == 0


def test_tick_skips_unknown_paths_but_still_processes_known() -> None:
    """A mix of known + ghost paths: ghost is silently dropped, known
    rows still get applied + a refresh fires."""
    known = Path("/tmp/known")
    app = _FakeApp([_Row(known)])
    app.dynamic_property_refresh_queue = [Path("/tmp/ghost"), known]
    dynamic_props.run_dynamic_property_refresh_tick(app, batch_size=10)
    assert app.touched == [known]
    assert app.refreshed == 2  # table + side
    assert app.invalidated == 1


def test_tick_swallows_widget_api_errors_during_refresh(monkeypatch) -> None:
    """If the table/side widget isn't mounted (e.g. during teardown),
    the table refresh raises ``WIDGET_API_ERRORS`` — the helper must
    swallow it so the tick can finish."""
    p = Path("/tmp/x")
    row = _Row(p)
    app = _FakeApp([row])
    app.dynamic_property_refresh_queue = [p]

    def _boom() -> None:
        raise AttributeError("not mounted")

    monkeypatch.setattr(app, "_refresh_table", _boom)
    # Must not raise.
    dynamic_props.run_dynamic_property_refresh_tick(app)
    assert app.touched == [p]
