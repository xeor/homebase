from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from homebase.core.models import PaneRef
from homebase.herdr import panes
from homebase.herdr.client import HerdrError


class FakeHerdr:
    """Answers herdr methods from canned results and records every call."""

    def __init__(self, results: dict[str, Any] | None = None) -> None:
        self.results = results or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, params))
        value = self.results.get(method, {})
        if isinstance(value, Exception):
            raise value
        return value(params) if callable(value) else value


def _pane(pane_id: str, cwd: Path, **extra: object) -> dict[str, object]:
    ws, _, num = pane_id.partition(":p")
    return {"pane_id": pane_id, "workspace_id": ws, "tab_id": f"{ws}:t1", "cwd": str(cwd), **extra}


def _ref(pane_id: str, cwd: Path, window: str = "ws") -> PaneRef:
    return PaneRef(
        pane_id=pane_id, target=pane_id, window_name=window, command="fish",
        cwd=cwd, active=False, source="herdr",
    )


def test_pane_command_prefers_agent_then_group_leader() -> None:
    procs = [{"pid": 1, "argv0": "caffeinate"}, {"pid": 2, "argv0": "/usr/bin/nvim"}]
    info = {"foreground_process_group_id": 2, "foreground_processes": procs}
    assert panes.pane_command({"agent": "claude"}, info) == "claude"
    assert panes.pane_command({}, info) == "nvim"
    assert panes.pane_command({}, {"foreground_processes": [{"name": "-fish"}]}) == "fish"
    assert panes.pane_command({}, {}) == ""


def test_pane_target_is_tmux_style() -> None:
    assert panes.pane_target({"workspace_id": "w4", "tab_id": "w4:t2", "pane_id": "w4:p7"}) == "w4:2.7"
    assert panes.pane_target({"workspace_id": "w4", "tab_id": "odd", "pane_id": "w4:p7"}) == "w4:odd.7"


def test_list_panes(tmp_path: Path) -> None:
    fake = FakeHerdr(
        {
            "workspace.list": {"workspaces": [{"workspace_id": "w1", "label": "proj"}, "junk"]},
            "pane.list": {
                "panes": [
                    _pane("w1:p1", tmp_path, foreground_cwd=str(tmp_path / "sub")),
                    _pane("w2:p3", tmp_path, focused=True),
                    {"pane_id": "", "cwd": "/x"},
                    "junk",
                ]
            },
            "pane.process_info": lambda p: (
                {"process_info": {"foreground_processes": [{"argv0": "nvim"}]}}
                if p["pane_id"] == "w1:p1"
                else {}
            ),
        }
    )
    out = panes.list_panes(call=fake)
    assert [(p.pane_id, p.window_name, p.command, p.active) for p in out] == [
        ("w2:p3", "w2", "", True),
        ("w1:p1", "proj", "nvim", False),
    ]
    assert out[1].cwd == tmp_path / "sub"
    assert out[1].target == "w1:1.1"
    assert all(p.source == "herdr" for p in out)


def test_list_panes_survives_process_info_errors(tmp_path: Path) -> None:
    fake = FakeHerdr(
        {"pane.list": {"panes": [_pane("w1:p1", tmp_path)]}, "pane.process_info": HerdrError("gone")}
    )
    [pane] = panes.list_panes(call=fake)
    assert pane.command == ""


def test_find_panes_for_cwd(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    (proj / "sub").mkdir(parents=True)
    other = tmp_path / "other"
    other.mkdir()
    inside = _ref("w1:p1", proj / "sub")
    named = _ref("w2:p1", other, window="proj")
    assert panes.find_panes_for_cwd(proj, [named, inside]) == [inside]
    assert panes.find_panes_for_cwd(proj, [named]) == [named]
    assert panes.find_panes_for_cwd(proj, [_ref("w3:p1", other)]) == []


def test_open_new_tab_uses_current_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeHerdr({"tab.create": {"root_pane": {"pane_id": "w1:p9"}}})
    assert panes.open_new(tmp_path, "tab", call=fake) == "w1:p9"
    assert fake.calls[-1] == ("tab.create", {"cwd": str(tmp_path), "label": tmp_path.name, "focus": True})
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")
    monkeypatch.setenv("HERDR_WORKSPACE_ID", "w1")
    panes.open_new(tmp_path, "tab", call=fake)
    assert fake.calls[-1][1]["workspace_id"] == "w1"


def test_open_new_workspace(tmp_path: Path) -> None:
    fake = FakeHerdr({"workspace.create": {"root_pane": "odd"}})
    assert panes.open_new(tmp_path, "workspace", call=fake) == ""
    assert fake.calls == [
        ("workspace.create", {"cwd": str(tmp_path), "label": tmp_path.name, "focus": True})
    ]


def _listing(*items: tuple[str, Path]) -> dict[str, Any]:
    return {"pane.list": {"panes": [_pane(pid, cwd) for pid, cwd in items]}}


def test_goto_candidates_skip_own_pane(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeHerdr(_listing(("w1:p1", tmp_path), ("w1:p2", tmp_path)))
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")
    assert [p.pane_id for p in panes.goto_candidates(tmp_path, call=fake)] == ["w1:p2"]


def _never_cd(_path: Path) -> int:
    raise AssertionError("must not cd")


def test_open_with_mode_goes_to_existing_pane(tmp_path: Path) -> None:
    fake = FakeHerdr(_listing(("w1:p2", tmp_path)))
    spec = {"goto_loaded": True, "herdr_new": "workspace"}
    assert panes.open_with_mode(tmp_path, spec, open_shell_in_dir=_never_cd, call=fake, available=lambda: True) == 0
    assert fake.calls[-1] == ("pane.focus", {"pane_id": "w1:p2"})


def test_open_with_mode_opens_new_when_nothing_matches(tmp_path: Path) -> None:
    fake = FakeHerdr(_listing())
    spec = {"goto_loaded": True, "herdr_new": "workspace"}
    assert panes.open_with_mode(tmp_path, spec, open_shell_in_dir=_never_cd, call=fake, available=lambda: True) == 0
    assert fake.calls[-1][0] == "workspace.create"


def test_open_with_mode_reports_herdr_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeHerdr({"tab.create": HerdrError("herdr tab.create: boom")})
    assert panes.open_with_mode(tmp_path, {}, open_shell_in_dir=_never_cd, call=fake, available=lambda: True) == 1
    assert "boom" in capsys.readouterr().err


def test_open_with_mode_without_herdr(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cds: list[Path] = []
    assert panes.open_with_mode(tmp_path, {}, open_shell_in_dir=lambda p: cds.append(p) or 0) == 0
    assert cds == [tmp_path]
    spec = {"fallback_cd": False}
    assert panes.open_with_mode(tmp_path, spec, open_shell_in_dir=_never_cd, available=lambda: False) == 1
    assert "running herdr" in capsys.readouterr().err
