from __future__ import annotations

from pathlib import Path

from homebase.core.models import PreOutcome, ProjectRow
from homebase.ui.actions import tag_actions


class _App:
    def __init__(self, path: Path) -> None:
        self.view_mode = "active"
        self.pending_tag_updates: set[Path] = set()
        self.logs: list[tuple[str, str]] = []
        self.active_rows = [
            ProjectRow(
                path=path,
                name=path.name,
                branch="-",
                dirty="",
                last="-",
                src="fs",
                created="-",
                tags=["old"],
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
        ]
        self.archived_rows: list[ProjectRow] = []

    def _find_row(self, path: Path):
        for idx, row in enumerate(self.active_rows):
            if row.path == path:
                return self.active_rows, idx
        return None

    def _busy_start(self, _msg: str) -> None:
        return None

    def _busy_tick(self) -> None:
        return None

    def _busy_stop(self) -> None:
        return None

    def _log(self, msg: str, level: str = "info") -> None:
        self.logs.append((level, msg))

    def _refresh_table(self) -> None:
        return None

    def _refresh_side(self) -> None:
        return None

    def _touch_rows_cache(self, *_args, **_kwargs):
        return None

    def _start_cache_refresh(self, *_args, **_kwargs):
        return None

    def _refresh_data(self):
        return None


def test_on_pick_tags_pre_hook_cancel_stops_update(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "p1"
    path.mkdir()
    app = _App(path)
    called = {"save": 0}

    def _save_base_tags(*_args, **_kwargs):
        called["save"] += 1

    monkeypatch.setattr(
        tag_actions.hooks_runtime,
        "dispatch_pre",
        lambda *_args, **_kwargs: PreOutcome(cancelled=True, reason="blocked", change={}),
    )

    tag_actions.on_pick_tags(
        app,
        {"x": "add"},
        [path],
        base_dir=tmp_path,
        is_packed_archive_path=lambda _path: False,
        load_base_meta=lambda _path: (["old"], "", False),
        save_base_tags=_save_base_tags,
    )
    assert called["save"] == 0
    assert any("cancelled by hook" in msg for _lvl, msg in app.logs)
