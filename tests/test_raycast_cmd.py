from __future__ import annotations

import json
from pathlib import Path

from homebase.commands import raycast
from homebase.core.models import Action, ProjectRow


def _row(base_dir: Path, name: str = "alpha") -> ProjectRow:
    return ProjectRow(
        path=base_dir / name,
        name=name,
        branch="main",
        dirty="-",
        last="",
        src="",
        created="",
        tags=["work"],
        properties=[],
        description="",
        created_ts=0,
        last_ts=0,
        git_ts=0,
        opened_ts=0,
        is_fork=False,
        is_tmp=False,
        archived=False,
        restore_target=None,
        archived_ts=0,
        wip=False,
        suffix=None,
    )


def _load_rows(row: ProjectRow):
    return lambda _base_dir: ([row], [], 0)


def test_cmd_actions_lists_only_raycast_enabled_supported_actions(
    tmp_path: Path,
    capsys,
) -> None:
    row = _row(tmp_path)
    actions = {
        "open_gui": Action(
            id="open_gui",
            label="Open GUI",
            kind="shell",
            scope="target",
            multi="joined",
            command="open {{ path_q }}",
            source="config",
            raycast={"enabled": True, "title": "Open in GUI"},
        ),
        "disabled_gui": Action(
            id="disabled_gui",
            label="Disabled GUI",
            kind="shell",
            scope="target",
            multi="joined",
            command="open {{ path_q }}",
            source="config",
        ),
        "notes_create": Action(
            id="notes_create",
            label="Create Note",
            kind="builtin",
            scope="target",
            multi="joined",
            raycast={"enabled": True},
        ),
        "notes_open": Action(
            id="notes_open",
            label="Open Note",
            kind="builtin",
            scope="target",
            multi="joined",
            raycast={"enabled": True},
        ),
    }

    rc = raycast.cmd_actions(
        tmp_path,
        "alpha",
        actions=actions,
        load_rows=_load_rows(row),
        notes_config={"path_template": "notes/{{ name }}.md"},
    )

    assert rc == 0
    assert json.loads(capsys.readouterr().out) == [
        {"id": "open_gui", "title": "Open in GUI"},
        {"id": "notes_create", "title": "Create Note"},
    ]


def test_cmd_actions_without_project_lists_all_projects(tmp_path: Path, capsys) -> None:
    alpha = _row(tmp_path, "alpha")
    beta = _row(tmp_path, "beta")
    actions = {
        "open_gui": Action(
            id="open_gui",
            label="Open GUI",
            kind="shell",
            scope="target",
            multi="joined",
            command="open {{ path_q }}",
            source="config",
            raycast={"enabled": True},
        )
    }

    rc = raycast.cmd_actions(
        tmp_path,
        "",
        actions=actions,
        load_rows=lambda _base_dir: ([alpha, beta], [], 0),
        notes_config={"path_template": "notes/{{ name }}.md"},
    )

    assert rc == 0
    assert json.loads(capsys.readouterr().out) == [
        {"project": "alpha", "actions": [{"id": "open_gui", "title": "Open GUI"}]},
        {"project": "beta", "actions": [{"id": "open_gui", "title": "Open GUI"}]},
    ]


def test_cmd_actions_uses_notes_open_when_note_exists(tmp_path: Path, capsys) -> None:
    row = _row(tmp_path)
    note_path = tmp_path / "notes" / "alpha.md"
    note_path.parent.mkdir()
    note_path.write_text("# alpha\n", encoding="utf-8")
    actions = {
        "notes_create": Action(
            id="notes_create",
            label="Create Note",
            kind="builtin",
            scope="target",
            multi="joined",
            raycast={"enabled": True},
        ),
        "notes_open": Action(
            id="notes_open",
            label="Open Note",
            kind="builtin",
            scope="target",
            multi="joined",
            raycast={"enabled": True},
        ),
    }

    rc = raycast.cmd_actions(
        tmp_path,
        "alpha",
        actions=actions,
        load_rows=_load_rows(row),
        notes_config={"path_template": "notes/{{ name }}.md"},
    )

    assert rc == 0
    assert json.loads(capsys.readouterr().out) == [
        {"id": "notes_open", "title": "Open Note"},
    ]


