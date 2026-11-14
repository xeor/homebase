from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

from homebase.commands import herdr_layout as cmd
from homebase.herdr import layout


class FakeHerdr:
    def __init__(self, results: dict[str, Any]) -> None:
        self.results = results
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, params))
        value = self.results.get(method, {})
        return value(params) if callable(value) else value

    def methods(self) -> list[str]:
        return [m for m, _ in self.calls]


SAVED = {
    "version": 1,
    "project": "proj",
    "focused_tab": 0,
    "tabs": [{"label": "k9s", "focused": 0, "zoomed": False,
              "root": {"type": "pane", "cwd": ".", "command": ["k9s"]}}],
}


@pytest.fixture
def base(tmp_path: Path) -> Path:
    (tmp_path / "base" / "proj").mkdir(parents=True)
    return tmp_path / "base"


@pytest.fixture
def herdr_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")
    monkeypatch.setenv("HERDR_WORKSPACE_ID", "w1")
    monkeypatch.setenv("HERDR_TAB_ID", "w1:t1")


def _fresh_space(cwd: Path, *, tabs: int = 1) -> FakeHerdr:
    tab_list = [{"tab_id": f"w1:t{i}", "workspace_id": "w1", "label": str(i)} for i in range(1, tabs + 1)]
    return FakeHerdr(
        {
            "tab.list": {"tabs": tab_list},
            "pane.list": {"panes": [{"pane_id": "w1:p1", "tab_id": "w1:t1", "workspace_id": "w1", "cwd": str(cwd)}]},
            "workspace.get": {"workspace": {"active_tab_id": "w1:t1"}},
            "layout.export": {"layout": {"root": {"type": "pane", "pane_id": "w1:p1", "cwd": str(cwd)},
                                         "focused_pane_id": "w1:p1"}},
            "pane.process_info": {"process_info": {"shell_pid": 1, "foreground_process_group_id": 2,
                                                   "foreground_processes": [{"pid": 2, "argv": ["k9s"]}]}},
            "layout.apply": {"layout": {"tab_id": "w1:t2", "root": {"type": "pane", "pane_id": "w1:p2"}}},
        }
    )


def _write_saved(base: Path) -> Path:
    path = cmd.layout_path(base / "proj")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(SAVED))
    return path


def test_write_layout_keeps_previous_and_skips_unchanged(tmp_path: Path) -> None:
    path = tmp_path / ".base-state" / "herdr-layout.json"
    assert cmd.write_layout(path, SAVED)
    assert not cmd.write_layout(path, SAVED)
    changed = {**SAVED, "focused_tab": 1}
    assert cmd.write_layout(path, changed)
    assert json.loads(path.read_text())["focused_tab"] == 1
    assert json.loads((path.parent / "herdr-layout.prev.json").read_text())["focused_tab"] == 0


def test_save_space_writes_new_project_layout(base: Path, tmp_path: Path) -> None:
    sdir = tmp_path / "st"
    status = cmd.save_space("w1", base, call=_fresh_space(base / "proj"), state_dir=sdir, now=time.time())
    assert status.startswith("saved proj")
    saved = json.loads(cmd.layout_path(base / "proj").read_text())
    assert saved["tabs"][0]["root"]["command"] == ["k9s"]
    # The space that made the file keeps saving it (regression: it skipped itself as "not asked").
    assert cmd.space_state(sdir, "w1") == cmd.STATE_DONE
    fake = _fresh_space(base / "proj")
    fake.results["pane.process_info"] = {"process_info": {"shell_pid": 1, "foreground_process_group_id": 2,
                                                          "foreground_processes": [{"pid": 2, "argv": ["htop"]}]}}
    assert cmd.save_space("w1", base, call=fake, state_dir=sdir, now=time.time()).startswith("saved proj")


def test_save_space_guards(base: Path, tmp_path: Path) -> None:
    sdir = tmp_path / "st"
    now = time.time()
    assert cmd.save_space("w1", base, call=_fresh_space(base), state_dir=sdir, now=now) == "skip: not a project"
    path = _write_saved(base)
    before = path.read_text()
    status = cmd.save_space("w1", base, call=_fresh_space(base / "proj"), state_dir=sdir, now=now)
    assert "not asked yet" in status
    cmd.set_space_state(sdir, "w1", cmd.STATE_LOADING)
    assert cmd.save_space("w1", base, call=_fresh_space(base / "proj"), state_dir=sdir, now=now) == "skip: loading"
    # A stale "loading" (crashed load) no longer blocks saving.
    os.utime(sdir / "w1", (now - 3600, now - 3600))
    assert cmd.save_space("w1", base, call=_fresh_space(base / "proj"), state_dir=sdir, now=now).startswith("saved")
    assert path.read_text() != before


