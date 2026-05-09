# Config redesign — `actions` and `bindings`

Single-user proposal. No backwards compatibility.
Goal: one place per fact, no duplication, every action (built-in or
custom) addressable by the same id, hotbar order explicit, dispatch
validated, action template clean and orthogonal.

WIP is **out of scope** of this redesign — it's a quick-jump favorites
system, not an action system. Keep the existing `wip.hotkeys` section.

## What's wrong today

Looking at the current `config.yaml` and `README.md`:

1. **Two parallel lists for one concept.** `custom_actions` defines
   actions, `custom_hotkeys` binds them. They share ids by string.
   Example pair (`open_item_in_codium` / `hk_open_item_in_codium`)
   duplicates `id`, `label`, and a prefix-string reference
   (`action:custom:open_item_in_codium`).
2. **Three target namespaces stuffed into one string field.**
   `target: action:open_selected`, `action:custom:foo`,
   `tab:side_main/selected`. Magic prefixes, no validation.
3. **Built-in actions can't be relabeled.** `archive`, `delete`,
   `notes_create`, `tags_set`, `open_selected`, `set_desc`,
   `rename_item`, … live only in `core/constants.ACTION_SHORT_HELP`
   and `_VIEW_CONFIG_DEFAULT`. The user has no way to rename the
   visible label.
4. **Action shape is implicit.** Whether an action is a shell command,
   a file-picker, or a note primitive is inferred from which keys
   are present (`command`, `list_command`+`run_command`,
   `note_command`). No discriminator.
5. **`{{ full_path }}` is magic-polymorphic.** With
   `loop_on_multi: false` it auto-expands to multiple quoted paths;
   with `loop_on_multi: true` it's a single path. Same template
   variable, two different shapes depending on a flag elsewhere.
   Confusing to read and write.
6. **Hotbar order is implicit list order** of `custom_hotkeys`.
   You can't read the config and know the on-screen order without
   filtering for `hotbar: true`.
7. **Vestigial fields.**
   - `custom_actions[].action: <other_id>` (forward-to-other) — never
     used in the live config.
   - `loop_on_multi: false` on `open_each_selected_in_editor`
     contradicts the id; the entry is identical to
     `open_item_in_editor`. The naming was driven by trying to express
     "loop" / "joined" semantics in the id — would not be needed if
     the multi-mode were a first-class field.
8. **Decorations rendered in code, not declared.** `(note)` /
   `(filepicker)` postfixes are hard-coded into `action_items.py`
   based on which fields are present. A user override label has no
   way to keep them.

## Proposed schema

Two concepts. **Action** = a thing that can be invoked.
**Binding** = a way to invoke it (hotbar slot or key). Bindings
reference actions by id, never re-define them.

### Built-in vs custom

- **Built-in actions** (`archive`, `delete`, `open_selected`,
  `notes_create`, `tags_set`, `restore`, `pack`, `unpack`,
  `toggle_pack`, `set_desc`, `rename_item`, `refresh_cache`,
  `full_reconcile`, `reload_global_config`, `edit_global_config`,
  `reconcile_all_cache`, `reconcile_selection_cache`,
  `review_meta`, `rename_meta_ext`, `readme_create`, `readme_edit`,
  `notes_open`, `suffix_set`, …) are implemented in code. The user
  **may only override `label`**. Behavior, scope, multi-mode,
  view-scope, confirm-prompt, and so on are fixed in code.
COMMENT: confirm-prompt should also be possible to override

- **Custom actions** are user-defined and have a full action
  template (`kind`, `scope`, `multi`, `command`, …).
- **Side-tab actions** (`tab.<name>`) are auto-registered built-ins
  for tab navigation. Same rule: only `label` is user-overridable.
- **Id collisions are rejected at load time.** A custom action
  whose id matches a built-in id is an error — built-in ids are
  reserved. To get different behavior than a built-in, define a
  custom action under a different id and bind your hotbar/keys to
  the new id.

### `actions:` map

