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
