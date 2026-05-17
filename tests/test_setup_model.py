from __future__ import annotations

import pytest

from homebase.core.setup_model import (
    INTENT_ABSENT,
    INTENT_CANNOT_CREATE,
    INTENT_CANNOT_REMOVE,
    INTENT_CREATE,
    INTENT_KEEP,
    INTENT_REMOVE,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    STATUS_WARN,
    FixResult,
    SetupCheck,
    SetupFix,
    SetupSummary,
)


def test_setup_check_rejects_invalid_status() -> None:
    with pytest.raises(ValueError):
        SetupCheck(id="x", name="x", status="weird", detail="d")


def test_setup_check_accepts_known_statuses() -> None:
    for status in (STATUS_PASS, STATUS_WARN, STATUS_FAIL, STATUS_SKIP):
        SetupCheck(id="x", name="x", status=status, detail="d")


def test_fix_result_defaults() -> None:
    r = FixResult(id="a", title="A", intent=INTENT_KEEP, success=True)
    assert r.error is None
    assert r.skipped is True  # INTENT_KEEP counts as skipped (no change)


def test_setup_summary_exit_code_maps_from_hard_fail() -> None:
    summary = SetupSummary(
        pass_count=1,
        warn_count=0,
        fail_count=0,
        hard_fail=False,
    )
    assert summary.exit_code == 0
    summary.hard_fail = True
    assert summary.exit_code == 1


def test_setup_fix_requires_defaults_to_empty_tuple() -> None:
    fix = SetupFix(
        id="x",
        title="X",
        currently_present=False,
        currently_correct=False,
        required=False,
        recommended=False,
        apply_create=lambda: None,
    )
    assert fix.requires == ()
    assert fix.preview_create == ()
    assert fix.preview_remove == ()


def test_selected_default_is_true_when_currently_correct() -> None:
    fix = SetupFix(id="x", title="X", currently_correct=True)
    assert fix.selected_default is True


def test_selected_default_is_true_for_absent_recommended_with_installer() -> None:
    fix = SetupFix(
        id="x", title="X",
        currently_correct=False, currently_present=False,
        recommended=True,
        apply_create=lambda: None,
    )
    assert fix.selected_default is True


def test_selected_default_is_false_for_absent_optional() -> None:
    fix = SetupFix(
        id="x", title="X",
        currently_correct=False, currently_present=False,
        recommended=False,
        apply_create=lambda: None,
    )
    assert fix.selected_default is False


def test_intent_selected_present_correct_is_keep() -> None:
    fix = SetupFix(id="x", title="X", currently_present=True, currently_correct=True)
    assert fix.intent(selected=True) == INTENT_KEEP


def test_intent_selected_absent_with_create_is_create() -> None:
    fix = SetupFix(id="x", title="X", apply_create=lambda: None)
    assert fix.intent(selected=True) == INTENT_CREATE


def test_intent_selected_absent_without_create_is_cannot_create() -> None:
    fix = SetupFix(id="x", title="X")
    assert fix.intent(selected=True) == INTENT_CANNOT_CREATE


def test_intent_unselected_present_with_remove_is_remove() -> None:
    fix = SetupFix(
        id="x", title="X",
        currently_present=True, currently_correct=True,
        apply_remove=lambda: None,
    )
    assert fix.intent(selected=False) == INTENT_REMOVE


def test_intent_unselected_present_without_remove_is_cannot_remove() -> None:
    fix = SetupFix(
        id="x", title="X",
        currently_present=True, currently_correct=True,
    )
    assert fix.intent(selected=False) == INTENT_CANNOT_REMOVE


def test_intent_unselected_absent_is_absent() -> None:
    fix = SetupFix(id="x", title="X")
    assert fix.intent(selected=False) == INTENT_ABSENT


def test_fix_result_changed_only_for_successful_changes() -> None:
    assert FixResult("a", "A", INTENT_CREATE, success=True).changed
    assert FixResult("a", "A", INTENT_REMOVE, success=True).changed
    assert not FixResult("a", "A", INTENT_KEEP, success=True).changed
    assert not FixResult("a", "A", INTENT_CREATE, success=False).changed
