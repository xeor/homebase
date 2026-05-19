from __future__ import annotations

from pathlib import Path

import yaml

from homebase.config import tag_rules
from homebase.config.store import (
    clear_global_config_cache,
    save_global_config_dict,
)
from homebase.core.constants import GLOBAL_CONFIG_FILE_NAME, HOMEBASE_DIR_NAME


def _setup_base(tmp_path: Path, rules: list[dict] | None = None) -> Path:
    base = tmp_path / "base"
    (base / HOMEBASE_DIR_NAME).mkdir(parents=True)
    cfg_path = base / HOMEBASE_DIR_NAME / GLOBAL_CONFIG_FILE_NAME
    if rules is None:
        cfg_path.write_text("")
    else:
        cfg_path.write_text(yaml.safe_dump({"tag_rules": rules}))
    clear_global_config_cache()
    tag_rules.clear_tag_rules_cache()
    return base


# ---- Styling -------------------------------------------------------


def test_no_rules_falls_back_to_hash_color(tmp_path: Path) -> None:
    base = _setup_base(tmp_path)
    out = tag_rules.resolve_for_display("work", base)
    assert out.display == "work"
    assert out.style_spec.startswith("#") and len(out.style_spec) == 7
    assert out.matched_rule == ""


def test_color_override_wins(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^work$", "color": "#abcdef"},
    ])
    out = tag_rules.resolve_for_display("work", base)
    assert out.style_spec == "#abcdef"
    assert out.matched_rule == "^work$"
    other = tag_rules.resolve_for_display("home", base)
    assert other.style_spec.startswith("#") and other.style_spec != "#abcdef"


def test_first_match_wins(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "color": "#ff0000", "bold": True},
        {"match": "^prio:p1$", "color": "#00ff00"},
    ])
    out = tag_rules.resolve_for_display("prio:p1", base)
    assert out.style_spec == "bold #ff0000"


def test_prefix_and_suffix_in_display(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^wip$", "prefix": "⚡ ", "suffix": " 🔥"},
    ])
    out = tag_rules.resolve_for_display("wip", base)
    assert out.display == "⚡ wip 🔥"


def test_all_modifiers_compose(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {
            "match": "^critical$",
            "color": "#ff5555",
            "bold": True,
            "italic": True,
            "underline": True,
        },
    ])
    out = tag_rules.resolve_for_display("critical", base)
    assert out.style_spec == "bold italic underline #ff5555"


def test_modifier_without_color_uses_hash_color(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^bold-me$", "bold": True},
    ])
    out = tag_rules.resolve_for_display("bold-me", base)
    assert out.style_spec.startswith("bold #")


def test_malformed_regex_is_skipped(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"match": "[unbalanced", "color": "#ff0000"},
        {"match": "^good$", "color": "#00ff00"},
    ])
    out = tag_rules.resolve_for_display("good", base)
    assert out.style_spec == "#00ff00"


def test_missing_match_and_tags_skips_rule(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"color": "#ff0000"},  # neither match nor tags
        {"match": "^x$", "color": "#00ff00"},
    ])
    out = tag_rules.resolve_for_display("x", base)
    assert out.style_spec == "#00ff00"


def test_rules_reload_when_config_changes(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^work$", "color": "#aaaaaa"},
    ])
    first = tag_rules.resolve_for_display("work", base)
    assert first.style_spec == "#aaaaaa"

    save_global_config_dict(
        base,
        {"tag_rules": [{"match": "^work$", "color": "#bbbbbb"}]},
    )
    clear_global_config_cache()
    tag_rules.clear_tag_rules_cache()

    second = tag_rules.resolve_for_display("work", base)
    assert second.style_spec == "#bbbbbb"


def test_resolution_is_cached(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^x$", "color": "#abcdef"},
    ])
    a = tag_rules.resolve_for_display("x", base)
    b = tag_rules.resolve_for_display("x", base)
    assert a is b


def test_hash_color_is_deterministic() -> None:
    assert tag_rules.hash_tag_color("work") == tag_rules.hash_tag_color("work")
    assert tag_rules.hash_tag_color("home") != tag_rules.hash_tag_color("work")


# ---- Explicit ``tags:`` list match --------------------------------


def test_explicit_tags_list_matches(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"tags": ["work", "office"], "color": "#88ccff"},
    ])
    assert tag_rules.resolve_for_display("work", base).style_spec == "#88ccff"
    assert tag_rules.resolve_for_display("office", base).style_spec == "#88ccff"
    assert tag_rules.resolve_for_display("home", base).style_spec != "#88ccff"