```yaml
actions:

  # ---- built-in: only label is overridable ----
  archive:        { label: Archive }
  delete:         { label: Delete forever }
  open_selected:  { label: Open in tmux }
  notes_create:   { label: New note }
  tags_set:       { label: Tags… }

  # ---- side-tab (built-in too — auto-registered, label override only) ----
  tab.selected:   { label: Selected }
  tab.events:     { label: Events }

  # ---- custom: shell, scope=target, joined paths (single invocation) ----
  open_item_in_editor:
    kind: shell
    label: Open in editor
    scope: target
    multi: joined
    command: '$EDITOR {{ paths_q }}'

  # ---- custom: shell, scope=target, run once per selected row ----
  open_in_daisydisk:
    kind: shell
    label: Open with DaisyDisk
    scope: target
    multi: per_row
    command: 'open -n -a DaisyDisk {{ path_q }}'

  # ---- custom: shell, no row context ----
  open_base_in_editor:
    kind: shell
    label: Open base dir
    scope: workspace
    command: '$EDITOR {{ base_dir_q }}'

  # ---- custom: filepicker ----
  pick_markdown_in_codium:
    kind: filepicker
    label: Pick markdown (Codium)
    scope: target
    list:    'find {{ path_q }} -type f -name "*.md"'
    command: 'codium {{ selection_q }}'

  # ---- custom: note primitive ----
  add_log_to_note:
    kind: note
    label: Add log to note
    scope: target
    op: add_log

  # ---- custom: with confirmation prompt that uses context vars ----
  delete_archived:
    kind: shell
    label: Wipe archived
    scope: workspace
    confirm: "Really delete {{ archive_count }} archived projects?"
    command: 'rm -rf {{ archive_dir_q }}'
```

#### Field reference

**Allowed on every action** (built-in *and* custom):

| Field    | Type | Meaning                                                      |
|----------|------|--------------------------------------------------------------|
| `label`  | str  | Display name. Built-ins use the system default if absent.    |

**Custom actions only** (rejected at config-load time on a built-in id):

| Field      | Type                       | Meaning                                                              |
|------------|----------------------------|----------------------------------------------------------------------|
| `kind`     | enum                       | `shell`, `filepicker`, `note`. Required.                             |
| `scope`    | `target` / `workspace`     | Does the action need a row? Default `target`.                        |
| `multi`    | `joined` / `per_row`       | When `scope=target` with multiple rows selected, how to dispatch. Default `joined`. Only meaningful on `kind: shell`; ignored on `kind: filepicker` and `kind: note` (see *kind*-specific table). |
| `confirm`  | bool / str                 | `true` → default prompt; `false`/absent → no prompt; string → custom prompt (template variables allowed; see below). |
| `when`     | str (predicate)            | Predicate; only show/dispatch when condition holds. *(future, slot reserved)* |
| `hidden`   | bool                       | Hide from action picker; still dispatchable via key/hotbar.          |
| `view_scope` | list[str]                | Which views the action applies to (`[active]`, `[archive]`; default both). |
| `icon`     | str                        | Small glyph rendered in menu. *(future, slot reserved)*              |
| `group`    | str                        | Category in the action menu. *(future, slot reserved)*               |

`kind`-specific fields (validated against `kind`, custom actions only):

| `kind`        | Required fields              | Allowed `scope`           | Notes                              |
|---------------|------------------------------|---------------------------|------------------------------------|
| `shell`       | `command`                    | `target` *or* `workspace` | Template; vars below.              |
| `filepicker`  | `list`, `command`            | `target` only             | `list` emits candidates per row, results merged; user picks once; `command` runs once with `{{ selection }}`. **`multi:` is not exposed** — semantics are fixed: collection phase loops on multi-selection, dispatch is single-shot. |
| `note`        | `op`                         | `target` only             | Built-in op enum. Only `add_log` today. Each `op` value may appear at most once across all actions. |

### Template variables

`{{ path }}` (single-row) and `{{ paths }}` (joined) are now distinct;
no more polymorphic `{{ full_path }}`.

