from __future__ import annotations

from homebase.commands.help import cmd_help_actions
from homebase.core.models import Action, HotbarEntry, KeyEntry


def test_help_actions_cli_renders_rows(capsys) -> None:
    actions = {
        "archive": Action(
            id="archive",
            label="Archive",
            kind="builtin",
            scope="target",
            multi="joined",
            source="builtin",
        ),
        "open_code": Action(
            id="open_code",
            label="Open Code",
            kind="shell",
            scope="target",
            multi="joined",
            command="code {{ paths_q }}",
            source="config",
        ),
    }
    hotbar = [HotbarEntry(action="archive"), HotbarEntry(action="open_code")]
    keys = {"f5": KeyEntry(action="open_code")}
    rc = cmd_help_actions(actions=actions, hotbar=hotbar, keys=keys)
    out = capsys.readouterr().out
    assert rc == 0
    assert "SOURCE" in out
    assert "archive" in out
    assert "open_code" in out
    assert "hotbar:2" in out
    assert "f5" in out
