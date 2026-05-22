from __future__ import annotations

from pathlib import Path

from homebase.workspace import discovery


def _ok_row(path: Path, **_kwargs) -> dict[str, object]:
    return {"path": path, "name": path.name}


def test_collect_projects_skips_failing_row(tmp_path: Path, capsys) -> None:
    (tmp_path / "good_a").mkdir()
    (tmp_path / "bad").mkdir()
    (tmp_path / "good_b").mkdir()

    def _project_row(path: Path, **kwargs):
        if path.name == "bad":
            raise OSError("simulated read failure")
        return _ok_row(path, **kwargs)

    rows = discovery.collect_projects(
        tmp_path,
        include_git_dirty=False,
        include_nested=False,
        size_cache=None,
        archive_dir_name="_archive",
        base_marker_file=".base.yaml",
        resolve_include_nested_fn=lambda _bd, _flag: False,
        skip_active_walk_path=lambda _base, _arch, _cur: False,
        prune_walk_dirnames=lambda _dirs: None,
        project_row=_project_row,
    )
    names = sorted(r["name"] for r in rows)
    assert names == ["good_a", "good_b"]
    err = capsys.readouterr().err
    assert "workspace scan: skipped" in err
    assert "bad" in err


def test_collect_projects_skips_yaml_error(tmp_path: Path, capsys) -> None:
    (tmp_path / "broken").mkdir()
    (tmp_path / "fine").mkdir()

    import yaml

    def _project_row(path: Path, **kwargs):
        if path.name == "broken":
            raise yaml.YAMLError("bad parse")
        return _ok_row(path, **kwargs)

    rows = discovery.collect_projects(
        tmp_path,
        include_git_dirty=False,
        include_nested=False,
        size_cache=None,
        archive_dir_name="_archive",
        base_marker_file=".base.yaml",
        resolve_include_nested_fn=lambda _bd, _flag: False,
        skip_active_walk_path=lambda _base, _arch, _cur: False,
        prune_walk_dirnames=lambda _dirs: None,
        project_row=_project_row,
    )
    assert [r["name"] for r in rows] == ["fine"]
    err = capsys.readouterr().err
    assert "YAMLError" in err


def test_collect_projects_propagates_unexpected_exception(tmp_path: Path) -> None:
    # The safety net is intentionally narrow — programming errors
    # like AttributeError must surface so we notice them in tests
    # / CI instead of silently hiding rows in production.
    (tmp_path / "buggy").mkdir()

    def _project_row(path: Path, **kwargs):
        raise AttributeError("bug")

    import pytest

    with pytest.raises(AttributeError):
        discovery.collect_projects(
            tmp_path,
            include_git_dirty=False,
            include_nested=False,
            size_cache=None,
            archive_dir_name="_archive",
            base_marker_file=".base.yaml",
            resolve_include_nested_fn=lambda _bd, _flag: False,
            skip_active_walk_path=lambda _base, _arch, _cur: False,
            prune_walk_dirnames=lambda _dirs: None,
            project_row=_project_row,
        )


def test_safe_project_row_passes_kwargs_through(tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def _project_row(path: Path, **kwargs):
        seen.update(kwargs)
        return _ok_row(path)

    discovery._safe_project_row(
        _project_row,
        tmp_path / "p",
        include_git_dirty=False,
        prev_size_bytes=42,
        prev_size_refresh_count=7,
    )
    assert seen == {
        "include_git_dirty": False,
        "prev_size_bytes": 42,
        "prev_size_refresh_count": 7,
    }