| Var                                     | Available in                | Meaning                              |
|-----------------------------------------|-----------------------------|--------------------------------------|
| `{{ path }}`                            | scope=target, multi=per_row | Absolute path of the current row.    |
| `{{ path_q }}`                          | scope=target, multi=per_row | Same, shell-quoted.                  |
| `{{ paths }}`                           | scope=target, multi=joined  | All selected paths, space-joined.    |
| `{{ paths_q }}`                         | scope=target, multi=joined  | All selected paths, each shell-quoted, space-joined. |
| `{{ rel_path }}` / `{{ rel_path_q }}`   | scope=target (per-row only) | Path relative to base_dir.           |
| `{{ name }}`                            | scope=target, multi=per_row | Project name.                        |
| `{{ branch }}`                          | scope=target, multi=per_row | Git branch.                          |
| `{{ tags }}`                            | scope=target, multi=per_row | Comma-joined tags.                   |
| `{{ properties }}`                      | scope=target, multi=per_row | Comma-joined property keys.          |
| `{{ count }}`                           | always                      | Number of currently selected rows in the active view (0 if no selection). Always reflects the visible selection — independent of action `scope`. Useful in `confirm:` strings. |
| `{{ base_dir }}` / `{{ base_dir_q }}`   | always                      | Workspace root.                      |
| `{{ archive_dir }}` / `{{ archive_dir_q }}` | always                  | Archive directory.                   |
| `{{ archive_count }}`                   | always                      | Number of archived projects.         |
| `{{ selection }}` / `{{ selection_q }}` | filepicker only             | Picked candidate.                    |
COMMENT: I want more template variables, both from the workspace context and from the item selected. Think about what might be useful and create them. Context variables should also be possible to view under info>stats (it can be renamed to stats/context).

Rules:
- A template that references a variable not available in the action's
  `scope`/`multi` context fails at config-load time with a clear error.
- `_q` suffix means shell-quoted. Use it for any value that lands
  inside a shell command. Validation warns if you use a non-`_q`
  form in a `command:` template.
- **`per_row` ordering is selection order** (top → bottom of the
  visible list at dispatch time). Stable and documented; do not rely
  on any other order.

### `confirm:` prompt — template variables

`confirm:` strings are templates. Same context as the action's
`command:` template applies (so `{{ count }}`, `{{ paths }}`,
`{{ base_dir }}`, etc. resolve before the prompt is shown).

Built-in actions ship with a fixed prompt where one is needed
(e.g. `delete` already has its own confirmation in code) and are
**not** user-configurable beyond `label`. Confirm prompts on custom
actions look like:

```yaml
wipe_selected:
  kind: shell
  label: Wipe selected
  scope: target
  multi: joined
  confirm: "Delete {{ count }} project(s) under {{ base_dir }}?"
  command: 'rm -rf {{ paths_q }}'
```

A future iteration may extend `confirm:` to a structured form for
richer prompts (multi-line text, default-no buttons, additional
inputs). The string-or-bool form proposed here covers today's needs
and forward-compatibly slots into the structured form later via
something like:

```yaml
# possible future
confirm:
  prompt: "Delete {{ count }} projects?"
  default: cancel        # cancel | accept
  inputs:
    reason: { label: "Reason", required: true }
```

The string-or-bool form remains valid; the map form is purely
additive.

### `hotbar:` — ordered list

```yaml
hotbar:
  - open_selected
  - notes_create
  - add_log_to_note
  - { action: open_item_in_codium, key: 'ç', label: codium }
```

- Position in the list = on-screen position (1, 2, 3, …).
- Item is either a string (action id) or a map with overrides.
- `key:` (optional) attaches a key shortcut to this hotbar entry.
COMMENT: There shoulnt be a key attached to it. Key can be removed

- `label:` (optional) overrides the action's label *for this binding
  only* (lets the same action appear differently in different
  bindings).

### `keys:` — flat key map

```yaml
keys:
  '†':           tags_set
  'ctrl+alt+r':  refresh_cache

  # long form when the binding needs an override
  'f5':
    action: open_item_in_codium
    label:  reload-with-codium
```

- Short form: `key: action_id`.
- Long form: `key: { action: ..., label: ... }`.
  (`when:` reserved for future, see *Future-friendly hooks*.)
