from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from homebase.ui.sync import worktree_health
from homebase.workspace.health import WorktreeIssue


class _Banner:
    def __init__(self) -> None:
        self.text = ""
        self.classes: set[str] = set()

    def update(self, text: str) -> None:
        self.text = text

    def add_class(self, name: str) -> None:
        self.classes.add(name)

    def remove_class(self, name: str) -> None:
        self.classes.discard(name)


class _RecordedScreen:
    def __init__(self, kind: str, *args, **kwargs) -> None:
        self.kind = kind
        self.args = args
        self.kwargs = kwargs


def _confirm_cls_factory():
    def make(title: str, details: str) -> _RecordedScreen:
        return _RecordedScreen("confirm", title=title, details=details)
    return make


def _result_cls_factory():
    def make(title: str, summary: str, details: str, *, level: str = "info") -> _RecordedScreen:
        return _RecordedScreen(
            "result", title=title, summary=summary, details=details, level=level
        )
    return make


def _make_app(tmp_path: Path) -> SimpleNamespace:
    banner = _Banner()
    app = SimpleNamespace(
        base_dir=tmp_path,
        worktree_health_issues=[],
        worktree_health_last_scan_ts=0,
        worktree_health_dismissed=False,
        logs=[],
        notified=[],
        pushed=[],
        _banner=banner,
        _confirm_screen_cls=_confirm_cls_factory(),
        _result_screen_cls=_result_cls_factory(),
    )

    def _log(msg: str, level: str = "info") -> None:
        app.logs.append((level, msg))

    def _query_one(selector: str, _typ):
        if selector == "#worktree_health_banner":
            return banner
        raise LookupError(selector)

    def _push_screen(screen, cb=None):
        app.pushed.append((screen, cb))

    def _notify(text: str, *, severity: str = "information") -> None:
        app.notified.append((severity, text))

    app._log = _log
    app.query_one = _query_one
    app.push_screen = _push_screen
    app.notify = _notify
    return app


def _issue(path: str, kind: str = "orphan_admin") -> WorktreeIssue:
    return WorktreeIssue(
        path=Path(path),
        kind=kind,
        detail="auto-detected drift",
        fix_summary="git worktree prune",
        parent_path=Path("/tmp/parent"),
    )


def test_clean_workspace_shows_result_modal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _make_app(tmp_path)
    monkeypatch.setattr(worktree_health, "audit_workspace", lambda _bd: [])

    worktree_health.action_fix_worktrees(app)

    assert any(lvl == "info" and "clean" in msg for lvl, msg in app.logs)
    result_screens = [s for s, _ in app.pushed if isinstance(s, _RecordedScreen) and s.kind == "result"]
    assert len(result_screens) == 1
    assert "nothing to do" in result_screens[0].kwargs["title"]
    assert app.notified  # toast


def test_issues_present_pushes_confirm_with_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _make_app(tmp_path)
    issues = [_issue("/p/a"), _issue("/p/b", kind="stale_gitdir")]
    monkeypatch.setattr(worktree_health, "audit_workspace", lambda _bd: list(issues))

    worktree_health.action_fix_worktrees(app)

    assert len(app.pushed) == 1
    screen, _cb = app.pushed[0]
    assert isinstance(screen, _RecordedScreen) and screen.kind == "confirm"
    assert "2 issue" in screen.kwargs["title"]
    assert "orphan_admin" in screen.kwargs["details"]
    assert "stale_gitdir" in screen.kwargs["details"]
    assert "/p/a" in screen.kwargs["details"]
    assert "git worktree prune" in screen.kwargs["details"]


def test_confirm_cancel_logs_and_skips_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _make_app(tmp_path)
    monkeypatch.setattr(worktree_health, "audit_workspace", lambda _bd: [_issue("/p/a")])

    def _repair_should_not_run(_i: Any) -> tuple[bool, str]:
        raise AssertionError("repair_issue must not be called when cancelled")

    monkeypatch.setattr(worktree_health, "repair_issue", _repair_should_not_run)

    worktree_health.action_fix_worktrees(app)
    _, cb = app.pushed[0]
    cb(False)

    assert any(lvl == "warn" and "cancelled" in msg for lvl, msg in app.logs)
    # No result modal pushed on cancel.
    result_screens = [s for s, _ in app.pushed if isinstance(s, _RecordedScreen) and s.kind == "result"]
    assert result_screens == []


def test_confirm_accept_runs_repair_and_pushes_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _make_app(tmp_path)
    issues = [_issue("/p/a"), _issue("/p/b", kind="stale_gitdir")]
    # First audit returns issues; second audit (after fix) returns clean.
    audits = iter([list(issues), []])
    monkeypatch.setattr(worktree_health, "audit_workspace", lambda _bd: next(audits))
    monkeypatch.setattr(
        worktree_health, "repair_issue", lambda _i: (True, "repaired")
    )
    monkeypatch.setattr(
        worktree_health, "cache_save_worktree_health", lambda *_a, **_k: None
    )

    worktree_health.action_fix_worktrees(app)
    _, cb = app.pushed[0]
    cb(True)

    result_screens = [s for s, _ in app.pushed if isinstance(s, _RecordedScreen) and s.kind == "result"]
    assert len(result_screens) == 1
    result = result_screens[0]
    assert "2 applied" in result.kwargs["title"]
    assert "0 failed" in result.kwargs["title"]
    assert result.kwargs["level"] == "info"
    assert app.notified
    assert app.notified[-1][0] == "information"


def test_repair_failure_marks_result_as_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _make_app(tmp_path)
    issues = [_issue("/p/a"), _issue("/p/b", kind="stale_gitdir")]
    audits = iter([list(issues), list(issues[:1])])
    monkeypatch.setattr(worktree_health, "audit_workspace", lambda _bd: next(audits))
    outcomes = iter([(True, "ok"), (False, "git missing")])
    monkeypatch.setattr(worktree_health, "repair_issue", lambda _i: next(outcomes))
    monkeypatch.setattr(
        worktree_health, "cache_save_worktree_health", lambda *_a, **_k: None
    )

    worktree_health.action_fix_worktrees(app)
    _, cb = app.pushed[0]
    cb(True)

    result = [s for s, _ in app.pushed if isinstance(s, _RecordedScreen) and s.kind == "result"][0]
    assert "1 applied" in result.kwargs["title"]
    assert "1 failed" in result.kwargs["title"]
    assert result.kwargs["level"] == "warn"
    assert "git missing" in result.kwargs["details"]
    assert app.notified[-1][0] == "warning"
