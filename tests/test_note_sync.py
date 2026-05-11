from __future__ import annotations

from pathlib import Path

from homebase.core.models import ProjectRow
from homebase.ui.actions.note_sync import build_note_sync_command


class _App:
    def _notes_template_context(self, row: ProjectRow) -> dict[str, str]:
        if row.archived:
            return {"NAME_WITH_ARCHIVE_PREFIX": "_archive/2026-05-11_demo"}
        return {"NAME_WITH_ARCHIVE_PREFIX": "demo"}


def _row(*, archived: bool) -> ProjectRow:
    return ProjectRow(
        path=Path("/tmp/base/demo"),
        name="demo",
        branch="",
        dirty="",
        last="",
        src="",
        created="",
        tags=[],
        properties=[],
        description="",
        created_ts=0,
        last_ts=0,
        git_ts=0,
        opened_ts=0,
        is_fork=False,
        is_tmp=False,
        archived=archived,
        restore_target=None,
        archived_ts=0,
        wip=False,
        suffix=None,
    )


def test_build_note_sync_command_uses_archive_prefixed_new_note_name() -> None:
    cmd = build_note_sync_command(
        _App(),
        source_row=_row(archived=False),
        target_row=_row(archived=True),
        old_note_path=Path("/notes/demo.md"),
        new_note_path=Path("/notes/_archive/2026-05-11_demo.md"),
        command_template='obsidian rename path="notes/{{ OLD_NOTE_FILE }}" name="{{ NEW_NOTE_NAME }}"',
    )
    assert cmd.endswith('name="_archive/2026-05-11_demo"')


def test_build_note_sync_command_uses_archive_prefixed_old_note_file_on_restore() -> None:
    cmd = build_note_sync_command(
        _App(),
        source_row=_row(archived=True),
        target_row=_row(archived=False),
        old_note_path=Path("/notes/_archive/2026-05-11_demo.md"),
        new_note_path=Path("/notes/demo.md"),
        command_template='obsidian rename path="notes/{{ OLD_NOTE_FILE }}" name="{{ NEW_NOTE_NAME }}"',
    )
    assert 'path="notes/_archive/2026-05-11_demo.md"' in cmd
    assert cmd.endswith('name="../demo.md"')
