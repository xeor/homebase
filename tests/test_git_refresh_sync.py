from __future__ import annotations

from pathlib import Path

from homebase.ui.sync import git_refresh


class _Row:
    def __init__(self, i: int) -> None:
        self.path = Path(f"/tmp/p{i}")
        self.branch = "main"
        self.dirty = "~"


class _App:
    def __init__(self) -> None:
        self.fast_exit_requested = False
        self.git_refresh_running = False
        self.cache_worker_running = False
        self.git_refresh_last_ts = 0.0
        self.git_refresh_next_due_at = 0.0
        self.selected = None
        self.rows = [_Row(i) for i in range(20)]
        self.started: list[Path] = []

    def _critical_job_active(self) -> bool:
        return False

    def _current_rows(self):
        return self.rows

    def _selected_row(self):
        return self.selected

    def _start_git_refresh(self, paths: list[Path], reason: str) -> None:
        self.started = paths

    def _git_refresh_min_interval_s(self) -> float:
        return 0.1

    def _git_refresh_batch_size(self) -> int:
        return 3


def test_maybe_refresh_visible_git_uses_profile_batch_size(monkeypatch) -> None:
    app = _App()
    monkeypatch.setattr(git_refresh.time, "time", lambda: 10.0)
    git_refresh.maybe_refresh_visible_git(app)
    assert len(app.started) == 3


def test_maybe_refresh_visible_git_respects_next_due(monkeypatch) -> None:
    app = _App()
    app.git_refresh_next_due_at = 11.0
    monkeypatch.setattr(git_refresh.time, "time", lambda: 10.0)
    git_refresh.maybe_refresh_visible_git(app)
    assert app.started == []
