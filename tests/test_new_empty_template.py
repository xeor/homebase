"""Tests for the private ``_apply_template`` helper in
``workspace/new/sources/empty.py``."""
from __future__ import annotations

from pathlib import Path

import pytest

from homebase.workspace.new.sources import empty as empty_source


def test_apply_template_missing_dir_raises(tmp_path: Path) -> None:
    """A template key with no matching directory under ``.copier/``
    must fail loudly so the caller doesn't silently produce an empty
    project."""
    base = tmp_path / "base"
    base.mkdir()
    target = tmp_path / "out"
    target.mkdir()
    with pytest.raises(ValueError, match="template not found"):
        empty_source._apply_template(base, "nope", target)


def test_apply_template_with_copier_yml_invokes_copier(
    tmp_path: Path, monkeypatch,
) -> None:
    base = tmp_path / "base"
    template_dir = base / ".copier" / "py"
    template_dir.mkdir(parents=True)
    (template_dir / "copier.yml").write_text("_min_copier_version: 9.0\n")
    target = tmp_path / "out"
    target.mkdir()

    monkeypatch.setattr(empty_source.shutil, "which", lambda _binary: "/usr/local/bin/copier")
    captured: list[list[str]] = []

    class _Proc:
        returncode = 0

    def fake_run(cmd, **_kwargs):
        captured.append(list(cmd))
        return _Proc()

    monkeypatch.setattr(empty_source.subprocess, "run", fake_run)
    empty_source._apply_template(base, "py", target)
    assert captured, "expected copier to be invoked"
    assert captured[0][:2] == ["copier", "copy"]
    assert str(template_dir) in captured[0]
    assert str(target) in captured[0]


def test_apply_template_copier_yaml_extension_also_detected(
    tmp_path: Path, monkeypatch,
) -> None:
    """Copier supports both ``copier.yml`` and ``copier.yaml`` —
    either should trigger the copier invocation."""
    base = tmp_path / "base"
    template_dir = base / ".copier" / "rs"
    template_dir.mkdir(parents=True)
    (template_dir / "copier.yaml").write_text("_min_copier_version: 9.0\n")
    target = tmp_path / "out"
    target.mkdir()
    monkeypatch.setattr(empty_source.shutil, "which", lambda _binary: "/usr/local/bin/copier")
    invoked = {"n": 0}

    def fake_run(*_a, **_kw):
        invoked["n"] += 1

        class _Proc:
            returncode = 0
        return _Proc()

    monkeypatch.setattr(empty_source.subprocess, "run", fake_run)
    empty_source._apply_template(base, "rs", target)
    assert invoked["n"] == 1


def test_apply_template_fails_when_copier_not_installed(
    tmp_path: Path, monkeypatch,
) -> None:
    base = tmp_path / "base"
    template_dir = base / ".copier" / "py"
    template_dir.mkdir(parents=True)
    (template_dir / "copier.yml").write_text("_min_copier_version: 9.0\n")
    target = tmp_path / "out"
    target.mkdir()
    monkeypatch.setattr(empty_source.shutil, "which", lambda _binary: None)
    with pytest.raises(ValueError, match="copier is not installed"):
        empty_source._apply_template(base, "py", target)


def test_apply_template_translates_copier_failure(
    tmp_path: Path, monkeypatch,
) -> None:
    base = tmp_path / "base"
    template_dir = base / ".copier" / "py"
    template_dir.mkdir(parents=True)
    (template_dir / "copier.yml").write_text("_min_copier_version: 9.0\n")
    target = tmp_path / "out"
    target.mkdir()
    monkeypatch.setattr(empty_source.shutil, "which", lambda _binary: "/usr/local/bin/copier")

    def fail_run(*_a, **_kw):
        raise empty_source.subprocess.CalledProcessError(returncode=2, cmd=["copier"])

    monkeypatch.setattr(empty_source.subprocess, "run", fail_run)
    with pytest.raises(ValueError, match=r"copier failed: exit 2"):
        empty_source._apply_template(base, "py", target)


def test_apply_template_falls_back_to_directory_scaffold(
    tmp_path: Path,
) -> None:
    """When a template directory has no ``copier.*`` manifest it's
    treated as a plain directory tree and copied via
    ``scaffold_template_directory``."""
    base = tmp_path / "base"
    template_dir = base / ".copier" / "plain"
    template_dir.mkdir(parents=True)
    (template_dir / "README.md").write_text("# template")
    (template_dir / "src").mkdir()
    (template_dir / "src" / "main.py").write_text("print('hi')\n")
    target = tmp_path / "out"
    target.mkdir()

    empty_source._apply_template(base, "plain", target)
    assert (target / "README.md").read_text() == "# template"
    assert (target / "src" / "main.py").read_text() == "print('hi')\n"
