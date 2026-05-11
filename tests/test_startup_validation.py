from __future__ import annotations

from homebase.workspace.startup_validation import run_startup_validations


def test_startup_validation_accepts_new_packed_archive_names(tmp_path) -> None:
    base = tmp_path / "base"
    archive = base / "_archive"
    archive.mkdir(parents=True)
    (archive / "2026-05-11_demo.tgz").write_text("x")

    issues = run_startup_validations(base)
    assert issues == []


def test_startup_validation_rejects_legacy_packed_archive_names(tmp_path) -> None:
    base = tmp_path / "base"
    archive = base / "_archive"
    archive.mkdir(parents=True)
    legacy = archive / "demo.2026-05-11T10:20:30+00:00.base-pkg.tgz"
    legacy.write_text("x")

    issues = run_startup_validations(base)
    assert len(issues) == 1
    assert issues[0].key == "archive.packed_name"
    assert issues[0].path == legacy


def test_startup_validation_accepts_relaxed_date_pattern(tmp_path) -> None:
    base = tmp_path / "base"
    archive = base / "_archive"
    archive.mkdir(parents=True)
    relaxed = archive / "2004-00-00_demo.tgz"
    relaxed.write_text("x")

    issues = run_startup_validations(base)
    assert issues == []


def test_startup_validation_ignores_nested_paths(tmp_path) -> None:
    base = tmp_path / "base"
    nested = base / "_archive" / "a"
    nested.mkdir(parents=True)
    (nested / "not-a-valid-name.tgz").write_text("x")
    deep = nested / "b"
    deep.mkdir(parents=True)
    (deep / "also-invalid.tgz").write_text("x")

    issues = run_startup_validations(base)
    assert issues == []
