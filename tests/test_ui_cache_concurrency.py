from __future__ import annotations

from types import SimpleNamespace

from homebase.cache import concurrency as cache_conc_mod
from homebase.ui.sync import cache_concurrency as ui_cc


class FakeBanner:
    def __init__(self) -> None:
        self.text: str = ""
        self.classes: set[str] = set()

    def update(self, text: str) -> None:
        self.text = text

    def add_class(self, name: str) -> None:
        self.classes.add(name)

    def remove_class(self, name: str) -> None:
        self.classes.discard(name)


def _make_app(banner: FakeBanner | None = None, **overrides: object) -> SimpleNamespace:
    banner = banner if banner is not None else FakeBanner()
    app = SimpleNamespace(
        cache_concurrency_drift_seen=0,
        cache_concurrency_dismissed=False,
        cache_concurrency_last_event=None,
        log_calls=[],
    )

    def query_one(_sel: str, _cls: type):
        if app.__dict__.get("_raise"):
            raise RuntimeError("missing")
        return banner

    app.query_one = query_one
    app._log_error_counted = lambda key, msg, level="info": app.log_calls.append(
        (key, msg, level)
    )
    for k, v in overrides.items():
        setattr(app, k, v)
    app._banner = banner
    return app


def test_paint_banner_clears_when_no_drift() -> None:
    app = _make_app()
    ui_cc.paint_banner(app)
    assert app._banner.text == ""
    assert "visible" not in app._banner.classes


def test_paint_banner_renders_message_when_drift_present() -> None:
    event = cache_conc_mod.CacheConcurrencyEvent(
        ts=0, expected_version=5, observed_version=3, kind="older_present", detail="x"
    )
    app = _make_app(
        cache_concurrency_drift_seen=2,
        cache_concurrency_last_event=event,
    )
    ui_cc.paint_banner(app)
    assert "cache schema drift detected" in app._banner.text
    assert "visible" in app._banner.classes


def test_paint_banner_skips_when_query_one_fails() -> None:
    app = _make_app()
    app.__dict__["_raise"] = True
    ui_cc.paint_banner(app)  # must not raise


def test_paint_banner_hides_when_dismissed() -> None:
    event = cache_conc_mod.CacheConcurrencyEvent(
        ts=0, expected_version=5, observed_version=3, kind="older_present", detail="x"
    )
    app = _make_app(
        cache_concurrency_drift_seen=2,
        cache_concurrency_last_event=event,
        cache_concurrency_dismissed=True,
    )
    ui_cc.paint_banner(app)
    assert app._banner.text == ""


def test_dismiss_sets_flag_and_repaints() -> None:
    event = cache_conc_mod.CacheConcurrencyEvent(
        ts=0, expected_version=5, observed_version=3, kind="older_present", detail="x"
    )
    app = _make_app(
        cache_concurrency_drift_seen=1,
        cache_concurrency_last_event=event,
    )
    ui_cc.paint_banner(app)
    assert "visible" in app._banner.classes
    ui_cc.dismiss(app)
    assert app.cache_concurrency_dismissed is True
    assert "visible" not in app._banner.classes


def test_check_cache_concurrency_updates_state_on_new_drift(monkeypatch) -> None:
    event = cache_conc_mod.CacheConcurrencyEvent(
        ts=int(__import__("time").time()),
        expected_version=5,
        observed_version=3,
        kind="older_present",
        detail="boom",
    )

    class FakeSnap:
        drift_count = 3
        last_event = event

    monkeypatch.setattr(cache_conc_mod, "snapshot", lambda: FakeSnap())
    app = _make_app(cache_concurrency_drift_seen=2)
    ui_cc.check_cache_concurrency(app)
    assert app.cache_concurrency_drift_seen == 3
    assert app.cache_concurrency_dismissed is False
    assert app.log_calls
    assert app.log_calls[0][0] == "cache_concurrency"


def test_check_cache_concurrency_noop_when_no_new_drift(monkeypatch) -> None:
    class FakeSnap:
        drift_count = 1
        last_event = None

    monkeypatch.setattr(cache_conc_mod, "snapshot", lambda: FakeSnap())
    app = _make_app(cache_concurrency_drift_seen=1)
    ui_cc.check_cache_concurrency(app)
    assert app.log_calls == []
