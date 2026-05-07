from __future__ import annotations

from pathlib import Path

import pytest

from homebase.config.property_defs import load_property_defs


def test_load_property_defs_token_keyed_map(tmp_path: Path) -> None:
    conf = tmp_path / ".homebase" / "config.yaml"
    conf.parent.mkdir()
    conf.write_text(
        """
properties:
  GIT:
    label: Git
    color: '#87afff'
    dir-exists: [.git]
  ACT:
    label: active
    color: '#ffb86c'
    cache_ttl_s: 3
    queries:
      - type: tmux_open_panes
""".strip()
    )
    defs = load_property_defs(tmp_path)
    by_key = {p.key: p for p in defs}
    assert "git" in by_key
    assert by_key["git"].token == "GIT"
    assert by_key["git"].color == "#87afff"
    assert "act" in by_key
    assert by_key["act"].queries
    assert by_key["act"].cache_ttl_s == 3


def test_load_property_defs_supports_variables(tmp_path: Path) -> None:
    conf = tmp_path / ".homebase" / "config.yaml"
    conf.parent.mkdir()
    conf.write_text(
        """
variables:
  _COLOR_DYN: '#ffb86c'
  _NOTES_ROOT: /tmp/notes
properties:
  ACT:
    label: '{{ _COLOR_DYN }} active'
    color: '{{ _COLOR_DYN }}'
    queries:
      - type: tmux_open_panes
  N:
    label: notes
    color: '{{ _COLOR_DYN }}'
    file-exists:
      - '{{ _NOTES_ROOT }}/{{ NAME_WITH_ARCHIVE_PREFIX }}.md'
""".strip()
    )
    defs = load_property_defs(tmp_path)
    by_key = {p.key: p for p in defs}
    assert by_key["act"].color == "#ffb86c"
    assert by_key["act"].label == "#ffb86c active"
    assert by_key["n"].file_exists == ("/tmp/notes/{{ NAME_WITH_ARCHIVE_PREFIX }}.md",)


def test_load_property_defs_supports_cache_profile_and_overrides(tmp_path: Path) -> None:
    conf = tmp_path / ".homebase" / "config.yaml"
    conf.parent.mkdir()
    conf.write_text(
        """
cache_profile:
  all:
    pri-2:
      update_interval_s: 10
      update_batch_size: 16
      update_priority: 40
      cache_mode: ttl
      cache_ttl_s: 30
  archive:
    pri-2:
      cache_ttl_s: 120
properties:
  E:
    label: env
    cache_profile: pri-2
    cache_profile_overrides:
      active:
        cache_ttl_s: 7
    queries:
      - type: tmux_open_panes
""".strip()
    )
    defs = load_property_defs(tmp_path)
    by_key = {p.key: p for p in defs}
    assert by_key["e"].cache_profile == "pri-2"
    assert by_key["e"].cache_ttl_for_view("active") == 7
    assert by_key["e"].cache_ttl_for_view("archive") == 120
    assert by_key["e"].cache_profiles_by_view is not None
    assert by_key["e"].cache_profiles_by_view["active"]["update_batch_size"] == 16


def test_load_property_defs_rejects_invalid_cache_profile_reference(tmp_path: Path) -> None:
    conf = tmp_path / ".homebase" / "config.yaml"
    conf.parent.mkdir()
    conf.write_text(
        """
properties:
  E:
    label: env
    cache_profile: missing
    queries:
      - type: tmux_open_panes
""".strip()
    )
    with pytest.raises(ValueError, match="invalid cache profile"):
        load_property_defs(tmp_path)
