from __future__ import annotations

from pathlib import Path

from homebase.filter import tag_index as tag_index


def test_safe_tag_and_link_component() -> None:
    assert tag_index.safe_tag_component(" api/core ") == "api_core"
    assert tag_index.safe_link_name("x/y") == "x_y"


def test_project_tag_link_name_nested(tmp_path: Path) -> None:
    base = tmp_path / "base"
    proj = base / "team" / "app"
    proj.mkdir(parents=True)
    assert tag_index.project_tag_link_name(base, proj) == "team__app"
