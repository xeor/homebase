from __future__ import annotations

from pathlib import Path

from homebase.core.models import PreOutcome, ProjectRow
from homebase.ui.actions import bulk_dispatch


class _AppStub:
    def __init__(self) -> None:
        self.logs: list[tuple[str, str]] = []
        self.refreshed_side = 0
        self.base_dir = Path("/tmp/base")

    def _log(self, msg: str, level: str) -> None:
        self.logs.append((level, msg))

    def _refresh_side(self) -> None:
        self.refreshed_side += 1

    def _preflight_bulk_action(self, _action: str, _paths: list[Path]):
        return [], []

    def _preflight_skip_summary(self, _skipped: list[tuple[Path, str]]) -> str:
        return ""

    def _find_row(self, _path: Path):
        return None


def _noop(*_args, **_kwargs):
    return None


def _false_meta(*_args, **_kwargs):
    return False, "err"


def test_on_confirm_bulk_logs_cancelled_and_returns() -> None:
    app = _AppStub()
    bulk_dispatch.on_confirm_bulk(
        app,
        False,
        "archive",
        [Path("/tmp/base/a")],
        archive_move_internal=_noop,
        archive_restore_internal=_noop,
        archive_pack_internal=_noop,
        archive_unpack_internal=_noop,
        delete_internal=_noop,
        is_packed_archive_path=lambda _path: False,
        open_meta_for_review=_false_meta,
        rename_legacy_base_yaml=_false_meta,
        project_row=_noop,
        row_build_errors=(ValueError,),
    )
    assert app.logs and app.logs[0][0] == "warn"
    assert "cancelled" in app.logs[0][1]
    assert app.refreshed_side == 1


def test_on_confirm_bulk_handles_no_runnable_items() -> None:
    app = _AppStub()
    bulk_dispatch.on_confirm_bulk(
        app,
        True,
        "archive",
        [Path("/tmp/base/a")],
        archive_move_internal=_noop,
        archive_restore_internal=_noop,
        archive_pack_internal=_noop,
        archive_unpack_internal=_noop,
        delete_internal=_noop,
        is_packed_archive_path=lambda _path: False,
        open_meta_for_review=_false_meta,
        rename_legacy_base_yaml=_false_meta,
        project_row=_noop,
        row_build_errors=(ValueError,),
    )
    assert app.logs and app.logs[0][0] == "warn"
    assert "no eligible items" in app.logs[0][1]
    assert app.refreshed_side == 1


def test_on_confirm_bulk_delete_respects_pre_hook_cancel(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "p1"
    target.mkdir()

    class _DeleteApp(_AppStub):
        def __init__(self) -> None:
            super().__init__()
            self.view_mode = "active"
            self._rows = [
                ProjectRow(
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

        def _preflight_bulk_action(self, _action: str, _paths: list[Path]):
            return [target], []

        def _find_row(self, path: Path):
            for idx, row in enumerate(self._rows):
                if row.path == path:
                    return self._rows, idx
            return None

        def _busy_start(self, _msg: str) -> None:
            return None

        def _busy_stop(self) -> None:
            return None

    called = {"delete": 0}

    def _delete_internal(*_args, **_kwargs):
        called["delete"] += 1

    monkeypatch.setattr(
        bulk_dispatch.hooks_runtime,
        "dispatch_pre",
        lambda *_args, **_kwargs: PreOutcome(cancelled=True, reason="blocked", change={}),
    )

    app = _DeleteApp()
    bulk_dispatch.on_confirm_bulk(
        app,
        True,
        "delete",
        [target],
        archive_move_internal=_noop,
        archive_restore_internal=_noop,
        archive_pack_internal=_noop,
        archive_unpack_internal=_noop,
        delete_internal=_delete_internal,
        is_packed_archive_path=lambda _path: False,
        open_meta_for_review=_false_meta,
        rename_legacy_base_yaml=_false_meta,
        project_row=_noop,
        row_build_errors=(ValueError,),
    )
    assert called["delete"] == 0
    assert any("cancelled by hook" in msg for _level, msg in app.logs)
