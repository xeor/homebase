from __future__ import annotations

from homebase.commands.help import cmd_help_actions
from homebase.core.models import Action


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
    favorites = [
        {"id": "fav_1", "target": "archive", "favorite": True},
        {"id": "fav_2", "target": "open_code", "favorite": True, "hotkey": "f5"},
    ]
    rc = cmd_help_actions(actions=actions, favorites=favorites)
    out = capsys.readouterr().out
    assert rc == 0
    assert "SOURCE" in out
    assert "archive" in out
    assert "open_code" in out
    assert "fav:2" in out
    assert "f5" in out
