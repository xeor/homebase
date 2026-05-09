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

### `actions:` map

```yaml
actions:

  # ---- built-in: override only (label / confirm / hidden / when) ----
  archive:        { label: Archive }
  delete:         { label: Delete forever, confirm: true }
  open_selected:  { label: Open in tmux }
  notes_create:   { label: New note }
  tags_set:       { label: Tags… }

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

  # ---- side-tab jump (auto-registered; override here only if needed) ----
  tab.selected:    { label: Selected }
  tab.events:      { label: Events }
```

#### Field reference

Top-level (apply to every action):

| Field      | Type               | Meaning                                         |
|------------|--------------------|-------------------------------------------------|
| `label`    | str                | Display name. Built-ins use the system default if absent. |
| `kind`     | enum               | `shell`, `filepicker`, `note`, `tab`. **Required** for new (custom) actions; **forbidden** when overriding a built-in. |
| `scope`    | `target`/`workspace` | Does the action need a row? Default `target`. |
| `multi`    | `joined`/`per_row` | When scope=target and multiple rows selected, how to dispatch. Default `joined`. Ignored for `scope: workspace`. |
| `confirm`  | bool / str         | If true, prompt with the action's default. If a string, use it as the prompt. |
| `when`     | str (predicate)    | Only show/dispatch when condition holds. *(future)* |
| `hidden`   | bool               | Don't show in the action picker (still dispatchable via key/hotbar). |
| `view_scope` | list[str]        | Which views the action applies to (`[active]`, `[archive]`, default both). |

`kind`-specific fields (validated against `kind`):

| `kind`        | Required fields              | Notes                              |
|---------------|------------------------------|------------------------------------|
| `shell`       | `command`                    | Template; vars below.              |
| `filepicker`  | `list`, `command`            | `list` emits candidates; user picks; `command` runs with `selection`. |
| `note`        | `op`                         | Built-in op enum. Only `add_log` today. Each `op` value may appear at most once across all actions. |
| `tab`         | `target_main`, `target_child?` | Auto-registered for known tabs; entry is for label override. |

### Template variables

`{{ path }}` (single-row) and `{{ paths }}` (joined) are now distinct;
no more polymorphic `{{ full_path }}`.

| Var               | Available in           | Meaning                              |
|-------------------|------------------------|--------------------------------------|
| `{{ path }}`      | scope=target, multi=per_row | Absolute path of the current row.   |
| `{{ path_q }}`    | scope=target, multi=per_row | Same, shell-quoted.                  |
| `{{ paths }}`     | scope=target, multi=joined  | All selected paths, space-joined.    |
| `{{ paths_q }}`   | scope=target, multi=joined  | All selected paths, each shell-quoted, space-joined. |
| `{{ rel_path }}` / `{{ rel_path_q }}` | scope=target | Path relative to base_dir. (Per-row only; joined form not provided — niche.) |
| `{{ name }}`      | scope=target, multi=per_row | Project name.                        |
| `{{ branch }}`    | scope=target, multi=per_row | Git branch.                          |
| `{{ tags }}`      | scope=target, multi=per_row | Comma-joined tags.                   |
| `{{ properties }}`| scope=target, multi=per_row | Comma-joined property keys.          |
| `{{ base_dir }}` / `{{ base_dir_q }}` | always | Workspace root.                      |
| `{{ selection }}` / `{{ selection_q }}` | filepicker only | Picked candidate. |

Rules:
- A template that references a variable not available in the action's
  `scope`/`multi` context fails at config-load time with a clear error.
- `_q` suffix means shell-quoted. Use it for any value that lands
  inside a shell command. Validation can warn if you use a non-`_q`
  form in a `command:` template (likely a footgun).

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
- Long form: `key: { action: ..., label: ..., when: ... }`.
- Same key can't appear twice.
- A key already present on the hotbar is fine — they're independent
  ways to reach the same action.

### Side-tab navigation

Today: `target: tab:side_main/selected`. New: side tabs are
auto-registered as actions with stable ids
(`tab.selected`, `tab.events`, …). To change a tab's hotbar label, do:

```yaml
actions:
  tab.events: { label: Log }

hotbar:
  - tab.events
```

No magic prefixes anywhere.

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

## Code changes required (non-trivial)

This is a structural refactor — touch points:

