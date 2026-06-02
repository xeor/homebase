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
        self.metadata_health_cache: dict[Path, tuple[str, str, float]] = {}
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
        base_meta_health=lambda _path: ("warning", "missing field"),
    )
    assert app.called == 2
    assert len(app.metadata_health_cache) == 2
    cached = app.metadata_health_cache[app.rows[0].path]
    assert cached[0] == "warning"
    assert cached[1] == "missing field"


def test_indicator_query_metadata_health_uses_cached_level(monkeypatch) -> None:
    row = _Row(Path("/tmp/a"))
    app = _App()
    app.metadata_health_cache[row.path] = ("error", "broken yaml", 100.0)
    monkeypatch.setattr(indicator_queries.time, "time", lambda: 10.0)
    assert (
        indicator_queries.evaluate_query_match(
            app,
            row,
            {"type": "metadata_health", "level": "error"},
        )
        is True
    )


# ---- additional metadata_health refresh branches --------------------


class _FailThread:
    def __init__(self, *_a, **_kw) -> None:
        raise AssertionError("worker thread should not be started")

    def start(self) -> None:  # pragma: no cover
        raise AssertionError("worker thread should not be started")


def test_skips_when_fast_exit_requested() -> None:
    app = _App()
    app.fast_exit_requested = True
    metadata_health.maybe_refresh_metadata_health(
        app, base_meta_health=lambda _p: ("ok", ""),
    )
    assert app.metadata_health_refresh_running is False


def test_skips_when_critical_job_active() -> None:
    app = _App()
    app._critical_job_active = lambda: True  # type: ignore[method-assign]
    metadata_health.maybe_refresh_metadata_health(
        app, base_meta_health=lambda _p: ("ok", ""),
    )
    assert app.metadata_health_refresh_running is False


def test_skips_when_refresh_already_running() -> None:
    app = _App()
    app.metadata_health_refresh_running = True
    metadata_health.maybe_refresh_metadata_health(
        app, base_meta_health=lambda _p: ("ok", ""),
    )
    # State unchanged — we leave the running flag alone.
    assert app.metadata_health_refresh_running is True


def test_skips_when_next_due_not_reached(monkeypatch) -> None:
    app = _App()
    monkeypatch.setattr(metadata_health.time, "time", lambda: 50.0)
    app.metadata_health_refresh_next_due_at = 100.0
    metadata_health.maybe_refresh_metadata_health(
        app, base_meta_health=lambda _p: ("ok", ""),
    )
    assert app.metadata_health_refresh_running is False


def test_skips_when_within_min_interval(monkeypatch) -> None:
    """A run that just finished must wait for the min interval —
    even if ``next_due_at`` has already elapsed."""
    app = _App()
    monkeypatch.setattr(metadata_health.time, "time", lambda: 10.05)
    app.metadata_health_refresh_last_ts = 10.0
    metadata_health.maybe_refresh_metadata_health(
        app, base_meta_health=lambda _p: ("ok", ""),
    )
    assert app.metadata_health_refresh_running is False


def test_skips_when_no_rows(monkeypatch) -> None:
    app = _App()
    app.rows = []
    monkeypatch.setattr(metadata_health.time, "time", lambda: 10.0)
    metadata_health.maybe_refresh_metadata_health(
        app, base_meta_health=lambda _p: ("ok", ""),
    )
    assert app.metadata_health_refresh_running is False


def test_pushes_next_due_when_nothing_to_refresh(monkeypatch) -> None:
    """If every visible row already has a fresh cache entry, we don't
    spawn a worker — but we advance ``next_due_at`` so the next tick
    doesn't immediately retry."""
    app = _App()
    monkeypatch.setattr(metadata_health.time, "time", lambda: 10.0)
    # Cache every row with a far-future expiry.
    for row in app.rows:
        app.metadata_health_cache[row.path] = ("ok", "", 1_000.0)
    metadata_health.maybe_refresh_metadata_health(
        app, base_meta_health=lambda _p: ("ok", ""),
    )
    assert app.metadata_health_refresh_running is False
    assert app.metadata_health_refresh_next_due_at == 11.0


def test_worker_swallows_probe_exceptions(monkeypatch) -> None:
    app = _App()

    class _ImmediateThread:
        def __init__(self, target, daemon: bool) -> None:
            self._target = target

        def start(self) -> None:
            self._target()

    monkeypatch.setattr(metadata_health.time, "time", lambda: 10.0)
    monkeypatch.setattr(metadata_health.threading, "Thread", _ImmediateThread)

    seen: list[Path] = []

    def _probe(path: Path) -> tuple[str, str]:
        seen.append(path)
        if path.name == "a":
            raise OSError("nope")
        return ("ok", "")

    metadata_health.maybe_refresh_metadata_health(app, base_meta_health=_probe)
    # ``a`` errored out and didn't make it into the cache;
    # ``b`` succeeded.
    assert app.metadata_health_cache.get(Path("/tmp/a")) is None
    assert Path("/tmp/b") in app.metadata_health_cache


def test_on_done_clears_state_when_empty() -> None:
    app = _App()
    app.metadata_health_refresh_running = True
    metadata_health.on_metadata_health_refresh_done(app, [])
    assert app.metadata_health_refresh_running is False
    assert app.metadata_health_cache == {}
