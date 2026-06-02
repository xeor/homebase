from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import yaml

from ..cache.api import cache_db_path, cache_load_rows, cache_store_rows
from ..core.constants import (
    ARCHIVE_DIR_NAME,
    BASE_MARKER_FILE,
    CACHE_SCHEMA_VERSION,
    ENV_BASE_DIR,
    HOMEBASE_DIR_NAME,
    PACKED_ARCHIVE_SUFFIX,
    REGRESSION_TEST_REPORT_FILE_NAME,
)
from ..core.models import RegressionCaseResult
from .rows import (
    collect_archived,
    collect_projects,
    reconcile_queue_pop_next,
    reconcile_queue_push,
)


def _missing(name: str) -> Callable[..., Any]:
    def _err(*_args: object, **_kwargs: object) -> Any:
        raise RuntimeError(
            f"regression handler {name!r} not configured; "
            "call cmd_test_regression() via the CLI entrypoint"
        )
    return _err


archive_pack_internal: Callable[..., Path] = _missing("archive_pack_internal")
archive_unpack_internal: Callable[..., Path] = _missing("archive_unpack_internal")
archive_restore_internal: Callable[..., Path] = _missing("archive_restore_internal")
cmd_rm: Callable[..., int] = _missing("cmd_rm")


def _regtest_case_result(
    name: str, fn: Callable[[Path], tuple[bool, str]]
) -> RegressionCaseResult:
    root = Path(tempfile.mkdtemp(prefix=".b-regtest-"))
    t0 = time.perf_counter()
    try:
        ok, detail = fn(root)
    except (
        OSError,
        ValueError,
        TypeError,
        RuntimeError,
        subprocess.SubprocessError,
        sqlite3.Error,
        yaml.YAMLError,
        json.JSONDecodeError,
    ) as exc:
        ok = False
        detail = f"unexpected {exc.__class__.__name__}: {exc}"
    finally:
        elapsed_s = time.perf_counter() - t0
        shutil.rmtree(root, ignore_errors=True)
    return RegressionCaseResult(name=name, ok=ok, detail=detail, elapsed_s=elapsed_s)


def _regtest_write_marker(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / BASE_MARKER_FILE).write_text("tags: []\n")


def _regtest_rm_outside_blocked(root: Path) -> tuple[bool, str]:
    base = root / "base"
    outside = root / "outside"
    base.mkdir(parents=True, exist_ok=True)
    outside.mkdir(parents=True, exist_ok=True)
    old = os.environ.get(ENV_BASE_DIR)
    os.environ[ENV_BASE_DIR] = str(base)
    try:
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            rc = cmd_rm(str(outside), force_outside_base=False)
    finally:
        if old is None:
            os.environ.pop(ENV_BASE_DIR, None)
        else:
            os.environ[ENV_BASE_DIR] = old
    if rc != 1:
        return False, f"expected rc=1, got rc={rc}"
    if not outside.exists():
        return False, "outside path deleted unexpectedly"
    return True, "outside-base delete blocked"


def _regtest_rm_symlink_escape_blocked(root: Path) -> tuple[bool, str]:
    base = root / "base"
    outside = root / "outside"
    base.mkdir(parents=True, exist_ok=True)
    outside.mkdir(parents=True, exist_ok=True)
    link = base / "outside-link"
    link.symlink_to(outside, target_is_directory=True)
    old = os.environ.get(ENV_BASE_DIR)
    os.environ[ENV_BASE_DIR] = str(base)
    try:
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            rc = cmd_rm(str(link), force_outside_base=False)
    finally:
        if old is None:
            os.environ.pop(ENV_BASE_DIR, None)
        else:
            os.environ[ENV_BASE_DIR] = old
    if rc != 1:
        return False, f"expected rc=1, got rc={rc}"
    if not outside.exists():
        return False, "symlink target outside base deleted unexpectedly"
    return True, "symlink escape blocked"


def _regtest_archive_pack_atomic_failure(root: Path) -> tuple[bool, str]:
    base = root / "base"
    src = base / ARCHIVE_DIR_NAME / "2026" / "2026-01-01_p"
    _regtest_write_marker(src)
    (src / "data.txt").write_text("payload\n")
    target = src.with_name(f"{src.name}{PACKED_ARCHIVE_SUFFIX}")

    orig_replace = Path.replace

    def _replace_injected(self: Path, target_path: Path | str) -> Path:
        dst = Path(target_path)
        if self.parent == src.parent and dst == target:
            raise OSError("injected replace failure")
        return orig_replace(self, target_path)

    Path.replace = _replace_injected  # type: ignore[method-assign,assignment]
    try:
        try:
            _ = archive_pack_internal(base, src)
            return False, "expected injected failure"
        except OSError as exc:
            if "injected" not in str(exc):
                return False, f"unexpected error: {exc}"
    finally:
        Path.replace = orig_replace  # type: ignore[method-assign]

    if not src.is_dir():
        return False, "source directory was not preserved"
    if target.exists():
        return False, "packed target unexpectedly exists"
    return True, "source preserved on finalize failure"