def test_cmd_actions_does_not_open_existing_note_unless_enabled(
    tmp_path: Path,
    capsys,
) -> None:
    row = _row(tmp_path)
    note_path = tmp_path / "notes" / "alpha.md"
    note_path.parent.mkdir()
    note_path.write_text("# alpha\n", encoding="utf-8")
    actions = {
        "notes_create": Action(
            id="notes_create",
            label="Create Note",
            kind="builtin",
            scope="target",
            multi="joined",
            raycast={"enabled": True},
        ),
        "notes_open": Action(
            id="notes_open",
            label="Open Note",
            kind="builtin",
            scope="target",
            multi="joined",
        ),
    }

    rc = raycast.cmd_actions(
        tmp_path,
        "alpha",
        actions=actions,
        load_rows=_load_rows(row),
        notes_config={"path_template": "notes/{{ name }}.md"},
    )

    assert rc == 0
    assert json.loads(capsys.readouterr().out) == []


def test_cmd_run_renders_enabled_notes_open_action(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    row = _row(tmp_path)
    note_path = tmp_path / "notes" / "alpha.md"
    note_path.parent.mkdir()
    note_path.write_text("# alpha\n", encoding="utf-8")
    actions = {
        "notes_open": Action(
            id="notes_open",
            label="Open Note",
            kind="builtin",
            scope="target",
            multi="joined",
            raycast={"enabled": True},
        ),
    }
    calls: list[tuple[list[str], str]] = []

    def fake_popen(argv, *, cwd):
        calls.append((argv, cwd))
        return object()

    monkeypatch.setattr(raycast.subprocess, "Popen", fake_popen)

    rc = raycast.cmd_run(
        tmp_path,
        "alpha",
        "notes_open",
        actions=actions,
        load_rows=_load_rows(row),
        notes_config={
            "path_template": "notes/{{ name }}.md",
            "open_command": "open {{ NOTE_PATH_Q }}",
        },
        open_project=lambda _base_dir, _project: 99,
    )

    assert rc == 0
    expected = f"open {note_path}"
    assert calls == [(["/bin/sh", "-lc", expected], str(tmp_path))]
    assert capsys.readouterr().out.strip() == expected


def test_cmd_run_renders_enabled_shell_action(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    row = _row(tmp_path)
    actions = {
        "open_gui": Action(
            id="open_gui",
            label="Open GUI",
            kind="shell",
            scope="target",
            multi="joined",
            command="open {{ path_q }}",
            source="config",
            raycast={"enabled": True},
        )
    }
    calls: list[tuple[list[str], str]] = []

    def fake_popen(argv, *, cwd):
        calls.append((argv, cwd))
        return object()

    monkeypatch.setattr(raycast.subprocess, "Popen", fake_popen)

    rc = raycast.cmd_run(
        tmp_path,
        "alpha",
        "open_gui",
        actions=actions,
        load_rows=_load_rows(row),
        notes_config={"path_template": "notes/{{ name }}.md"},
        open_project=lambda _base_dir, _project: 99,
    )

    assert rc == 0
    expected = f"open {tmp_path / 'alpha'}"
    assert calls == [(["/bin/sh", "-lc", expected], str(tmp_path))]
    assert capsys.readouterr().out.strip() == expected


def test_cmd_run_rejects_disabled_action(tmp_path: Path, capsys) -> None:
    row = _row(tmp_path)
    actions = {
        "open_gui": Action(
            id="open_gui",
            label="Open GUI",
            kind="shell",
            scope="target",
            multi="joined",
            command="open {{ path_q }}",
            source="config",
        )
    }

    rc = raycast.cmd_run(
        tmp_path,
        "alpha",
        "open_gui",
        actions=actions,
        load_rows=_load_rows(row),
        notes_config={"path_template": "notes/{{ name }}.md"},
        open_project=lambda _base_dir, _project: 0,
    )

    assert rc == 2
    assert "unsupported or disabled action" in capsys.readouterr().err
