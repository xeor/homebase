from __future__ import annotations

from homebase.ui.app_display import AppDisplayMixin


class _FakeSize:
    def __init__(self, width: int) -> None:
        self.width = width


class _FakeDataTable:
    def __init__(self, width: int = 120) -> None:
        self.size = _FakeSize(width)
        self.cell_padding = 1
        self.clear_calls = 0
        self.columns: list[tuple[str, int | None]] = []

    def clear(self, *, columns: bool = False) -> None:
        self.clear_calls += 1
        if columns:
            self.columns = []

    def add_column(self, label: str, width: int | None = None) -> None:
        self.columns.append((label, width))


class _FakeDisplay(AppDisplayMixin):
    def __init__(self) -> None:
        self.view_mode = "active"
        self._table = _FakeDataTable()
        self._visible_column_effective_width_by_id: dict[str, int] = {}
        self._table_column_signature_by_view: dict[str, tuple[object, ...]] = {}

    def query_one(self, _selector: str, _typ: object = None) -> _FakeDataTable:
        return self._table

    def _table_visible_columns_for_view(self, _view: str) -> list[dict[str, object]]:
        return [
            {"id": "name", "label": "NAME", "enabled": True, "width": 20},
            {"id": "git", "label": "GIT", "enabled": True, "width": 14},
        ]

    def _table_columns_for_view(self, _view: str) -> list[dict[str, object]]:
        return self._table_visible_columns_for_view(_view)


def test_configure_table_columns_skips_clear_when_signature_unchanged() -> None:
    app = _FakeDisplay()
    app._configure_table_columns()
    first_clear_calls = app._table.clear_calls
    assert first_clear_calls == 1

    app._configure_table_columns()
    assert app._table.clear_calls == first_clear_calls
