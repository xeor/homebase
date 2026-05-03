from __future__ import annotations

from pathlib import Path

from homebase.ui.sync import indicator_queries, metadata_health


class _Row:
    def __init__(self, path: Path) -> None:
        self.path = path


class _App:
    def __init__(self) -> None:
        self.fast_exit_requested = False
        self.metadata_health_refresh_running = False
        self.metadata_health_refresh_last_ts = 0.0
        self.metadata_health_refresh_next_due_at = 0.0
        self.metadata_health_cache: dict[Path, tuple[str, float]] = {}
        self.rows = [_Row(Path("/tmp/a")), _Row(Path("/tmp/b")), _Row(Path("/tmp/c"))]
        self.called = 0

    def _critical_job_active(self) -> bool:
        return False

    def _current_rows(self):
        return self.rows

    def _metadata_health_min_interval_s(self) -> float:
        return 0.1

    def _metadata_health_interval_s(self) -> float:
        return 1.0

    def _metadata_health_batch_size(self) -> int:
        return 2

    def _metadata_health_ttl_s(self) -> float:
        return 5.0

    def call_from_thread(self, fn, updated):
        fn(updated)

    def _on_metadata_health_refresh_done(self, updated):
        self.called += len(updated)
        metadata_health.on_metadata_health_refresh_done(self, updated)


def test_maybe_refresh_metadata_health_updates_batch(monkeypatch) -> None:
    app = _App()

    class _ImmediateThread:
        def __init__(self, target, daemon: bool) -> None:
            self._target = target

        def start(self) -> None:
            self._target()

    monkeypatch.setattr(metadata_health.time, "time", lambda: 10.0)
    monkeypatch.setattr(metadata_health.threading, "Thread", _ImmediateThread)
    metadata_health.maybe_refresh_metadata_health(
        app,
        base_meta_health=lambda _path: ("warning", "w"),
    )
    assert app.called == 2
    assert len(app.metadata_health_cache) == 2


def test_indicator_query_metadata_health_uses_cached_level(monkeypatch) -> None:
    row = _Row(Path("/tmp/a"))
    app = _App()
    app.metadata_health_cache[row.path] = ("error", 100.0)
    monkeypatch.setattr(indicator_queries.time, "time", lambda: 10.0)
    assert (
        indicator_queries.evaluate_query_match(
            app,
            row,
            {"type": "metadata_health", "level": "error"},
        )
        is True
    )
