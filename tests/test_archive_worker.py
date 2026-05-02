from __future__ import annotations

from pathlib import Path

from homebase.core.models import ArchiveActionOutcome
from homebase.ui.actions import archive_worker


class _AppStub:
    def __init__(self) -> None:
        self.action_worker_done = 0
        self.action_worker_current = ""
        self.action_worker_stage = ""
        self.action_worker_command = ""
        self.action_worker_running = True
        self.action_worker_action = "pack"
        self.action_worker_total = 2
        self.action_worker_started_ts = 123
        self.logs: list[tuple[str, str]] = []
        self.removed: list[Path] = []
        self.upserted = 0
        self.cache_refresh_reason = ""
        self.side_refreshed = 0
        self.table_refreshed = 0

    def _refresh_side(self) -> None:
        self.side_refreshed += 1

    def _busy_stop(self) -> None:
        pass

    def _log(self, msg: str, level: str) -> None:
        self.logs.append((level, msg))

    def _remove_paths_local(self, paths: list[Path]) -> None:
        self.removed.extend(paths)

    def _upsert_row_local(self, _row) -> None:
        self.upserted += 1

    def _touch_rows_cache(self, _rows, removed=None) -> None:
        _ = removed

    def _start_cache_refresh(self, reason: str, force: bool = False) -> None:
        _ = force
        self.cache_refresh_reason = reason

    def _refresh_data(self) -> None:
        pass

    def _refresh_table(self) -> None:
        self.table_refreshed += 1

    def _worker_debug(self, _message: str) -> None:
        pass


def test_worker_progress_updates_runtime_fields() -> None:
    app = _AppStub()
    archive_worker.on_archive_action_worker_progress(app, 1, "foo", "packing", "tar")
    assert app.action_worker_done == 1
    assert app.action_worker_current == "foo"
    assert app.action_worker_stage == "packing"
    assert app.action_worker_command == "tar"
    assert app.side_refreshed == 1


def test_worker_done_resets_state_and_logs_summary() -> None:
    app = _AppStub()
    outcome = ArchiveActionOutcome(
        action="pack",
        total=2,
        success=2,
        failed=0,
        removed_paths=[Path("/tmp/a")],
        upsert_rows=[],
        logs=[("info", "packed")],
    )
    archive_worker.on_archive_action_worker_done(app, outcome)
    assert app.action_worker_running is False
    assert app.action_worker_action == ""
    assert app.cache_refresh_reason == "pack update"
    assert any("pack finished" in msg for _lvl, msg in app.logs)