1. **`config/workspace.py`** — replace `load_custom_actions` /
   `load_custom_hotkeys` with `load_actions(data)` returning a
   `dict[str, ActionDef]`, plus `load_hotbar(data)` and
   `load_keys(data)`. Validate:
   - `kind` is required for non-built-in ids; forbidden for built-ins.
   - `kind`-specific required fields present.
   - Template vars valid for given `scope`/`multi`.
   - Each binding's `action` resolves to an action id.
   - No duplicate keys / hotbar slots.

2. **`core/constants.py`** — rename `ACTION_SHORT_HELP` to
   `BUILTIN_ACTIONS: dict[str, BuiltinActionMeta]` with fields
   `default_label`, `help_text`, `default_confirm`, `view_scope`.
   This becomes the canonical list a user can override.

3. **`ui/context.py`** — store the merged action map (built-ins
   with overrides + custom additions) on `RuntimeContext`. The
   merge happens at config-load time so the rest of the UI consumes
   a single uniform shape.

4. **`ui/actions/action_items.py`** — drop the implicit-decoration
   logic. Render `(filepicker)` / `(note)` from `action.kind` at
   menu-render time (still in code, but now derived rather than
   tied to which YAML fields are present).
   `valid_action_items()` builds its list from the merged action
   map filtered by `view_scope` / target eligibility.
   `run_custom_action()` becomes `dispatch_action()`, switches on
   `kind`, uses the new template vars (`path` vs `paths`).

5. **`ui/app.py`** — replace `_dispatch_hotkey_target`'s
   prefix-string switch with a single
   `dispatch_action(action_id)`. Side tabs are dispatched through
   `kind: tab` actions. `_toggle_hotbar_target_from_palette` writes
   to the new ordered `hotbar:` list (insert/move/remove).

6. **`config/prefs.py`** — `save_custom_hotkeys` becomes
   `save_hotbar` + `save_keys`. The hotbar-toggle from the
   command palette appends/removes from the ordered list and
   preserves index for unchanged entries.

7. **`README.md`** — rewrite the `Custom Action Hotkeys` section
   end-to-end. Drop `loop_on_multi`, `scope: global`, and
   `{{ full_path }}` magic. Document `kind`, `scope`, `multi`,
   `path` vs `paths`, `_q` rule.

8. **Migration** — none needed (user opted out of
   compatibility). Tests for the new schema replace the old ones.

## Future-friendly hooks (cost: zero today, optional fields)

Already accommodated by the schema; no code now:

- `actions.<id>.icon` — small unicode/emoji shown in menu.
- `actions.<id>.confirm` — bool (default prompt) or string (custom
  prompt).
- `actions.<id>.when` — predicate, e.g. `target.archived`,
  `count > 1`, `view == 'archive'`.
- `actions.<id>.group` — categorize in the action menu.
- `kind: chain` with `steps: [action_id, ...]` for macros.
- `actions.<id>.label_by_view` — different label in active vs
  archive.
- `actions.<id>.hidden: true` — bind by key without showing in menu.

## Open questions

- **`view_scope` on built-ins.** Today some actions are active-only
  (`archive`) or archive-only (`restore`, `unpack`). Hardcoded in
  `_VIEW_CONFIG_DEFAULT`. Move to per-action `view_scope: [active]`
  in `BUILTIN_ACTIONS`, allow user override. Recommendation: yes —
  one place where the answer lives.

- **Built-in registry: enumerate or implicit?** I'd enumerate
  every built-in id in `core/constants.BUILTIN_ACTIONS` so the user
  can run `b help actions` to list every overridable id. Code stays
  the source of truth for default labels; YAML only overrides.

- **`confirm:` shape.** I'd allow:
  - `confirm: true` → use the action's default prompt.
  - `confirm: false` (or absent) → no prompt.
  - `confirm: "Really delete N projects?"` → custom prompt.

- **Should `multi: per_row` be invocation order strict (top→bottom of
  selection) or arbitrary?** Today's loop is selection order. I'd
  keep that; document it.

- **Filepicker + multi-selection.** Today the picker runs per-row
  when multiple are selected, with merged candidate list (one
  selection runs once at the end). This stays — the filepicker's
  inherent UX is "single final action". The `multi:` field on
  filepicker actions controls whether the *list-collection* phase
  loops or not. Recommendation: just document this behavior; do not
  expose `multi:` on `kind: filepicker` (force a fixed semantics).

- **`scope: workspace` naming.** Today's word is `global`. I prefer
  `workspace` because it's more descriptive — "this action targets
  the workspace, not a project". But `global` has the merit of being
  shorter and matches the existing CLI vocabulary in some places.
  Pick one and stick with it.
