from __future__ import annotations

from types import SimpleNamespace

from homebase.ui.screens.guard import confirm_destructive


def _fake_app():
    pushed: list[tuple[object, object]] = []
    app = SimpleNamespace(pushed=pushed)
    app.push_screen = lambda screen, callback: pushed.append((screen, callback))
    return app


def test_confirm_destructive_pushes_a_confirm_screen() -> None:
    app = _fake_app()
    confirm_destructive(
        app,
        title="Reset?",
        details="losing data",
        on_yes=lambda: None,
    )
    assert len(app.pushed) == 1
    screen, _ = app.pushed[0]
    assert getattr(screen, "title", None) == "Reset?"
    assert "losing data" in getattr(screen, "details", "")


def test_confirm_destructive_runs_on_yes_when_accepted() -> None:
    app = _fake_app()
    yes_called = []
    no_called = []
    confirm_destructive(
        app,
        title="t",
        on_yes=lambda: yes_called.append(True),
        on_no=lambda: no_called.append(True),
    )
    _screen, callback = app.pushed[0]
    callback(True)
    assert yes_called == [True]
    assert no_called == []


def test_confirm_destructive_runs_on_no_when_declined() -> None:
    app = _fake_app()
    yes_called = []
    no_called = []
    confirm_destructive(
        app,
        title="t",
        on_yes=lambda: yes_called.append(True),
        on_no=lambda: no_called.append(True),
    )
    _screen, callback = app.pushed[0]
    callback(False)
    assert yes_called == []
    assert no_called == [True]


def test_confirm_destructive_silent_when_no_no_handler() -> None:
    app = _fake_app()
    confirm_destructive(
        app,
        title="t",
        on_yes=lambda: None,
    )
    _screen, callback = app.pushed[0]
    callback(False)
    callback(None)
    # No exceptions raised; nothing else to assert — silence on
    # decline is the documented behaviour.
