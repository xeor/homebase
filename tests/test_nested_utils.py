from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from homebase.core import nested as nested_utils
from homebase.core.constants import (
    BASE_MARKER_FILE,
    HOMEBASE_DIR_NAME,
    NESTED_DISCOVERY_REPORT_FILE_NAME,
)


def _touch_marker(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / BASE_MARKER_FILE).write_text("\n")


def _skip_never(_base: Path, _archive: Path, _cur: Path) -> bool:
    return False


def _prune_noop(_dirnames: list[str]) -> None:
    return None


def _skip_archive_root(base: Path, archive: Path, cur: Path) -> bool:
    return cur == archive


def _prune_dotdirs(dirnames: list[str]) -> None:
    dirnames[:] = [d for d in dirnames if not d.startswith(".")]


def _zone_depth_simple(base: Path, path: Path) -> tuple[str, int]:
    rel = path.resolve().relative_to(base.resolve())
    if rel.parts and rel.parts[0] == "_archive":
        depth = max(0, len(rel.parts) - 1)
        return "archive", depth
    return "active", len(rel.parts)


def _marker_allowed_when_top_level(
    _base: Path, _marker: Path, _include_nested: bool | None
) -> bool:
    return True


def test_suggest_flat_name_nested(tmp_path: Path) -> None:
    base = tmp_path / "base"
    path = base / "grp" / "sub"
    path.mkdir(parents=True)
    assert nested_utils.suggest_flat_name(base, path) == "grp-sub"