def test_save_space_never_saves_trivial(base: Path, tmp_path: Path) -> None:
    fake = _fresh_space(base / "proj")
    fake.results["pane.process_info"] = {"process_info": {"shell_pid": 1, "foreground_process_group_id": 1}}
    assert cmd.save_space("w1", base, call=fake, state_dir=tmp_path, now=time.time()) == "skip: proj trivial"
    assert not cmd.layout_path(base / "proj").exists()


def test_cmd_herdr_save_all_prunes_states(base: Path, tmp_path: Path) -> None:
    sdir = tmp_path / "st"
    cmd.set_space_state(sdir, "gone", cmd.STATE_DONE)
    fake = _fresh_space(base / "proj")
    fake.results["workspace.list"] = {"workspaces": [{"workspace_id": "w1"}]}
    assert cmd.cmd_herdr_save(base, all_spaces=True, call=fake, state_dir=sdir) == 0
    assert not (sdir / "gone").exists()


def test_load_ask_yes_applies_and_closes_start_tab(base: Path, tmp_path: Path, herdr_env: None) -> None:
    _write_saved(base)
    fake = _fresh_space(base / "proj")
    sdir = tmp_path / "st"
    rc = cmd.cmd_herdr_load(base, str(base / "proj"), ask=True, call=fake, state_dir=sdir,
                            prompt=lambda *_a, **_k: "")
    assert rc == 0
    assert "layout.apply" in fake.methods()
    assert ("pane.send_text", {"pane_id": "w1:p2", "text": "k9s"}) in fake.calls
    assert fake.calls[-1] == ("tab.close", {"tab_id": "w1:t1"})
    assert cmd.space_state(sdir, "w1") == cmd.STATE_DONE


def test_load_ask_no_marks_asked_only(base: Path, tmp_path: Path, herdr_env: None) -> None:
    _write_saved(base)
    fake = _fresh_space(base / "proj")
    sdir = tmp_path / "st"
    rc = cmd.cmd_herdr_load(base, str(base / "proj"), ask=True, call=fake, state_dir=sdir,
                            prompt=lambda *_a, **_k: "n")
    assert rc == 0
    assert "layout.apply" not in fake.methods()
    assert cmd.space_state(sdir, "w1") == cmd.STATE_DONE
    # Asked once: never again for this space.
    prompts: list[str] = []
    cmd.cmd_herdr_load(base, str(base / "proj"), ask=True, call=fake, state_dir=sdir,
                       prompt=lambda *a, **_k: prompts.append(a[0]) or "y")
    assert prompts == []


def test_load_ask_skips_busy_space_without_prompt(base: Path, tmp_path: Path, herdr_env: None) -> None:
    _write_saved(base)
    fake = _fresh_space(base / "proj", tabs=2)
    rc = cmd.cmd_herdr_load(base, str(base / "proj"), ask=True, call=fake, state_dir=tmp_path,
                            prompt=lambda *_a, **_k: pytest.fail("asked in a busy space"))
    assert rc == 0
    assert "layout.apply" not in fake.methods()
    assert cmd.space_state(tmp_path, "w1") == cmd.STATE_DONE


def test_load_explicit_in_busy_space_adds_tabs_keeps_current(base: Path, tmp_path: Path, herdr_env: None) -> None:
    _write_saved(base)
    fake = _fresh_space(base / "proj", tabs=2)
    assert cmd.cmd_herdr_load(base, str(base / "proj"), call=fake, state_dir=tmp_path) == 0
    assert "layout.apply" in fake.methods()
    assert "tab.close" not in fake.methods()


def test_load_errors(base: Path, tmp_path: Path, herdr_env: None, capsys: pytest.CaptureFixture[str]) -> None:
    fake = _fresh_space(base / "proj")
    assert cmd.cmd_herdr_load(base, str(base / "proj"), ask=True, call=fake, state_dir=tmp_path) == 0
    assert cmd.cmd_herdr_load(base, str(base / "proj"), call=fake, state_dir=tmp_path) == 1
    path = _write_saved(base)
    path.write_text('{"version": 9}')
    assert cmd.cmd_herdr_load(base, str(base / "proj"), call=fake, state_dir=tmp_path) == 1
    assert "version 1" in capsys.readouterr().err


def test_load_outside_herdr(base: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HERDR_ENV", raising=False)
    assert cmd.cmd_herdr_load(base, str(base / "proj"), call=FakeHerdr({}), state_dir=tmp_path) == 1


def test_layout_module_used_for_paths(base: Path) -> None:
    assert layout.project_root(base / "proj", base) == base.resolve() / "proj"
