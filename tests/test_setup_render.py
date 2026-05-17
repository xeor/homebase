from __future__ import annotations

from homebase.core import setup_render
from homebase.core.setup_model import (
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_WARN,
    SetupCheck,
    SetupSummary,
)


def test_format_status_label_plain_when_not_tty(monkeypatch) -> None:
    monkeypatch.setattr(setup_render.sys.stdout, "isatty", lambda: False)
    assert setup_render.format_status_label("PASS") == "PASS"


def test_format_status_label_colored_when_tty(monkeypatch) -> None:
    monkeypatch.setattr(setup_render.sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    out = setup_render.format_status_label("WARN")
    assert "\x1b[33m" in out
    assert "WARN" in out


def test_format_status_label_respects_no_color(monkeypatch) -> None:
    monkeypatch.setattr(setup_render.sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("NO_COLOR", "1")
    assert setup_render.format_status_label("FAIL") == "FAIL"


def test_format_check_row_includes_name_and_detail(monkeypatch) -> None:
    monkeypatch.setattr(setup_render.sys.stdout, "isatty", lambda: False)
    check = SetupCheck(id="x", name="uv", status=STATUS_PASS, detail="/usr/bin/uv")
    row = setup_render.format_check_row(check)
    assert "uv" in row
    assert "/usr/bin/uv" in row
    assert "PASS" in row


def test_render_checks_prints_each_row_and_extras(monkeypatch, capsys) -> None:
    monkeypatch.setattr(setup_render.sys.stdout, "isatty", lambda: False)
    checks = [
        SetupCheck(id="a", name="a", status=STATUS_PASS, detail="ok"),
        SetupCheck(
            id="b",
            name="b",
            status=STATUS_WARN,
            detail="needs fix",
            extra_lines=("  hint: foo",),
        ),
    ]
    setup_render.render_checks(checks)
    out = capsys.readouterr().out
    assert "a: ok" in out
    assert "b: needs fix" in out
    assert "hint: foo" in out


def test_render_summary_marks_ready_when_no_hard_fail(monkeypatch, capsys) -> None:
    monkeypatch.setattr(setup_render.sys.stdout, "isatty", lambda: False)
    summary = SetupSummary(
        pass_count=3, warn_count=1, fail_count=0, hard_fail=False,
    )
    setup_render.render_summary(summary)
    out = capsys.readouterr().out
    assert "setup: ready" in out
    assert "PASS=3 WARN=1 FAIL=0" in out


def test_render_summary_marks_incomplete_when_hard_fail(monkeypatch, capsys) -> None:
    monkeypatch.setattr(setup_render.sys.stdout, "isatty", lambda: False)
    summary = SetupSummary(
        pass_count=1, warn_count=0, fail_count=1, hard_fail=True,
    )
    setup_render.render_summary(summary)
    out = capsys.readouterr().out
    assert "setup: incomplete" in out
    assert STATUS_FAIL in out or "FAIL" in out
