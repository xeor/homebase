# TODO

Active work for `homebase`. Two sections: code follow-ups and product
features.

## Code follow-ups

- [x] **Wire `UIContext` through to `BApp`.** `ui/context.py` defines
  the carrier and `build_ui_context()` snapshots `core.constants`,
  but `BApp` still reads everything from `core.constants` (mutated
  in-place by `cli/entry.main`). Pass the full context, store on
  `self.ctx`, drop the in-place mutation.

- [x] **Drop primitive forwarders in `workspace/rows.py`.**
  `is_under`, `archive_now_iso`, `archive_iso_from_ts`,
  `parse_archive_timestamp`, `split_archive_name`,
  `packed_archive_dir_name`, `split_archive_entry_name`, `fmt_ymd` —
  all wrappers that bind constants. After `UIContext` is wired,
  callers can call `core.utils.X(…, ARCHIVE_TZ)` directly.

- [ ] **Further split `ui/app.py` (~2880 lines).** Five remaining
  long methods worth extracting to module functions:
  - [x] `_on_confirm_bulk` (168 lines) → `ui/actions/bulk_dispatch.py`
  - [x] `_start_archive_action_worker` (128 lines) →
    `ui/actions/archive_worker.py`
  - [x] `_on_pick_actions` (117 lines) — converted to dispatch dict in
    `ui/actions/pick_actions.py`
  - `compose` (80) and `on_mount` (64) — fine.
  Then group thin delegations by topic into mixin classes:
  - [x] `ui/app_display.py` — `_configure_table_columns`, `_refresh_side`,
    `_build_side_*`, `_refresh_table`
  - [x] `ui/app_actions.py` — core `action_*` thin delegations
  - [x] `ui/app_events.py` — `on_data_table_*`, `on_button_pressed`, `on_key`

- [x] **Split `workspace/rows.py` (555 lines)** by topic:
  - `workspace/rows.py` — `collect_workspace_rows`,
    `collect_projects`, `collect_archived`, `archived_restore_target`,
    `sort_rows`, `_sort_modes_for_view`,
    `_normalize_sort_mode_for_view`, `match_query`
  - [x] `workspace/discovery_helpers.py` — extracted `_discovery_*`
    + `DISCOVERY_PRUNE_DIR_NAMES` block
  - [x] `workspace/filter_compile.py` — extracted `_FILTER_TOKEN_RE`,
    `_property_alias_set`, `compile_filter_expr`,
    `query_uses_filter_syntax`, `normalize_filter_expression`,
    `pretty_filter_expression`
  - [x] Moved `cmd_setup`, `cmd_cache_warm`, `cmd_tags_sync`,
    `cmd_status`, `cmd_recent`, `cmd_utils`,
    `cmd_utils_opt_in_nested_discovery`, `print_help` and setup
    helpers into `commands/setup.py`.

- [x] **Split `commands/archive.py` (~340 lines)** by topic (reviewed).
  Current `commands/archive.py` is domain-coherent and already delegates
  heavy lifting to `archive/io.py`, `archive/ops.py`, `archive/service.py`
  and `commands/workspace.py`; no further split needed now.
  - `commands/policy.py` — `_archive_root`, `_policy_reason_*`,
    `_archive_require_*`, `is_packed_archive_path`,
    `normalize_restore_target`, the tar/safe-extract helpers,
    `_archive_extract_single_root`, `_archive_sync_tags_if_needed`,
    `_remove_placeholder_target`, prompt helpers
  - `commands/archive_ops.py` — `archive_parent_for`,
    `archive_move_internal`, `archive_pack_internal`,
    `archive_unpack_internal`, `archive_restore_internal`,
    `delete_internal`
  - `commands/archive.py` — `cmd_archive_mv`, `cmd_archive_ls`,
    `cmd_archive_undo`, `cmd_archive_restore_entry`
  - `commands/misc.py` — `cmd_rm`, `cmd_migrate`, `cmd_fix`,
    `suggest_project_root`, `find_marker_root_upward`,
    `try_parse_archive_suffix_loose`, `confirm`

- [x] **Layering test.** Add `tests/test_layering.py` that walks
  each subpackage's imports and asserts the rule in `AGENTS.md` §5.
  Catches regressions of the inward-only layering rule.

- [ ] **Collapse `ui/runtime.py`.** It's a 5-line re-export of
  `from .app import run_textual_ui`. Could be folded into
  `ui/__init__.py` to remove one extra hop. Low priority.

## Feature backlog

- [ ] **"Running vscode" property** — `ACT` and `vscode` shown in
  orange; detection command must be configurable in global config.

- [ ] **Hotkeys for custom actions** — e.g. an F-key bound to start
  vscode for the focused project.

- [ ] **Dedupe `opened_at` and `opened_ts`** in `.base.yml`. Pick one.

- [ ] **Standardize on `.yaml`** suffix; migrate from `.yml` (the
  `.base.yml` marker, the optional `.base.yaml` legacy form, and the
  global config file).

- [ ] **Stable `ctrl+p` ordering**: `item`, `selected`, `global` — no
  special logic, just naming.

- [ ] **Hide the `selected` group** in the `ctrl+p` menu when no
  items are selected.

- [ ] **"Edit global config"** entry in the (global setting) menu —
  opens the file in `$EDITOR`, then `b` reloads when the editor
  exits.

- [ ] **Document every meaning-bearing color** in the cheat-sheet.
  The purple in archive-mode is currently undocumented.

- [ ] **`b c <key>` quick-create command.** Reads a config table like
  `create_templates: [{key: "tmp", options: ["prefix-datetime",
  "property-tmp", "changedir"]}]`. Picks options from a small set
  (date prefix, `.tmp` suffix, copier template id, `cd` after create,
  skip-TUI, …). Replace the example with whatever shape ends up most
  natural after a real implementation pass.
