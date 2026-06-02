from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from homebase.commands.archive import (
    archive_pack_internal as _archive_pack_internal,
)
from homebase.commands.archive import (
    archive_restore_internal as _archive_restore_internal,
)
from homebase.commands.archive import (
    archive_unpack_internal as _archive_unpack_internal,
)
from homebase.commands.archive import (
    cmd_rm as _cmd_rm,
)
from homebase.core.constants import (
    HOMEBASE_DIR_NAME,
    REGRESSION_TEST_REPORT_FILE_NAME,
)
from homebase.workspace import regression


@pytest.fixture(autouse=True)
def _wire_regression_handlers() -> None:
    regression.archive_pack_internal = _archive_pack_internal
    regression.archive_unpack_internal = _archive_unpack_internal
    regression.archive_restore_internal = _archive_restore_internal
    regression.cmd_rm = _cmd_rm


def test_cmd_test_regression_list_only_prints_all_cases(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    rc = regression.cmd_test_regression(tmp_path, tmp_path, list_only=True)
    out = capsys.readouterr().out
    assert rc == 0
    for name, _fn in regression._regression_cases():
        assert name in out


def test_cmd_test_regression_unknown_case_returns_1(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    rc = regression.cmd_test_regression(
        tmp_path, tmp_path, selected=["does-not-exist"]
    )
    err = capsys.readouterr().err
    assert rc == 1
    assert "unknown case" in err


def test_cmd_test_regression_runs_selected_case_and_writes_report(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    rc = regression.cmd_test_regression(
        tmp_path, tmp_path, selected=["reconcile_queue_priority"]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "reconcile_queue_priority" in out
    report_path = tmp_path / HOMEBASE_DIR_NAME / REGRESSION_TEST_REPORT_FILE_NAME
    assert report_path.is_file()
    payload = yaml.safe_load(report_path.read_text())
    assert payload["total"] == 1
    assert payload["passed"] == 1
    assert payload["failed"] == 0
    names = [c["name"] for c in payload["cases"]]
    assert names == ["reconcile_queue_priority"]


def test_regtest_case_result_catches_exceptions(tmp_path: Path) -> None:
    def boom(_root: Path) -> tuple[bool, str]:
        raise RuntimeError("nope")

    res = regression._regtest_case_result("boom", boom)
    assert res.name == "boom"
    assert res.ok is False
    assert "RuntimeError" in res.detail
    assert res.elapsed_s >= 0


def test_regtest_rm_outside_blocked_self_test(tmp_path: Path) -> None:
    ok, detail = regression._regtest_rm_outside_blocked(tmp_path)
    assert ok is True
    assert "blocked" in detail


def test_regtest_rm_symlink_escape_blocked_self_test(tmp_path: Path) -> None:
    ok, detail = regression._regtest_rm_symlink_escape_blocked(tmp_path)
    assert ok is True
    assert "blocked" in detail


def test_regtest_archive_pack_atomic_failure_self_test(tmp_path: Path) -> None:
    ok, detail = regression._regtest_archive_pack_atomic_failure(tmp_path)
    assert ok is True
    assert "source preserved" in detail


def test_regtest_tar_unpack_rejects_traversal_self_test(tmp_path: Path) -> None:
    ok, detail = regression._regtest_tar_unpack_rejects_traversal(tmp_path)
    assert ok is True
    assert "rejected" in detail


def test_regtest_restore_outside_opt_in_self_test(tmp_path: Path) -> None:
    ok, detail = regression._regtest_restore_outside_opt_in(tmp_path)
    assert ok is True
    assert "opt-in" in detail


def test_regtest_cache_schema_multi_base_self_test(tmp_path: Path) -> None:
    ok, detail = regression._regtest_cache_schema_multi_base(tmp_path)
    assert ok is True
    assert "stable" in detail


def test_regtest_reconcile_queue_priority_self_test(tmp_path: Path) -> None:
    ok, detail = regression._regtest_reconcile_queue_priority(tmp_path)
    assert ok is True
    assert "queue" in detail


def test_regtest_nested_discovery_parity_self_test(tmp_path: Path) -> None:
    ok, detail = regression._regtest_nested_discovery_parity(tmp_path)
    assert ok is True


def test_cmd_test_regression_no_selection_runs_all(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    rc = regression.cmd_test_regression(tmp_path, tmp_path)
    out = capsys.readouterr().out
    assert "regression summary" in out
    report_path = tmp_path / HOMEBASE_DIR_NAME / REGRESSION_TEST_REPORT_FILE_NAME
    assert report_path.is_file()
    payload = yaml.safe_load(report_path.read_text())
    assert payload["total"] == len(regression._regression_cases())
    # If any case fails, rc should be 1; otherwise 0
    if payload["failed"] == 0:
        assert rc == 0
    else:
        assert rc == 1