- A key may appear at most **once across the entire bindings set**
  — the union of `hotbar` `key:` fields and `keys:` keys. If you
  want a hotbar slot *and* a keyboard shortcut for the same action,
  attach the `key:` to the `hotbar` entry; do not also list it in
  `keys:`.

### Side-tab navigation

Today: `target: tab:side_main/selected`. New: side tabs are
auto-registered as actions with stable ids
(`tab.selected`, `tab.events`, …). Like other built-ins, only
`label` is overridable.

```yaml
actions:
  tab.events: { label: Log }

hotbar:
  - tab.events
```

No magic prefixes anywhere.

COMMENT: Take care that the tab menu are hieractical. Ie, the events are really under info.events. There are two levels of menues. The example above should be tab.info.events

## The current config rewritten

```yaml
new:
  post-commands:
    - { label: git init, command: git init }

archive: { timezone: Europe/Oslo }
suffixes: [tmp, fork]

# UNCHANGED — wip is favorites/quick-jump, not actions.
wip:
  hotkeys: { '1': '©', '2': '™', '3': '£', '4': '€', '5': '∞', '6': '§', '7': '|', '8': '[', '9': ']' }

filters:
  named:
    recent-web: '#web created=@-1w'
    python:    '#python'
    node:      '#node'
    test1:     '(@python OR @node) !documentation'
  saved:
    - '#python abc'
    - '(@python OR @node) !documentation'
    - '#node'
    - '#python'

variables:
  _COLOR_CORE: '#7dcfff'
  # ... (unchanged)

properties:
  # ... (unchanged)

actions:
  # built-in label overrides
  open_selected: { label: Open (tmux) }
  notes_create:  { label: Notes }
  tags_set:      { label: Tags… }

  open_item_in_editor:
    kind: shell
    label: Open in editor
    scope: target
    multi: joined
    command: '$EDITOR {{ paths_q }}'

  open_base_in_editor:
    kind: shell
    label: Open base dir in editor
    scope: workspace
    command: '$EDITOR {{ base_dir_q }}'

  open_in_daisydisk:
    kind: shell
    label: Open/scan with DaisyDisk
    scope: target
    multi: per_row
    command: 'open -n -a DaisyDisk {{ path_q }}'

  open_item_in_codium:
    kind: shell
    label: Open in VSCodium
    scope: target
    multi: joined
    command: 'codium {{ paths_q }}'

  open_item_in_tmux_window:
    kind: shell
    label: Open in new tmux window
    scope: target
    multi: per_row
    command: 'tmux new-window -c {{ path_q }}'

  pick_markdown_in_codium:
    kind: filepicker
    label: Pick markdown (Codium)
    scope: target
    list:    'find {{ path_q }} -type f -name "*.md"'
    command: 'codium {{ selection_q }}'

  add_log_to_note:
    kind: note
    label: Add log to note
    scope: target
    op: add_log

hotbar:
  - open_selected
  - notes_create
  - add_log_to_note
  - { action: open_item_in_codium, key: 'ç', label: codium }

keys:
  '†': tags_set

# rest (create_templates, open_mode, reconcile, state, notes, table,
# new_project, files_view, ...) unchanged.
```

Eliminated from current `custom_actions` (8 → 7 entries):
- `open_each_selected_in_editor` — was a hack to express
  `loop_on_multi: false` semantics in the id; obsolete now that
  `multi: per_row | joined` is a first-class field.

`custom_hotkeys` (5 entries) replaced by:
- `hotbar` (4 entries, ordered)
- `keys` (1 entry)

No id duplication. No `hk_*` mirror ids. No magic `action:custom:` /
`tab:` prefixes.

## What changes in the action template (the user's "rotete" point)

Side-by-side, today vs proposed:

```yaml
# TODAY
- id: open_item_in_codium
  label: Open item in VSCodium
  scope: target
  command: codium {{ full_path }}
- id: open_in_daisydisk
  label: Open/scan with DaisyDisk
  scope: target
  command: open -n -a DaisyDisk {{ full_path }}
  loop_on_multi: true
```

