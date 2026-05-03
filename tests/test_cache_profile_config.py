from __future__ import annotations

import pytest

from homebase.config import cache_profile


def test_load_cache_profile_table_applies_all_and_view_overrides() -> None:
    table = cache_profile.load_cache_profile_table(
        {
            "cache_profile": {
                "all": {
                    "pri-2": {
                        "update_interval_s": 10,
                        "update_batch_size": 16,
                        "update_priority": 40,
                        "cache_mode": "ttl",
                        "cache_ttl_s": 30,
                    }
                },
                "active": {"pri-2": {"update_batch_size": 24}},
            }
        }
    )

    resolved = cache_profile.resolve_cache_profile(
        profile_name="pri-2",
        view="active",
        profile_table=table,
    )
    assert resolved["update_interval_s"] == 10
    assert resolved["update_batch_size"] == 24
    assert resolved["update_priority"] == 40


def test_resolve_cache_profile_merge_order() -> None:
    table = cache_profile.load_cache_profile_table(
        {
            "cache_profile": {
                "all": {
                    "pri-1": {
                        "update_interval_s": 5,
                        "update_batch_size": 10,
                        "update_priority": 20,
                        "cache_mode": "ttl",
                        "cache_ttl_s": 15,
                    }
                },
                "archive": {"pri-1": {"update_batch_size": 4}},
            }
        }
    )
    resolved = cache_profile.resolve_cache_profile(
        profile_name="pri-1",
        view="archive",
        profile_table=table,
        explicit_fields={"update_batch_size": 2},
        profile_overrides={
            "all": {"update_batch_size": 8},
            "archive": {"update_batch_size": 3},
        },
    )
    assert resolved["update_batch_size"] == 3


def test_load_cache_profile_table_rejects_invalid_profile_keys() -> None:
    with pytest.raises(ValueError, match="invalid keys"):
        cache_profile.load_cache_profile_table(
            {
                "cache_profile": {
                    "all": {
                        "pri-3": {
                            "update_interval_s": 10,
                            "update_batch_size": 1,
                            "update_priority": 90,
                            "cache_mode": "ttl",
                            "cache_ttl_s": 60,
                            "bad_key": 1,
                        }
                    }
                }
            }
        )


def test_resolve_cache_profile_rejects_unknown_reference() -> None:
    table = cache_profile.load_cache_profile_table({"cache_profile": {"all": {}}})
    with pytest.raises(ValueError, match="unknown cache_profile reference"):
        cache_profile.resolve_cache_profile(
            profile_name="missing",
            view="active",
            profile_table=table,
        )