def _regtest_tar_unpack_rejects_traversal(root: Path) -> tuple[bool, str]:
    base = root / "base"
    arc = base / ARCHIVE_DIR_NAME / "2026"
    arc.mkdir(parents=True, exist_ok=True)
    packed = arc / f"2026-01-01_mal{PACKED_ARCHIVE_SUFFIX}"
    with tarfile.open(packed, "w:gz") as tf:
        ti = tarfile.TarInfo("../evil.txt")
        payload = b"x\n"
        ti.size = len(payload)
        tf.addfile(ti, io.BytesIO(payload))
    try:
        _ = archive_unpack_internal(base, packed)
    except ValueError as exc:
        if "unsafe archive member path" not in str(exc):
            return False, f"unexpected error text: {exc}"
    else:
        return False, "expected traversal tar to be rejected"
    if (root / "evil.txt").exists():
        return False, "escape file was written outside extraction dir"
    return True, "traversal payload rejected"


def _regtest_restore_outside_opt_in(root: Path) -> tuple[bool, str]:
    base = root / "base"
    src = base / ARCHIVE_DIR_NAME / "2026" / "2026-01-01_p"
    _regtest_write_marker(src)
    (src / "data.txt").write_text("payload\n")
    outside_target = root / "outside" / "restored"

    try:
        _ = archive_restore_internal(
            base,
            src,
            target_override=outside_target,
            sync_tags=False,
            allow_outside_base=False,
        )
        return False, "expected outside restore to fail without opt-in"
    except ValueError:
        pass
    if not src.exists():
        return False, "archive source missing after rejected restore"

    restored = archive_restore_internal(
        base,
        src,
        target_override=outside_target,
        sync_tags=False,
        allow_outside_base=True,
    )
    if restored != outside_target.resolve():
        return False, f"unexpected restore target: {restored}"
    if not outside_target.is_dir():
        return False, "outside target not restored"
    return True, "outside restore requires explicit opt-in"


def _regtest_cache_schema_multi_base(root: Path) -> tuple[bool, str]:
    base1 = root / "base1"
    base2 = root / "base2"
    base1.mkdir(parents=True, exist_ok=True)
    base2.mkdir(parents=True, exist_ok=True)

    ts1 = cache_store_rows(base1, [], [])
    ts2 = cache_store_rows(base2, [], [])
    if ts1 <= 0 or ts2 <= 0:
        return False, "cache_store_rows returned invalid refresh timestamp"

    _a1, _r1, refreshed1 = cache_load_rows(base1)
    _a2, _r2, refreshed2 = cache_load_rows(base2)
    if refreshed1 <= 0 or refreshed2 <= 0:
        return False, "cache_load_rows did not read refresh timestamp"

    for db in (cache_db_path(base1), cache_db_path(base2)):
        if not db.is_file():
            return False, f"cache db missing: {db}"
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute(
                "SELECT value FROM cache_meta WHERE key='schema_version'"
            ).fetchone()
        finally:
            conn.close()
        if not row or str(row[0]) != str(CACHE_SCHEMA_VERSION):
            return False, f"schema_version mismatch in {db}"
    return True, "multi-base cache init stable"


def _regtest_nested_discovery_parity(root: Path) -> tuple[bool, str]:
    base = root / "base"
    base.mkdir(parents=True, exist_ok=True)

    _regtest_write_marker(base / "top")
    _regtest_write_marker(base / "grp" / "sub")
    _regtest_write_marker(base / "parent")
    _regtest_write_marker(base / "parent" / "child")

    _regtest_write_marker(base / ARCHIVE_DIR_NAME / "2026" / "2026-01-01_a")
    _regtest_write_marker(
        base / ARCHIVE_DIR_NAME / "2026" / "grp" / "2026-01-01_b"
    )
    _regtest_write_marker(base / ARCHIVE_DIR_NAME / "2026" / "2026-01-01_p")
    _regtest_write_marker(
        base
        / ARCHIVE_DIR_NAME
        / "2026"
        / "2026-01-01_p"
        / "2026-01-01_c"
    )

    active_false = {r.path.name for r in collect_projects(base, include_nested=False)}
    archive_false = {r.path.name for r in collect_archived(base, include_nested=False)}
    if "sub" in active_false:
        return False, "active nested marker leaked with include_nested=false"
    if "2026-01-01_b" in archive_false:
        return False, "archive nested marker leaked with include_nested=false"

    active_true = {r.path.name for r in collect_projects(base, include_nested=True)}
    archive_true = {r.path.name for r in collect_archived(base, include_nested=True)}
    if "sub" not in active_true:
        return False, "active nested marker missing with include_nested=true"
    if "2026-01-01_b" not in archive_true:
        return False, "archive nested marker missing with include_nested=true"
    if "child" in active_true:
        return False, "active child-of-marker should be excluded"
    if "2026-01-01_c" in archive_true:
        return False, "archive child-of-marker should be excluded"
    return True, "active/archive nested discovery parity holds"