def test_rule_with_both_match_and_tags(tmp_path: Path) -> None:
    """A rule may declare both — either should trigger it."""
    base = _setup_base(tmp_path, [
        {
            "match": "^prio:",
            "tags": ["urgent"],
            "color": "#ff5555",
        },
    ])
    assert tag_rules.resolve_for_display("prio:p0", base).style_spec == "#ff5555"
    assert tag_rules.resolve_for_display("urgent", base).style_spec == "#ff5555"


# ---- Tree / grouping ----------------------------------------------


def test_direct_parents_from_matching_rule(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"]},
        {"tags": ["work", "office"], "parents": ["business"]},
    ])
    assert tag_rules.direct_parents("prio:p0", base) == ("priority",)
    assert tag_rules.direct_parents("work", base) == ("business",)
    assert tag_rules.direct_parents("unknown", base) == ()


def test_multiple_parents_per_rule(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"tags": ["python", "rust"], "parents": ["programming", "compiled"]},
    ])
    assert tag_rules.direct_parents("python", base) == (
        "programming", "compiled",
    )


def test_ancestors_transitive(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"]},
        {"tags": ["priority"], "parents": ["meta"]},
    ])
    anc = tag_rules.ancestors("prio:p0", base)
    assert anc == frozenset({"priority", "meta"})


def test_ancestors_cycle_is_broken(tmp_path: Path) -> None:
    """Misconfigured loop must not hang. ``a`` → ``b`` → ``a``."""
    base = _setup_base(tmp_path, [
        {"tags": ["a"], "parents": ["b"]},
        {"tags": ["b"], "parents": ["a"]},
    ])
    assert tag_rules.ancestors("a", base) == frozenset({"b"})
    assert tag_rules.ancestors("b", base) == frozenset({"a"})


def test_is_descendant_of_inclusive(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"]},
    ])
    assert tag_rules.is_descendant_of("priority", "priority", base)
    assert tag_rules.is_descendant_of("prio:p0", "priority", base)
    assert not tag_rules.is_descendant_of("home", "priority", base)


def test_descendants_within_candidate_set(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"]},
        {"tags": ["priority"], "parents": ["meta"]},
    ])
    candidates = frozenset({
        "prio:p0", "prio:p1", "priority", "meta", "home", "work",
    })
    assert tag_rules.descendants("priority", candidates, base) == frozenset({
        "prio:p0", "prio:p1", "priority",
    })
    assert tag_rules.descendants("meta", candidates, base) == frozenset({
        "prio:p0", "prio:p1", "priority", "meta",
    })


def test_roots_lists_all_declared_parents(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority", "meta"]},
        {"tags": ["work"], "parents": ["business"]},
        {"tags": ["wip"]},  # no parents
    ])
    assert tag_rules.roots(base) == ("business", "meta", "priority")


def test_is_group_only_defaults_false(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"tags": ["work"], "color": "#88ccff"},
    ])
    assert tag_rules.is_group_only("work", base) is False
    # Unmatched tag → False too.
    assert tag_rules.is_group_only("anything", base) is False


def test_is_group_only_flag_propagates(tmp_path: Path) -> None:
    base = _setup_base(tmp_path, [
        {"tags": ["priority", "meta"], "group_only": True},
        {"tags": ["work"], "color": "#88ccff"},
    ])
    assert tag_rules.is_group_only("priority", base) is True
    assert tag_rules.is_group_only("meta", base) is True
    assert tag_rules.is_group_only("work", base) is False


def test_is_group_only_respects_first_match_wins(tmp_path: Path) -> None:
    """Earlier rule's group_only=False sticks even if a later rule
    has group_only=True for the same tag (first match wins)."""
    base = _setup_base(tmp_path, [
        {"tags": ["x"], "group_only": False},
        {"tags": ["x"], "group_only": True},
    ])
    assert tag_rules.is_group_only("x", base) is False


def test_grouping_only_rule_has_default_style(tmp_path: Path) -> None:
    """A rule that only assigns parents (no color/modifiers) must
    still let the matched tag render with the default hash color."""
    base = _setup_base(tmp_path, [
        {"match": "^prio:", "parents": ["priority"]},
    ])
    out = tag_rules.resolve_for_display("prio:p0", base)
    assert out.style_spec.startswith("#")
    assert out.matched_rule == "^prio:"
    assert tag_rules.direct_parents("prio:p0", base) == ("priority",)
