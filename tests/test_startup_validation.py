from __future__ import annotations

from homebase.workspace.startup_validation import run_startup_validations


def test_startup_validation_accepts_year_nested_layout(tmp_path) -> None:
    base = tmp_path / "base"
    year = base / "_archive" / "2026"
    year.mkdir(parents=True)
    (year / "2026-05-11_demo.tgz").write_text("x")
    (year / "2026-05-11_other").mkdir()

    issues = run_startup_validations(base)
    assert issues == []


def test_startup_validation_rejects_flat_entries(tmp_path) -> None:
    base = tmp_path / "base"
    archive = base / "_archive"
    archive.mkdir(parents=True)
    flat = archive / "2026-05-11_demo.tgz"
    flat.write_text("x")

    issues = run_startup_validations(base)
    assert len(issues) == 1
    assert issues[0].key == "archive.layout"
    assert issues[0].path == flat


def test_startup_validation_rejects_zero_segments(tmp_path) -> None:
    base = tmp_path / "base"
    year = base / "_archive" / "2004"
    year.mkdir(parents=True)
    bad = year / "2004-00-00_demo.tgz"
    bad.write_text("x")

    issues = run_startup_validations(base)
    assert len(issues) == 1
    assert issues[0].key == "archive.entry_name"
    assert issues[0].path == bad


def test_startup_validation_rejects_legacy_dot_timestamp(tmp_path) -> None:
    base = tmp_path / "base"
    year = base / "_archive" / "2026"
    year.mkdir(parents=True)
    legacy = year / "demo.2026-05-11T10:20:30+00:00.tgz"
    legacy.write_text("x")

    issues = run_startup_validations(base)
    assert len(issues) == 1
    assert issues[0].key == "archive.entry_name"


def test_startup_validation_rejects_year_mismatch(tmp_path) -> None:
    base = tmp_path / "base"
    year = base / "_archive" / "2025"
    year.mkdir(parents=True)
    bad = year / "2024-01-15_demo"
    bad.mkdir()

    issues = run_startup_validations(base)
    assert len(issues) == 1
    assert issues[0].key == "archive.year_mismatch"
