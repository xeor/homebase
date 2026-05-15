from __future__ import annotations

from pathlib import Path

from homebase.core.models import ProjectRow
from homebase.ui.actions import item_edits


class _AppStub:
    def __init__(self, src: Path) -> None:
        self.pending_rename_target = src
        self.view_mode = "active"
        self._rows = [
            ProjectRow(
                path=src,
                name=src.name,
                branch="-",
                dirty="",
                last="-",
                src="fs",
                created="-",
                tags=[],
                properties=[],
                description="",
                created_ts=0,
                last_ts=0,
                git_ts=0,
                opened_ts=123,
                is_fork=False,
                is_tmp=False,
                archived=False,
                restore_target=None,
                archived_ts=0,
                wip=False,
                suffix=None,
            )
        ]
        self.multi_selected: set[Path] = set()
        self.selected_path: Path | None = None
        self.moved_opened: tuple[Path, Path] | None = None

    def _find_row(self, path: Path):
        for idx, row in enumerate(self._rows):
            if row.path == path:
                return self._rows, idx
        return None

    def _remove_paths_local(self, paths):
        remove = set(paths)
        self._rows = [row for row in self._rows if row.path not in remove]

    def _move_opened_ts_local(self, src: Path, dst: Path) -> None:
        self.moved_opened = (src, dst)

    def _upsert_row_local(self, row, **_kwargs):
        self._rows.append(row)

    def _same_path(self, a: Path, b: Path) -> bool:
        return a == b

    def _touch_rows_cache(self, *_args, **_kwargs):
        return None

    def _start_cache_refresh(self, *_args, **_kwargs):
        return None

    def _request_tag_sync(self, *_args, **_kwargs):
        return None

    def _refresh_table(self):
        return None

    def _refresh_side(self):
        return None

    def _refresh_data(self):
        return None

    def _log(self, *_args):
        return None


def test_on_rename_item_preserves_opened_ts_and_moves_mapping(tmp_path: Path) -> None:
    src = tmp_path / "alpha"
    src.mkdir()
    app = _AppStub(src)

    def _project_row(target: Path, **kwargs):
        return ProjectRow(
            path=target,
            name=target.name,
            branch="-",
            dirty="",
            last="-",
            src="fs",
            created="-",
            tags=[],
            properties=[],
            description="",
            created_ts=0,
            last_ts=0,
            git_ts=0,
            opened_ts=int(kwargs.get("opened_ts_override", 0)),
            is_fork=False,
            is_tmp=False,
            archived=bool(kwargs.get("archived", False)),
            restore_target=kwargs.get("restore_target"),
            archived_ts=int(kwargs.get("archived_ts", 0)),
            wip=False,
            suffix=None,
        )

    item_edits.on_rename_item(app, "beta", project_row=_project_row)
    assert app.moved_opened == (src, tmp_path / "beta")
    assert len(app._rows) == 1
    assert app._rows[0].opened_ts == 123


def test_on_rename_item_dispatches_post_hook_payload(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "alpha"
    src.mkdir()
    app = _AppStub(src)
    captured: dict[str, object] = {}

    def _project_row(target: Path, **kwargs):
        return ProjectRow(
            path=target,
            name=target.name,
            branch="-",
            dirty="",
            last="-",
            src="fs",
            created="-",
            tags=[],
            properties=[],
            description="",
            created_ts=0,
            last_ts=0,
            git_ts=0,
            opened_ts=int(kwargs.get("opened_ts_override", 0)),
            is_fork=False,
            is_tmp=False,
            archived=bool(kwargs.get("archived", False)),
            restore_target=kwargs.get("restore_target"),
            archived_ts=int(kwargs.get("archived_ts", 0)),
            wip=False,
            suffix=None,
        )

    def _capture_dispatch(app_obj, *, event, targets, change, view):
        captured["event"] = event
        captured["targets"] = targets
        captured["change"] = change
        captured["view"] = view

    monkeypatch.setattr(item_edits.hooks_runtime, "dispatch_post", _capture_dispatch)
    item_edits.on_rename_item(app, "beta", project_row=_project_row)
    assert captured["event"] == "rename"
    assert captured["view"] == "active"
    change = captured["change"]
    assert change["old_name"] == "alpha"
    assert change["new_name"] == "beta"
