"""Tests for ``ui/actions/wip_actions.py``."""
from __future__ import annotations

from pathlib import Path

from homebase.core.models import ProjectRow
from homebase.ui.actions import wip_actions


def _row(name: str, *, wip: bool = False, archived: bool = False) -> ProjectRow:
    return ProjectRow(
        path=Path(f"/tmp/{name}"),
        name=name,
        branch="-",
        dirty="",
        last="",
        src="fs",
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


class _App:
    def __init__(
        self,
        *,
        selected: ProjectRow | None = None,
        rows: list[ProjectRow] | None = None,
        wip_rows: list[ProjectRow] | None = None,
        view_mode: str = "active",
        pin_wip: bool = False,
    ) -> None:
        self._selected = selected
        self.rows = list(rows or [])
        self._wip_rows = list(wip_rows or [])
        self.view_mode = view_mode
        self._pin_wip = pin_wip
        self.logs: list[tuple[str, str]] = []
        self.runtime_errors: list[tuple[str, Exception]] = []
        self.refresh_side_count = 0
        self.refresh_table_count = 0
        self.refresh_data_count = 0
        self.refresh_selected_details_calls: list[bool] = []
        self.invalidated = 0
        self.touched_rows: list[list[ProjectRow]] = []
        self._restore_apply_scroll = {"active": False, "archive": False}
        self._view_row_offset = {"active": 0, "archive": 0}
        self.opened_wip_indices: list[int] = []

    # ---- app surface used by wip_actions -------------------------

    def _selected_row(self) -> ProjectRow | None:
        return self._selected

    def _wip_rows_sorted(self) -> list[ProjectRow]:
        return self._wip_rows

    def _find_row(self, path: Path):
        for idx, row in enumerate(self.rows):
            if row.path == path:
                return self.rows, idx
        return None

    def _log(self, msg: str, level: str = "info") -> None:
        self.logs.append((msg, level))

    def _refresh_side(self) -> None:
        self.refresh_side_count += 1

    def _refresh_table(self) -> None:
        self.refresh_table_count += 1

    def _refresh_data(self) -> None:
        self.refresh_data_count += 1

    def _show_runtime_error(self, label: str, exc: Exception) -> None:
        self.runtime_errors.append((label, exc))

    def _invalidate_current_rows_cache(self) -> None:
        self.invalidated += 1

    def _touch_rows_cache(self, rows) -> None:
        self.touched_rows.append(list(rows))

    def _table_pin_wip_top_enabled(self) -> bool:
        return self._pin_wip

    def _refresh_selected_details(self, *, log_success: bool = False) -> None:
        self.refresh_selected_details_calls.append(log_success)

    def _open_wip_index(self, idx: int) -> None:
        self.opened_wip_indices.append(idx)


# ---- action_toggle_wip ----------------------------------------------


def test_toggle_wip_skips_when_no_selection() -> None:
    """Toggling WIP without any row selected is a silent no-op —
    refresh_side should not even be called."""
    app = _App()
    wip_actions.action_toggle_wip(
        app, mode_active="active", save_base_wip=lambda _p, _v: None,
    )
    assert app.refresh_side_count == 0
    assert app.logs == []


def test_toggle_wip_blocks_archive_view() -> None:
    row = _row("a", archived=True)
    app = _App(selected=row)
    wip_actions.action_toggle_wip(
        app, mode_active="active", save_base_wip=lambda _p, _v: None,
    )
    assert app.logs == [("wip toggle ignored in archive view", "warn")]
    assert app.refresh_side_count == 1


def test_toggle_wip_enforces_limit_of_nine() -> None:
    """Adding a 10th WIP must be refused — the WIP shelf has nine
    hotbar slots and any more would be unaddressable from the keyboard."""
    row = _row("new")
    existing = [_row(f"w{i}", wip=True) for i in range(9)]
    app = _App(selected=row, wip_rows=existing)
    wip_actions.action_toggle_wip(
        app, mode_active="active", save_base_wip=lambda _p, _v: None,
    )
    assert app.logs == [("wip limit reached (max 9)", "warn")]


def test_toggle_wip_allows_unsetting_even_when_at_limit() -> None:
    """Toggling OFF for a row that's already counted in the limit must
    succeed — limit only gates the off→on transition."""
    row = _row("w0", wip=True)
    app = _App(selected=row, rows=[row], wip_rows=[row] + [_row(f"w{i}", wip=True) for i in range(1, 9)])

    def _save(_path, _value):
        return None

    wip_actions.action_toggle_wip(app, mode_active="active", save_base_wip=_save)
    # Should NOT log the limit warning — the toggle is OFF.
    assert ("wip limit reached (max 9)", "warn") not in app.logs


def test_toggle_wip_updates_row_state_when_save_succeeds() -> None:
    row = _row("a", wip=False)
    app = _App(selected=row, rows=[row])
    saved: list[tuple[Path, bool]] = []
    wip_actions.action_toggle_wip(
        app,
        mode_active="active",
        save_base_wip=lambda p, v: saved.append((p, v)),
    )
    assert saved == [(row.path, True)]
    assert app.rows[0].wip is True
    assert app.touched_rows == [[app.rows[0]]]
    # Side+table refresh both fire.
    assert app.refresh_table_count == 1
    assert app.refresh_side_count >= 1


def test_toggle_wip_logs_state_change() -> None:
    row = _row("alpha", wip=False)
    app = _App(selected=row, rows=[row])
    wip_actions.action_toggle_wip(
        app, mode_active="active", save_base_wip=lambda _p, _v: None,
    )
    assert any("wip enabled: alpha" in m for m, _l in app.logs)


def test_toggle_wip_logs_state_disabled() -> None:
    row = _row("alpha", wip=True)
    app = _App(selected=row, rows=[row], wip_rows=[row])
    wip_actions.action_toggle_wip(
        app, mode_active="active", save_base_wip=lambda _p, _v: None,
    )
    assert any("wip disabled: alpha" in m for m, _l in app.logs)


def test_toggle_wip_surfaces_save_errors() -> None:
    row = _row("a", wip=False)
    app = _App(selected=row, rows=[row])

    def _save(*_a, **_kw):
        raise OSError("disk full")

    wip_actions.action_toggle_wip(
        app, mode_active="active", save_base_wip=_save,
    )
    assert app.runtime_errors and isinstance(app.runtime_errors[0][1], OSError)
    # Row state must not have been mutated.
    assert app.rows[0].wip is False


def test_toggle_wip_falls_back_to_refresh_data_when_row_unknown() -> None:
    """If the row disappears between selection and writeback, fall
    back to a full data refresh rather than touching a stale entry."""
    row = _row("ghost", wip=False)
    app = _App(selected=row, rows=[])
    wip_actions.action_toggle_wip(
        app, mode_active="active", save_base_wip=lambda _p, _v: None,
    )
    assert app.refresh_data_count == 1
    assert app.touched_rows == []


def test_toggle_wip_resets_scroll_when_pinning_to_top() -> None:
    """With ``pin_wip_top`` on, enabling WIP must scroll the table
    back to the top so the new pinned row is visible."""
    row = _row("a", wip=False)
    app = _App(selected=row, rows=[row], pin_wip=True)
    wip_actions.action_toggle_wip(
        app, mode_active="active", save_base_wip=lambda _p, _v: None,
    )
    assert app._restore_apply_scroll["active"] is True
    assert app._view_row_offset["active"] == 0


def test_toggle_wip_skips_scroll_reset_when_pin_disabled() -> None:
    row = _row("a", wip=False)
    app = _App(selected=row, rows=[row], pin_wip=False)
    wip_actions.action_toggle_wip(
        app, mode_active="active", save_base_wip=lambda _p, _v: None,
    )
    assert app._restore_apply_scroll["active"] is False
    assert app._view_row_offset["active"] == 0


# ---- action_refresh_details -----------------------------------------


def test_action_refresh_details_forwards_to_app() -> None:
    app = _App()
    wip_actions.action_refresh_details(app)
    assert app.refresh_selected_details_calls == [True]
    assert app.refresh_side_count == 1


# ---- action_open_wip_index ------------------------------------------


def test_action_open_wip_index_delegates_to_app() -> None:
    app = _App()
    wip_actions.action_open_wip_index(app, 3)
    assert app.opened_wip_indices == [3]
