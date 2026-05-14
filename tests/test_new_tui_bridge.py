from __future__ import annotations

from pathlib import Path

from homebase.ui.actions.project_create import _payload_to_namespace
from homebase.workspace.new.base import NewContext
from homebase.workspace.new.cmd import plan_and_apply_one
from homebase.workspace.new.config_loader import load_new_sources


def _run_payload(base: Path, payload: dict) -> tuple[int, object, object]:
    ns = _payload_to_namespace(payload)
    raw_input = ns.inputs[0] if ns.inputs else None
    explicit_name = ns.inputs[1] if len(ns.inputs) > 1 else None
    sources_cfg = load_new_sources(base)
    ctx = NewContext(base_dir=base, cwd=base)
    return plan_and_apply_one(ns, raw_input, explicit_name, sources_cfg, ctx)


def test_bridge_creates_empty_project(tmp_path: Path) -> None:
    rc, result, _plan = _run_payload(
        tmp_path,
        {
            "input": "myproj",
            "name": "",
            "source": "auto",
            "tmp": False,
            "timestamp": False,
            "cd": False,
            "confirm": False,
            "archive": False,
            "template": "",
            "tags": [],
        },
    )
    assert rc == 0
    assert result is not None
    assert (tmp_path / "myproj").is_dir()


def test_bridge_with_tmp_and_tags(tmp_path: Path) -> None:
    rc, result, _plan = _run_payload(
        tmp_path,
        {
            "input": "myproj",
            "name": "",
            "source": "auto",
            "tmp": True,
            "timestamp": False,
            "cd": False,
            "confirm": False,
            "archive": False,
            "template": "",
            "tags": ["work", "wip"],
        },
    )
    assert rc == 0
    assert (tmp_path / "myproj.tmp").is_dir()
    text = (tmp_path / "myproj.tmp" / ".base.yaml").read_text()
    assert "work" in text
    assert "wip" in text


def test_bridge_with_explicit_source_override(tmp_path: Path) -> None:
    src = tmp_path / "to-move"
    src.mkdir()
    base = tmp_path / "base"
    base.mkdir()
    rc, result, _plan = _run_payload(
        base,
        {
            "input": str(src),
            "name": "renamed",
            "source": "local",
            "tmp": False,
            "timestamp": False,
            "cd": False,
            "confirm": False,
            "archive": False,
            "template": "",
            "tags": [],
        },
    )
    assert rc == 0
    assert (base / "renamed").is_dir()
    assert not src.exists()


def test_bridge_with_archive_modifier(tmp_path: Path) -> None:
    rc, result, plan = _run_payload(
        tmp_path,
        {
            "input": "myproj",
            "name": "",
            "source": "auto",
            "tmp": False,
            "timestamp": False,
            "cd": False,
            "confirm": False,
            "archive": True,
            "template": "",
            "tags": [],
        },
    )
    assert rc == 0
    archived = list((tmp_path / "_archive").rglob("*_myproj"))
    assert len(archived) == 1
