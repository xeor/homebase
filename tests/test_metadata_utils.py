from __future__ import annotations

from homebase.metadata import utils as metadata_utils


def test_extract_base_meta_fields_handles_invalid_shapes() -> None:
    tags, description, wip = metadata_utils.extract_base_meta_fields(
        {
            "tags": ["api", "", "api", 42],
            "description": "  desc  ",
            "wip": 1,
        }
    )

    assert tags == ["api", "api", "42"]
    assert description == "desc"
    assert wip is True


def test_normalize_base_data_coerces_and_deduplicates() -> None:
    normalized, notes = metadata_utils.normalize_base_data(
        {
            "tags": ["a", "", "a", "b"],
            "description": 12,
            "wip": "yes",
            "log": {"events": [{"ok": 1}, "bad", {"ok": 2}]},
        }
    )

    assert normalized["tags"] == ["a", "b"]
    assert normalized["description"] == "12"
    assert normalized["wip"] is True
    assert normalized["log"] == {"events": [{"ok": 1}, {"ok": 2}]}
    assert "normalized description" in notes
    assert "normalized wip" in notes
    assert "normalized log.events entries" in notes


def test_base_meta_schema_issues_reports_warnings() -> None:
    issues = metadata_utils.base_meta_schema_issues(
        {
            "tags": {"bad": 1},
            "description": 1,
            "wip": "yes",
            "extra": "x",
        },
        allowed_keys={"tags", "description", "wip", "log"},
    )

    assert len(issues) == 1
    level, code, message = issues[0]
    assert level == "warning"
    assert code == "schema_warn"
    assert "tags has non-standard type" in message
