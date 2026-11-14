from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from homebase.herdr import layout


class FakeHerdr:
    """Answers herdr methods from canned results and records every call."""

    def __init__(self, results: dict[str, Any]) -> None:
        self.results = results
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, params))
        value = self.results.get(method, {})
        return value(params) if callable(value) else value


def _split(direction: str, ratio: float, first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    return {"type": "split", "direction": direction, "ratio": ratio, "first": first, "second": second}


def _pane(pane_id: str, cwd: Path, **extra: object) -> dict[str, Any]:
    return {"type": "pane", "pane_id": pane_id, "cwd": str(cwd), **extra}


def test_clean_tab_label() -> None:
    assert layout.clean_tab_label("[2] k9s-nil") == "k9s-nil"
    assert layout.clean_tab_label("[3]") is None
    assert layout.clean_tab_label("4") is None
    assert layout.clean_tab_label("") is None
    assert layout.clean_tab_label("logs") == "logs"


def test_project_root(tmp_path: Path) -> None:
    deep = tmp_path / "proj" / "realms" / "nil"
    deep.mkdir(parents=True)
    assert layout.project_root(deep, tmp_path) == tmp_path.resolve() / "proj"
    assert layout.project_root(tmp_path, tmp_path) is None
    assert layout.project_root(tmp_path.parent, tmp_path) is None


def test_leader_argv() -> None:
    procs = [
        {"pid": 9, "argv": ["python", "runbook.py"]},
        {"pid": 8, "argv": ["task", "@runbook"]},
    ]
    assert layout.leader_argv({"shell_pid": 1, "foreground_process_group_id": 8, "foreground_processes": procs}) == [
        "task",
        "@runbook",
    ]
    assert layout.leader_argv({"shell_pid": 1, "foreground_process_group_id": 1, "foreground_processes": []}) is None
    assert layout.leader_argv({"shell_pid": 1, "foreground_process_group_id": 7, "foreground_processes": procs}) is None


def test_saved_and_apply_node_round_trip(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    tree = _split(
        "down",
        0.434210541,
        _pane("w1:p1", tmp_path, label="agent"),
        _split("right", 0.5, _pane("w1:p2", tmp_path / "sub"), _pane("w1:p3", Path("/elsewhere"))),
    )
    saved = layout.saved_node(tree, tmp_path, {"w1:p2": ["k9s"]})
    assert saved["ratio"] == 0.4342
    assert saved["first"] == {"type": "pane", "cwd": ".", "label": "agent"}
    assert saved["second"]["first"] == {"type": "pane", "cwd": "sub", "command": ["k9s"]}
    assert saved["second"]["second"] == {"type": "pane", "cwd": "/elsewhere"}

    applied = layout.apply_node(saved, tmp_path)
    cwds = [leaf["cwd"] for leaf in layout.leaves(applied)]
    # A missing directory falls back to the project root.
    assert cwds == [str(tmp_path), str(tmp_path / "sub"), str(tmp_path)]
    assert all("command" not in leaf for leaf in layout.leaves(applied))


def test_is_trivial_and_summary() -> None:
    one = {"tabs": [{"root": {"type": "pane", "cwd": "."}}]}
    assert layout.is_trivial(one)
    assert layout.summary(one) == "1 tab, 1 pane"
    busy = {"tabs": [{"root": {"type": "pane", "cwd": ".", "command": ["k9s"]}}]}
    assert not layout.is_trivial(busy)
    two = {"tabs": [one["tabs"][0], one["tabs"][0]]}
    assert not layout.is_trivial(two)
    assert layout.summary(two) == "2 tabs, 2 panes"


def test_validate_rejects_bad_layouts() -> None:
    good = {"version": 1, "tabs": [{"root": {"type": "pane", "cwd": ".", "command": ["k9s"]}}]}
    assert layout.validate(good) is good
    for bad in (
        {"version": 2, "tabs": good["tabs"]},
        {"version": 1, "tabs": []},
        {"version": 1, "tabs": [{"root": {"type": "box"}}]},
        {"version": 1, "tabs": [{"root": {"type": "pane", "command": "k9s"}}]},
        {"version": 1, "tabs": [{"root": _split("up", 0.5, {"type": "pane"}, {"type": "pane"})}]},
    ):
        with pytest.raises(ValueError):
            layout.validate(bad)


def _space(tmp_path: Path) -> FakeHerdr:
    tabs = [
        {"tab_id": "w1:t1", "workspace_id": "w1", "label": "[1]"},
        {"tab_id": "w1:t4", "workspace_id": "w1", "label": "[2] k9s"},
    ]
    panes = [
        {"pane_id": "w1:pB", "tab_id": "w1:t1", "workspace_id": "w1", "cwd": str(tmp_path / "late")},
        {"pane_id": "w1:p2", "tab_id": "w1:t1", "workspace_id": "w1", "cwd": str(tmp_path)},
        {"pane_id": "w1:p3", "tab_id": "w1:t4", "workspace_id": "w1", "cwd": str(tmp_path)},
    ]
    exports = {
        "w1:t1": {"root": _split("right", 0.5, _pane("w1:p2", tmp_path), _pane("w1:pB", tmp_path)),
                  "focused_pane_id": "w1:pB", "zoomed": False},
        "w1:t4": {"root": _pane("w1:p3", tmp_path), "focused_pane_id": "w1:p3", "zoomed": True},
    }
    info = {
        "w1:p3": {"shell_pid": 1, "foreground_process_group_id": 5,
                  "foreground_processes": [{"pid": 5, "argv": ["k9s", "--context", "nil"]}]},
    }
    return FakeHerdr(
        {
            "tab.list": {"tabs": tabs},
            "pane.list": {"panes": panes},
            "workspace.get": {"workspace": {"active_tab_id": "w1:t4"}},
            "layout.export": lambda p: {"layout": exports[p["tab_id"]]},
            "pane.process_info": lambda p: {"process_info": info.get(p["pane_id"], {"shell_pid": 1, "foreground_process_group_id": 1})},
        }
    )


def test_first_pane_cwd_is_oldest_pane_of_first_tab(tmp_path: Path) -> None:
    assert layout.first_pane_cwd("w1", call=_space(tmp_path)) == tmp_path
    assert not layout.is_fresh("w1", call=_space(tmp_path))


def test_export_space(tmp_path: Path) -> None:
    saved = layout.export_space("w1", tmp_path, call=_space(tmp_path))
    assert saved["version"] == 1
    assert saved["project"] == tmp_path.name
    assert saved["focused_tab"] == 1
    first, second = saved["tabs"]
    assert first["label"] is None and first["focused"] == 1 and not first["zoomed"]
    assert second["label"] == "k9s" and second["zoomed"]
    assert second["root"] == {"type": "pane", "cwd": ".", "command": ["k9s", "--context", "nil"]}


def test_apply_space_types_commands_and_restores_focus(tmp_path: Path) -> None:
    saved = {
        "version": 1,
        "focused_tab": 1,
        "tabs": [
            {"label": None, "focused": 1, "zoomed": False,
             "root": _split("right", 0.5, {"type": "pane", "cwd": "."}, {"type": "pane", "cwd": "."})},
            {"label": "k9s", "focused": 0, "zoomed": True,
             "root": {"type": "pane", "cwd": ".", "command": ["k9s", "--context", "my ctx"]}},
        ],
    }
    counter = iter(range(10, 20))

    def apply(params: dict[str, Any]) -> dict[str, Any]:
        def fill(node: dict[str, Any]) -> dict[str, Any]:
            if node["type"] == "split":
                return {**node, "first": fill(node["first"]), "second": fill(node["second"])}
            return {**node, "pane_id": f"w1:p{next(counter)}"}

        return {"layout": {"tab_id": f"w1:t{next(counter)}", "root": fill(params["root"])}}

    fake = FakeHerdr({"layout.apply": apply})
    new_tabs = layout.apply_space(saved, "w1", tmp_path, call=fake)
    assert len(new_tabs) == 2
    methods = [(m, p) for m, p in fake.calls if m != "layout.apply"]
    assert ("pane.send_text", {"pane_id": "w1:p14", "text": "k9s --context 'my ctx'"}) in methods
    assert ("pane.zoom", {"pane_id": "w1:p14", "mode": "on"}) in methods
    focus = [p["pane_id"] for m, p in methods if m == "pane.focus"]
    assert focus == ["w1:p12", "w1:p14", "w1:p14"]
    applies = [p for m, p in fake.calls if m == "layout.apply"]
    assert "tab_label" not in applies[0] and applies[1]["tab_label"] == "k9s"
    assert all(p["workspace_id"] == "w1" and p["focus"] is False for p in applies)