```yaml
# PROPOSED
open_item_in_codium:
  kind: shell
  label: Open in VSCodium
  scope: target
  multi: joined
  command: 'codium {{ paths_q }}'

open_in_daisydisk:
  kind: shell
  label: Open/scan with DaisyDisk
  scope: target
  multi: per_row
  command: 'open -n -a DaisyDisk {{ path_q }}'
```

Differences that matter:
- `id` is gone — the YAML key *is* the id.
- `kind: shell` is explicit (no inferred polymorphism).
- `loop_on_multi: true/false` → `multi: per_row | joined` (named after
  what it does; defaults to `joined` matching today's default).
- `{{ full_path }}` (which silently meant "single-or-many depending
  on flag") → either `{{ path_q }}` (per_row) or `{{ paths_q }}`
  (joined). One template variable per actual concept.
- Quoting required at the call site (`_q`); validation flags
  unquoted vars in commands.

## `b help actions` — discoverability

Add a CLI command (or side-tab listing) that prints every dispatchable
action so the user can learn what's overridable without grepping
source code.

Sketch:

```
$ b help actions
SOURCE      ID                          LABEL                      KIND        SCOPE      MULTI     BOUND
builtin     archive                     Archive                    -           target     -         -
builtin     delete                      Delete                     -           target     -         -
overridden  open_selected               Open (tmux)                -           target     -         hotbar:1
overridden  notes_create                Notes                      -           target     -         hotbar:2
overridden  tags_set                    Tags…                      -           target     -         '†'
builtin     tab.selected                Selected                   -           -          -         -
builtin     tab.events                  Events                     -           -          -         -
config      open_item_in_codium         Open in VSCodium           shell       target     joined    hotbar:4 'ç'
config      open_in_daisydisk           Open/scan with DaisyDisk   shell       target     per_row   -
config      pick_markdown_in_codium     Pick markdown (Codium)     filepicker  target     -         -
config      add_log_to_note             Add log to note            note        target     -         hotbar:3
config      open_base_in_editor         Open base dir in editor    shell       workspace  -         -
```

- `SOURCE` column shows where the action comes from:
  `builtin` (no override), `config` (user-defined custom action),
  `overridden` (built-in with a `label` override in config).
- `LABEL` is the *effective* label after overrides. Pass
  `--show-defaults` to also print the system default alongside
  overridden labels.
- `KIND` / `SCOPE` / `MULTI` are blank (`-`) for built-ins —
  their behavior lives in code, not in the user-visible schema.
- `BOUND` column shows user-configured bindings only — hotbar slot
  (`hotbar:N`, 1-indexed) and any keys. Hardcoded UI keys
  (e.g. `enter` to open the selected row, arrow keys to navigate)
  are part of the application, not the bindings system, and are not
  shown here.
- Filter flags: `--source builtin|config|overridden`,
  `--unbound` (only show actions with no binding), `--bound`,
  `--view active|archive`.

This doubles as documentation: every overridable id surfaces here.

## Code changes required (non-trivial)

This is a structural refactor — touch points:

1. **`config/workspace.py`** — replace `load_custom_actions` /
   `load_custom_hotkeys` with `load_actions(data)` returning a
   `dict[str, ActionDef]`, plus `load_hotbar(data)` and
   `load_keys(data)`. Validate:
   - Built-in id entries may carry only `label`; any other field is
     a load-time error with a clear message
     (e.g. *"`archive` is built-in; only `label` is overridable"*).
   - Custom action entries must declare `kind`; kind-specific
     required fields present.
   - Template vars valid for given `scope`/`multi`.
   - Each binding's `action` resolves to an action id.
   - No duplicate keys / hotbar slots.

2. **`core/constants.py`** — rename `ACTION_SHORT_HELP` to
   `BUILTIN_ACTIONS: dict[str, BuiltinActionMeta]` with
   `default_label`, `help_text`, `default_confirm`, `view_scope`
   etc. — these live in code (not YAML), and define the immutable
   behavior of each built-in. The user-facing override in YAML is
   limited to `label`.

3. **`ui/context.py`** — store the merged action map on
   `RuntimeContext`. Merge happens at config-load time so the rest
   of the UI consumes a single uniform shape:
   - Start with `BUILTIN_ACTIONS` (with their hard-coded behavior).
   - For each entry in `actions:`:
     - Id matches a built-in: allowed only if the entry contains
       *only* `label` (label override). Any other field
       (`kind`, `scope`, `multi`, `command`, …) → load-time error
       (*"`<id>` is built-in; only `label` is overridable"*).
     - Id is new: must declare `kind`; treated as a custom action.

4. **`ui/actions/action_items.py`** — drop the implicit-decoration
   logic. Render `(filepicker)` / `(note)` from `action.kind` at
   menu-render time (still in code, but now derived rather than
   tied to which YAML fields are present).
   `valid_action_items()` builds its list from the merged action
   map, filtered by view-scope / target eligibility.
   `run_custom_action()` becomes `dispatch_action()`, switches on
   `kind`, uses the new template vars (`path` vs `paths`).

5. **`ui/app.py`** — replace `_dispatch_hotkey_target`'s
   prefix-string switch with a single
   `dispatch_action(action_id)`. Side tabs are dispatched through
   `tab.<name>` action ids. `_toggle_hotbar_target_from_palette`
   writes to the new ordered `hotbar:` list (insert/move/remove,
   preserving index for unchanged entries).

6. **`config/prefs.py`** — `save_custom_hotkeys` becomes
   `save_hotbar` + `save_keys` (or one combined `save_bindings`).

7. **CLI** — add `b help actions` (`commands/help.py` or
   `commands/actions.py`) producing the table sketched above.
   Filters: `--source`, `--bound`, `--unbound`, `--view`.

8. **`README.md`** — rewrite the `Custom Action Hotkeys` section
   end-to-end. Drop `loop_on_multi`, `scope: global`,
   `{{ full_path }}` magic. Document `kind`, `scope`,
   `multi`, `path` vs `paths`, `_q` rule, `per_row` selection
   ordering, and filepicker dispatch semantics.

9. **Migration** — none needed (user opted out of compatibility).
   Tests for the new schema replace the old ones.

## Behavior notes (must be documented)

These are decisions worth calling out explicitly in user-facing docs:

- **`multi: per_row` runs in selection order.** Top-to-bottom of
  the visible list at dispatch time. Stable, intentional. If the
  ordering matters to you (e.g. running a chain of commits), order
  your selection accordingly.
- **Filepicker on multi-selection.** The `list` template runs once
  per selected row, candidates are merged into a single fuzzy list,
  the user picks one entry, `command` runs once. This is *not*
  per-row dispatch of `command` — the picker's UX is "pick one
  thing, do one thing". `multi:` is not exposed on `kind:
  filepicker`.
- **`scope: workspace`** (the action does not need a row context).
  Replaces today's `scope: global`. The naming change is
  deliberate — "workspace" describes what's in scope.
- **Built-ins are immutable except for label.** No `confirm`
  override, no `view_scope` override, no `kind` override. The
  reasoning: built-ins ship with code that depends on those values;
  letting the user change them invites action-specific bugs that
  are hard to debug. If you need different behavior, define a
  custom action.

## Future extensions (slots reserved, no code now)

Fields/kinds the schema is designed to grow into. Each one sits in a
named slot already documented in the field reference; they're listed
here as the explicit roadmap of what we don't have to build today
but won't have to redesign for either.

- **`when:` predicate** — e.g. `target.archived`, `count > 1`,
  `view == 'archive'`. Filters when an action shows in the menu and
  whether bindings dispatch.
- **`icon:` glyph** — small unicode/emoji rendered next to the
  label in the menu.
- **`group:` category** — group actions under headings in the
  picker.
- **Structured `confirm:`** — the map form sketched in the
  *confirm:* section (prompt + default + inputs). Coexists with the
  string-or-bool form.
- **`label_by_view:`** — different label per view
  (e.g. `{ active: Box up, archive: Restore from box }`).
- **`kind: chain`** — `steps: [action_id, ...]` macros that run a
  sequence of other actions.
- **Structured `keys:` `when:`** — same predicate language applied
  to bindings (only dispatch in some context).