def _regtest_reconcile_queue_priority(root: Path) -> tuple[bool, str]:
    _ = root
    q: list[tuple[int, str, str, list[Path]]] = []
    q = reconcile_queue_push(q, "active", "bg-z", [Path("/tmp/bg-z")], priority=1)
    q = reconcile_queue_push(
        q, "archive", "manual-now", [Path("/tmp/manual")], priority=2
    )
    q = reconcile_queue_push(q, "active", "bg-a", [Path("/tmp/bg-a")], priority=1)

    q_after_busy, first_busy = reconcile_queue_pop_next(q, worker_running=True)
    if first_busy is not None:
        return False, "queue popped while worker_running=True"
    if len(q_after_busy) != 3:
        return False, "queue changed while worker_running=True"

    q2, first = reconcile_queue_pop_next(q_after_busy, worker_running=False)
    if first is None:
        return False, "queue did not pop with worker idle"
    if first[2] != "manual-now":
        return False, f"expected manual request first, got {first[2]}"

    q3, second = reconcile_queue_pop_next(q2, worker_running=False)
    if second is None or second[2] != "bg-a":
        got = second[2] if second is not None else "<none>"
        return False, f"expected bg-a second, got {got}"

    q4 = q3
    for i in range(60):
        q4 = reconcile_queue_push(
            q4,
            "active",
            f"bg-{i:02d}",
            [Path(f"/tmp/bg-{i:02d}")],
            priority=1,
            limit=40,
        )
    if len(q4) != 40:
        return False, f"queue length cap failed: got {len(q4)}"
    if not any(item[2] == "bg-00" for item in q4):
        return (
            False,
            "queue ordering/cap unexpectedly dropped highest lexical background item",
        )
    return True, "manual/background queue priority and cap behavior stable"


def _regression_cases() -> list[tuple[str, Callable[[Path], tuple[bool, str]]]]:
    return [
        ("rm_outside_blocked", _regtest_rm_outside_blocked),
        ("rm_symlink_escape_blocked", _regtest_rm_symlink_escape_blocked),
        ("archive_pack_atomic_failure", _regtest_archive_pack_atomic_failure),
        ("tar_unpack_rejects_traversal", _regtest_tar_unpack_rejects_traversal),
        ("restore_outside_opt_in", _regtest_restore_outside_opt_in),
        ("cache_schema_multi_base", _regtest_cache_schema_multi_base),
        ("reconcile_queue_priority", _regtest_reconcile_queue_priority),
        ("nested_discovery_parity", _regtest_nested_discovery_parity),
    ]


def cmd_test_regression(
    base_dir: Path,
    run_cwd: Path,
    list_only: bool = False,
    selected: list[str] | None = None,
    *,
    archive_pack_internal: Callable[[Path, Path], Path] | None = None,
    archive_unpack_internal: Callable[[Path, Path], Path] | None = None,
    archive_restore_internal: Callable[..., Path] | None = None,
    cmd_rm: Callable[..., int] | None = None,
) -> int:
    selected = list(selected or [])

    if archive_pack_internal is not None:
        globals()["archive_pack_internal"] = archive_pack_internal
    if archive_unpack_internal is not None:
        globals()["archive_unpack_internal"] = archive_unpack_internal
    if archive_restore_internal is not None:
        globals()["archive_restore_internal"] = archive_restore_internal
    if cmd_rm is not None:
        globals()["cmd_rm"] = cmd_rm

    cases = _regression_cases()
    case_map = {name: fn for name, fn in cases}
    if list_only:
        for name, _fn in cases:
            print(name)
        return 0

    run_cases: list[tuple[str, Callable[[Path], tuple[bool, str]]]] = []
    if selected:
        for name in selected:
            fn = case_map.get(name)
            if fn is None:
                print(f"unknown case: {name}", file=sys.stderr)
                print(
                    "run `b test regression --list` to inspect available cases",
                    file=sys.stderr,
                )
                return 1
            run_cases.append((name, fn))
    else:
        run_cases = cases

    print(f"regression tests: {len(run_cases)} case(s)")
    print(f"configured base folder: {base_dir}")
    results: list[RegressionCaseResult] = []
    for name, fn in run_cases:
        res = _regtest_case_result(name, fn)
        results.append(res)
        status = "PASS" if res.ok else "FAIL"
        print(f"- {name:<30} {status}  {res.elapsed_s:.3f}s  {res.detail}")

    failures = [r for r in results if not r.ok]
    elapsed_total = sum(r.elapsed_s for r in results)
    print(
        f"regression summary: total={len(results)} pass={len(results) - len(failures)} fail={len(failures)} elapsed={elapsed_total:.2f}s"
    )

    report_path = base_dir / HOMEBASE_DIR_NAME / REGRESSION_TEST_REPORT_FILE_NAME
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "total": len(results),
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "elapsed_s": round(elapsed_total, 6),
        "cases": [
            {
                "name": r.name,
                "ok": r.ok,
                "detail": r.detail,
                "elapsed_s": round(r.elapsed_s, 6),
            }
            for r in results
        ],
    }
    report_path.write_text(yaml.safe_dump(payload, sort_keys=False))
    print(f"regression report updated: {report_path}")
    return 1 if failures else 0
