from __future__ import annotations

import shlex
from pathlib import Path
from types import SimpleNamespace

from homebase.core.models import Action
from homebase.ui.actions import action_items


class _AppStub:
    def __init__(self) -> None:
        self.ctx = SimpleNamespace(
            actions={
                "hotkey_open_item": Action(
                    id="hotkey_open_item",
                    label="open",
                    kind="shell",
                    scope="target",
                    multi="joined",
                    command="echo ok",
                    source="config",
                )
            }
        )
        self.picked: str | None = None

    def _on_pick_actions(self, value: str | None) -> None:
        self.picked = value


class _RunAppStub:
    def __init__(self, actions: list[dict[str, str]], targets: list[Path]) -> None:
        action_map: dict[str, Action] = {}
        for row in actions:
            cid = str(row.get("id", "")).strip()
            if not cid:
                continue
            action_map[cid] = Action(
                id=cid,
                label=cid,
                kind="shell",
                scope="target",
                multi="per_row" if str(row.get("loop_on_multi", "")).lower() == "true" else "joined",
                command=str(row.get("command", "")),
                source="config",
            )
        self.ctx = SimpleNamespace(actions=action_map)
        self.view_mode = "active"
        self._targets = [SimpleNamespace(path=p, name=p.name, tags=[], properties=[], created="", last="", opened_ts=0, branch="") for p in targets]
        self.logged: list[tuple[str, str]] = []
        self.commands: list[str] = []

    def _target_rows(self):
        return self._targets

    def _log(self, msg: str, level: str) -> None:
        self.logged.append((level, msg))

    def _refresh_side(self) -> None:
        return

    def _show_runtime_error(self, _ctx: str, _exc: Exception) -> None:
        return

    def _mark_row_active(self, _path: Path) -> None:
        return

    def _start_managed_shell_command(
        self,
        command: str,
        *,
        cwd: Path,
        label: str,
        wait: bool,
        terminate_on_quit: bool,
    ) -> None:
        _ = cwd, label, wait, terminate_on_quit
        self.commands.append(command)


def test_custom_action_by_id_reads_from_ctx_actions() -> None:
    app = _AppStub()
    action = action_items.custom_action_by_id(app, "hotkey_open_item")
    assert action is not None
    assert action.id == "hotkey_open_item"


def test_run_custom_action_joins_full_path_when_not_looping() -> None:
    app = _RunAppStub(
        [
            {
                "id": "x",
                "scope": "target",
                "command": "cmd {{ full_path }}",
            }
        ],
        [Path("/tmp/a b"), Path("/tmp/c")],
    )
    action_items.run_custom_action(app, "x", base_dir=Path("/tmp"), fmt_ymd=lambda _x: "")
    assert app.commands == [f"cmd {shlex.quote('/tmp/a b')} {shlex.quote('/tmp/c')}"]


def test_run_custom_action_loops_when_enabled() -> None:
    app = _RunAppStub(
        [
            {
                "id": "x",
                "scope": "target",
                "command": "cmd {{ full_path }}",
                "loop_on_multi": "true",
            }
        ],
        [Path("/tmp/a"), Path("/tmp/b")],
    )
    action_items.run_custom_action(app, "x", base_dir=Path("/tmp"), fmt_ymd=lambda _x: "")
    assert app.commands == ["cmd /tmp/a", "cmd /tmp/b"]
