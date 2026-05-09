# Actions, Hotbar, Keys

Technical reference for `actions`, `hotbar`, and `keys` in
`<base>/.homebase/config.yaml`.

## Model

- `actions`: map `action_id -> action_def`
- `hotbar`: ordered list of target-scope action ids (or `{action,label}`)
- `keys`: map `hotkey -> action_id` (or `{action,label}`)

Built-ins are loaded from code (`BUILTIN_ACTIONS` + auto-registered tab
actions). Config may override built-in `label` and `confirm` only.

## Action kinds

- `builtin`: implemented in code
- `shell`: executes templated command
- `filepicker`: runs templated list command, chooses one item, runs command once
- `note`: built-in note op (`add_log`)

## Scope

- `target`: action uses selected row(s)
- `workspace`: action does not require row context
- `tab`: tab-jump action id (`tab.<top>` / `tab.<top>.<child>`)

## Multi dispatch (`shell`)

- `joined` (default): one dispatch with list vars (`paths_q`, `names_q`, ...)
- `per_row`: one dispatch per selected row with per-row vars (`path_q`, `name`, ...)

## Template variable families

- always: workspace/runtime vars (`base_dir_q`, `count`, `view`, `now_iso`, ...)
- per-row: row vars (`path_q`, `rel_path_q`, `branch`, `tags`, ...)
- list-form: selection vars (`paths_q`, `rel_paths_q`, `names_q`)
- filepicker: picker vars (`selection`, `selection_q`)

Use `_q` forms for shell command rendering.

## Validation rules

- `actions` must be a map
- built-in id entries: only `label` and `confirm`; `confirm` must be string
- custom entries:
  - `kind` required (`shell|filepicker|note`)
  - `shell` requires `command`
  - `filepicker` requires `scope: target`, `list`, `command`
  - `note` requires `scope: target`, `op: add_log`
  - `note` op value may appear once across all actions
- templates referencing unavailable vars fail at config load
- `hotbar` entries must resolve to existing `scope: target` actions
- `keys` entries must resolve to existing action ids

## Tab actions

Auto-registered at runtime from side-tab config:

- `tab.<top>`
- `tab.<top>.<child>`

They dispatch via side-tab jump and are not hotbar-eligible.

## Discoverability surfaces

- CLI: `b help actions`
- TUI: `Info > Stats` (live template context inspector)