def test_suggest_flat_name_top_level(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    path = base / "single"
    path.mkdir()
    assert nested_utils.suggest_flat_name(base, path) == "single"


def test_suggest_flat_name_returns_basename_when_no_parts(tmp_path: Path) -> None:
    # When nested_path resolves equal to base_dir the relative path
    # has no parts; the helper falls back to nested_path.name.
    base = tmp_path / "base"
    base.mkdir()
    assert nested_utils.suggest_flat_name(base, base) == "base"


def test_cmd_utils_unknown_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    rc = nested_utils.cmd_utils(
        Path("."),
        "unknown",
        cmd_utils_opt_in_nested_discovery=lambda _b: 0,
    )
    err = capsys.readouterr().err
    assert rc == 1
    assert "unknown utils subcommand" in err


def test_cmd_utils_known_subcommand_delegates(tmp_path: Path) -> None:
    seen: dict[str, Path] = {}

    def fake_opt_in(base: Path) -> int:
        seen["base"] = base
        return 7

    rc = nested_utils.cmd_utils(
        tmp_path,
        "opt-in-nested-discovery",
        cmd_utils_opt_in_nested_discovery=fake_opt_in,
    )
    assert rc == 7
    assert seen["base"] == tmp_path


def test_scan_nested_project_paths_finds_nested_markers(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    _touch_marker(base)
    _touch_marker(base / "grp" / "sub")
    _touch_marker(base / "grp" / "sub" / "leaf")
    _touch_marker(base / "_archive")

    found = nested_utils.scan_nested_project_paths(
        base,
        archive_dir_name="_archive",
        base_marker_file=BASE_MARKER_FILE,
        discovery_should_skip_active_walk_path=_skip_archive_root,
        discovery_prune_walk_dirnames=_prune_dotdirs,
    )
    names = {p.name for p in found}
    assert "sub" in names
    # walking stops at the first nested marker found in each branch
    assert "leaf" not in names
    assert base not in found
    # archive root pruned by skip callback
    assert (base / "_archive").resolve() not in found


def test_scan_nested_project_paths_skips_top_level_markers(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    _touch_marker(base / "topA")
    _touch_marker(base / "topB")
    found = nested_utils.scan_nested_project_paths(
        base,
        archive_dir_name="_archive",
        base_marker_file=BASE_MARKER_FILE,
        discovery_should_skip_active_walk_path=_skip_never,
        discovery_prune_walk_dirnames=_prune_noop,
    )
    # depth==1 entries are not "nested"
    assert found == []


def test_scan_nested_markers_all_categorises_entries(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    _touch_marker(base / "topA")
    _touch_marker(base / "grp" / "sub")
    _touch_marker(base / "parent")
    _touch_marker(base / "parent" / "child")
    _touch_marker(base / "_archive" / "2026" / "2026-01-01_a")
    _touch_marker(base / "_archive" / "2026" / "2026-01-01_a" / "leaf")

    counts, entries = nested_utils.scan_nested_markers_all(
        base,
        base_marker_file=BASE_MARKER_FILE,
        discovery_zone_depth=_zone_depth_simple,
        discovery_marker_allowed=_marker_allowed_when_top_level,
    )

    assert counts["markers_total"] == 6
    by_rel = {entry["relative"]: entry for entry in entries}
    assert by_rel["topA"]["zone"] == "active"
    assert by_rel["topA"]["nested"] is False
    assert by_rel["grp/sub"]["zone"] == "active"
    assert by_rel["grp/sub"]["active_subfolder"] is True
    assert by_rel["parent/child"]["nested"] is True
    archive_rel = "_archive/2026/2026-01-01_a"
    assert by_rel[archive_rel]["zone"] == "archive"
    assert by_rel[f"{archive_rel}/leaf"]["nested"] is True
    assert counts["active_subfolder_markers"] >= 1
    assert counts["active_child_of_marker"] >= 1
    assert counts["archive_child_of_marker"] >= 1


def test_cmd_utils_opt_in_writes_report_when_invalid(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    _touch_marker(base / "parent")
    _touch_marker(base / "parent" / "child")

    state = {"nested_enabled": False}

    def scan(_base: Path) -> tuple[dict[str, int], list[dict[str, object]]]:
        return nested_utils.scan_nested_markers_all(
            base,
            base_marker_file=BASE_MARKER_FILE,
            discovery_zone_depth=_zone_depth_simple,
            discovery_marker_allowed=_marker_allowed_when_top_level,
        )

    yes_no_calls: list[str] = []

    def prompt(question: str, _default: bool) -> bool:
        yes_no_calls.append(question)
        return True

    def nested_enabled(_base: Path) -> bool:
        return state["nested_enabled"]

    def set_nested(_base: Path, value: bool) -> None:
        state["nested_enabled"] = value

    rc = nested_utils.cmd_utils_opt_in_nested_discovery(
        base,
        base_marker_file=BASE_MARKER_FILE,
        archive_dir_name="_archive",
        nested_discovery_enabled=nested_enabled,
        set_nested_discovery_enabled=set_nested,
        prompt_yes_no=prompt,
        scan_nested_markers_all_fn=scan,
    )

    assert rc == 2
    report_path = base / HOMEBASE_DIR_NAME / NESTED_DISCOVERY_REPORT_FILE_NAME
    assert report_path.is_file()
    payload = yaml.safe_load(report_path.read_text())
    assert payload["base_dir"] == str(base)
    assert payload["summary"]["markers_total"] == 2
    assert any(q.startswith("Write full nested marker report") for q in yes_no_calls)


def test_cmd_utils_opt_in_enables_nested_when_valid_subfolder(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base"
    base.mkdir()
    _touch_marker(base / "grp" / "sub")  # valid subfolder marker, no parent marker

    state = {"nested_enabled": False}

    def scan(_base: Path) -> tuple[dict[str, int], list[dict[str, object]]]:
        return nested_utils.scan_nested_markers_all(
            base,
            base_marker_file=BASE_MARKER_FILE,
            discovery_zone_depth=_zone_depth_simple,
            discovery_marker_allowed=_marker_allowed_when_top_level,
        )

    def prompt(_question: str, _default: bool) -> bool:
        return True

    rc = nested_utils.cmd_utils_opt_in_nested_discovery(
        base,
        base_marker_file=BASE_MARKER_FILE,
        archive_dir_name="_archive",
        nested_discovery_enabled=lambda _b: state["nested_enabled"],
        set_nested_discovery_enabled=lambda _b, v: state.__setitem__("nested_enabled", v),
        prompt_yes_no=prompt,
        scan_nested_markers_all_fn=scan,
    )
    assert rc == 0
    assert state["nested_enabled"] is True


def test_cmd_utils_opt_in_disables_when_no_valid_subfolders(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    _touch_marker(base / "topA")
    _touch_marker(base / "topB")

    state = {"nested_enabled": True}

    def scan(_base: Path) -> tuple[dict[str, int], list[dict[str, object]]]:
        return nested_utils.scan_nested_markers_all(
            base,
            base_marker_file=BASE_MARKER_FILE,
            discovery_zone_depth=_zone_depth_simple,
            discovery_marker_allowed=_marker_allowed_when_top_level,
        )

    def prompt(_question: str, _default: bool) -> bool:
        return True

    rc = nested_utils.cmd_utils_opt_in_nested_discovery(
        base,
        base_marker_file=BASE_MARKER_FILE,
        archive_dir_name="_archive",
        nested_discovery_enabled=lambda _b: state["nested_enabled"],
        set_nested_discovery_enabled=lambda _b, v: state.__setitem__("nested_enabled", v),
        prompt_yes_no=prompt,
        scan_nested_markers_all_fn=scan,
    )
    assert rc == 0
    assert state["nested_enabled"] is False


def test_cmd_utils_opt_in_keeps_state_when_user_declines(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    _touch_marker(base / "grp" / "sub")  # valid subfolder marker

    state = {"nested_enabled": False}

    def scan(_base: Path) -> tuple[dict[str, int], list[dict[str, object]]]:
        return nested_utils.scan_nested_markers_all(
            base,
            base_marker_file=BASE_MARKER_FILE,
            discovery_zone_depth=_zone_depth_simple,
            discovery_marker_allowed=_marker_allowed_when_top_level,
        )

    rc = nested_utils.cmd_utils_opt_in_nested_discovery(
        base,
        base_marker_file=BASE_MARKER_FILE,
        archive_dir_name="_archive",
        nested_discovery_enabled=lambda _b: state["nested_enabled"],
        set_nested_discovery_enabled=lambda _b, v: state.__setitem__("nested_enabled", v),
        prompt_yes_no=lambda _q, _d: False,
        scan_nested_markers_all_fn=scan,
    )
    assert rc == 0
    assert state["nested_enabled"] is False
