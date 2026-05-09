# Config redesign — `actions` and `bindings`

Single-user proposal. No backwards compatibility.
Goal: one place per fact, no duplication, every action (built-in or
custom) addressable by the same id, hotbar order explicit, dispatch
validated, action template clean and orthogonal.

WIP is **out of scope** of this redesign — it's a quick-jump favorites
system, not an action system. Keep the existing `wip.hotkeys` section.

## Implementation status

> Source of truth for "where is this work?" Read this section first.
> Update it at the end of every phase.

| Phase | Status      | Notes |
|-------|-------------|-------|
| 1. Built-in action registry           | not started | — |
| 2. Action data model + merged map     | not started | — |
| 3. Template engine v2                 | not started | — |
| 4. Dispatch refactor                  | not started | — |
| 5. New schema (`actions:` / `hotbar:` / `keys:`) | not started | — |
| 6. Side-tab auto-registration + eligibility checks | not started | — |
| 7. Discoverability (`b help actions`, context view) | not started | — |
| 8. README rewrite + final cleanup     | not started | — |

**Currently active phase:** none. Start with Phase 1.

**Phase log** (append a one-liner per completed phase: date, anything
surprising encountered that the next phase should know about):

- _none yet_

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

Three concepts:

- **Action** — a thing that can be invoked. Built-in or custom.
  Defined once; referenced by id.
- **Hotbar** — an ordered list of *target-scope* actions. The
  currently-active entry is what *Enter on the focused row* runs.
  Cycled with `ctrl+@`. Not a favorites bar.
- **Keys** — a flat key → action map for global keyboard shortcuts.
  Fires regardless of row focus. Used for workspace-scope actions,
  tab jumps, and target-scope shortcuts that you want available
  even when Enter is bound to something else.

Both hotbar and keys reference actions by id; neither re-defines
them.

### Built-in vs custom

- **Built-in actions** (`archive`, `delete`, `open_selected`,
  `notes_create`, `tags_set`, `restore`, `pack`, `unpack`,
  `toggle_pack`, `set_desc`, `rename_item`, `refresh_cache`,
  `full_reconcile`, `reload_global_config`, `edit_global_config`,
  `reconcile_all_cache`, `reconcile_selection_cache`,
  `review_meta`, `rename_meta_ext`, `readme_create`, `readme_edit`,
  `notes_open`, `suffix_set`, …) are implemented in code. The user
  may override **`label`** and **`confirm`** on built-ins; nothing
  else. Behavior, scope, multi-mode, view-scope, kind, command,
  etc. are fixed in code.
- **Custom actions** are user-defined and have the full action
  template (`kind`, `scope`, `multi`, `command`, `confirm`, …).
- **Side-tab actions** (`tab.<top>` / `tab.<top>.<child>`) are
  auto-registered built-ins for tab navigation. They never need
  confirmation; only `label` is overridable on a tab action.
- **Id collisions are rejected at load time.** A custom action
  whose id matches a built-in id is an error — built-in ids are
  reserved. To get different behavior than a built-in, define a
  custom action under a different id and bind your hotbar/keys to
  the new id.

### `actions:` map

```yaml
actions:

  # ---- built-in: only `label` and `confirm` are overridable ----
  archive:        { label: Archive }
  delete:
    label: Delete forever
    confirm: "Delete {{ count }} project(s) from {{ base_dir }}?"
  open_selected:  { label: Open in tmux }
  notes_create:   { label: New note }
  tags_set:       { label: Tags… }

  # ---- side-tab (built-in too — auto-registered, label override only) ----
  # Tab ids mirror the hierarchical tab layout: `tab.<top>` for a
  # top-level tab, `tab.<top>.<child>` for a sub-tab.
  tab.selected:        { label: Selected }
  tab.info.events:     { label: Log }
  tab.settings.global: { label: Global config }

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

| Field      | Type        | Meaning                                                                 |
|------------|-------------|-------------------------------------------------------------------------|
| `label`    | str         | Display name. Built-ins use the system default if absent.               |
| `confirm`  | bool / str  | `true` → action's default prompt; `false`/absent → no prompt; string → custom prompt (template variables allowed; see below). **On built-ins:** only the *string* form is accepted (it overrides the prompt **text**). Whether the action prompts at all is fixed in code per built-in (e.g. `delete` always prompts, `refresh_cache` never does). `confirm: true` / `confirm: false` on a built-in is a load-time error. |

**Custom actions only** (rejected at config-load time on a built-in id):

| Field        | Type                       | Meaning                                                              |
|--------------|----------------------------|----------------------------------------------------------------------|
| `kind`       | enum                       | `shell`, `filepicker`, `note`. Required.                             |
| `scope`      | `target` / `workspace`     | Does the action need a row? Default `target`.                        |
| `multi`      | `joined` / `per_row`       | How the action dispatches against the current selection. `joined` (default) → run **once**, with list-form vars (`paths_q`, `names_q`, …) resolved to the full selection (1 or N rows). `per_row` → run **once per selected row**, with per-row vars (`path_q`, `name`, …) resolved per iteration. Independent of selection count: the variable family is determined by the action's declaration, not by how many rows the user picked. Only meaningful on `kind: shell`; ignored on `kind: filepicker` and `kind: note`. |
| `when`       | str (predicate)            | Predicate; only show/dispatch when condition holds. *(future, slot reserved)* |
| `hidden`     | bool                       | Hide from action picker; still dispatchable via key/hotbar.          |
| `view_scope` | list[str]                  | Which views the action applies to (`[active]`, `[archive]`; default both). |
| `icon`       | str                        | Small glyph rendered in menu. *(future, slot reserved)*              |
| `group`      | str                        | Category in the action menu. *(future, slot reserved)*               |

`kind`-specific fields (validated against `kind`, custom actions only):

| `kind`        | Required fields              | Allowed `scope`           | Notes                              |
|---------------|------------------------------|---------------------------|------------------------------------|
| `shell`       | `command`                    | `target` *or* `workspace` | Template; vars below.              |
| `filepicker`  | `list`, `command`            | `target` only             | `list` emits candidates per row, results merged; user picks once; `command` runs once with `{{ selection }}`. **`multi:` is not exposed** — semantics are fixed: collection phase loops on multi-selection, dispatch is single-shot. |
| `note`        | `op`                         | `target` only             | Built-in op enum. Only `add_log` today. Each `op` value may appear at most once across all actions. |

### Template variables

`{{ path }}` (single-row) and `{{ paths }}` (list-form) are now
distinct; no more polymorphic `{{ full_path }}`. Every variable
that can land in a shell command has a `_q` form (shell-quoted).
The bare form returns the raw value (useful for confirm prompts
and labels).

The set below is the v1 surface — generous on purpose, since adding
more later requires no schema change. Validation rule still holds:
referencing a variable not available in the action's `scope`/`multi`
context is a config-load error.

#### Two dispatch families: per-row vs list-form

The variable that resolves depends on what the action *declared*
in its `multi:` field, **not** on how many rows the user happens to
have selected:

- **`multi: per_row`** — the action runs **once per selected row**.
  Inside each iteration, per-row variables resolve (`path`, `name`,
  `branch`, …). Selecting one row dispatches the action once;
  selecting N rows dispatches it N times in selection order. List-
  form vars (`paths`, `paths_q`, …) are not available.
- **`multi: joined`** (default) — the action runs **once total**,
  with list-form variables resolved to the full selection. Selecting
  one row → list of one. Selecting N rows → list of N. The variable
  is the same in both cases; it just contains a different number of
  items. Per-row vars (`path`, `name`, …) are not available.

That second point is the important one: `{{ paths_q }}` works for
*any* selection size ≥ 1. With one row selected,
`'$EDITOR {{ paths_q }}'` resolves to `$EDITOR "/path/to/one"`. With
three rows, it resolves to
`$EDITOR "/path/to/a" "/path/to/b" "/path/to/c"`. The same action
template, the same variable, the right shape in both cases — that's
the whole point of the joined family.

Worked examples (assume the action is `open_item_in_editor`,
`scope: target`, `multi: joined`,
`command: '$EDITOR {{ paths_q }}'`):

| Rows selected | Resolved command                                  |
|---------------|---------------------------------------------------|
| 1 (`/p/a`)    | `$EDITOR "/p/a"`                                  |
| 2 (`/p/a`,`/p/b`) | `$EDITOR "/p/a" "/p/b"`                       |
| 3 (`/p/a`,`/p/b`,`/p/c`) | `$EDITOR "/p/a" "/p/b" "/p/c"`         |

For `open_in_daisydisk` (`multi: per_row`,
`command: 'open -n -a DaisyDisk {{ path_q }}'`) the engine instead
runs the command once per selected row, with `{{ path_q }}` set to
that row's path on each iteration.

#### Per-row family (available on `multi: per_row` actions and inside `kind: filepicker`'s per-row `list:` template)

Resolved fresh on each iteration of the dispatch loop.

| Var                                       | Meaning                                    |
|-------------------------------------------|--------------------------------------------|
| `{{ path }}` / `{{ path_q }}`             | Absolute project path.                     |
| `{{ rel_path }}` / `{{ rel_path_q }}`     | Path relative to base_dir.                 |
| `{{ name }}` / `{{ name_q }}`             | Project folder name.                       |
| `{{ parent_path }}` / `{{ parent_path_q }}` | Parent directory of the project.         |
| `{{ branch }}` / `{{ branch_q }}`         | Git branch (`-` if not a repo).            |
| `{{ dirty }}`                             | Git dirty marker (`""`, `*`, `~`, `?`).    |
| `{{ description }}` / `{{ description_q }}` | `.base.yaml` description.                |
| `{{ tags }}`                              | Comma-joined tags.                         |
| `{{ tags_space }}` / `{{ tags_space_q }}` | Space-joined tags (handy for shell loops). |
| `{{ properties }}`                        | Comma-joined property keys.                |
| `{{ suffix }}`                            | `tmp`, `fork`, or empty.                   |
| `{{ wip }}`                               | `1` if WIP, `0` otherwise.                 |
| `{{ archived }}`                          | `1` if archived, `0` otherwise.            |
| `{{ packed }}`                            | `1` if packed-archive `.tgz`, `0` otherwise. |
| `{{ created }}` / `{{ created_iso }}` / `{{ created_ts }}` | Creation date (`YYYY-MM-DD` / ISO / unix). |
| `{{ last_modified }}` / `{{ last_modified_iso }}` / `{{ last_modified_ts }}` | Last-modified date in same three forms. |
| `{{ last_opened }}` / `{{ last_opened_iso }}` / `{{ last_opened_ts }}` | Last-opened date (empty/0 if never opened). |
| `{{ archived_at }}` / `{{ archived_at_iso }}` / `{{ archived_at_ts }}` | Archive timestamp (empty/0 when not archived). |
| `{{ size_bytes }}` / `{{ size_human }}`   | Directory size.                            |
| `{{ note_path }}` / `{{ note_path_q }}`   | Resolved note path for this row (per `notes.path_template`). |

#### List-form family (available on `multi: joined` actions)

Resolved once with the full current selection. **Works at any
selection size ≥ 1** — selecting one row produces a list of one,
selecting N rows produces a list of N. The action template is the
same; only the count of items in the resolved value changes.

| Var                                       | 1 selected (e.g. `/p/a`) | N selected (e.g. `/p/a`, `/p/b`) |
|-------------------------------------------|--------------------------|----------------------------------|
| `{{ paths }}`                             | `/p/a`                   | `/p/a /p/b`                      |
| `{{ paths_q }}`                           | `"/p/a"`                 | `"/p/a" "/p/b"`                  |
| `{{ rel_paths }}` / `{{ rel_paths_q }}`   | (same shape, relative to `base_dir`) |                      |
| `{{ names }}` / `{{ names_q }}`           | (same shape, project names instead of paths) |              |

#### Filepicker

| Var                                       | Meaning                                    |
|-------------------------------------------|--------------------------------------------|
| `{{ selection }}` / `{{ selection_q }}`   | The candidate the user picked.             |

#### Always (workspace context — usable everywhere, including `confirm:` and `keys`/`hotbar` labels)

| Var                                       | Meaning                                    |
|-------------------------------------------|--------------------------------------------|
| `{{ base_dir }}` / `{{ base_dir_q }}`     | Workspace root.                            |
| `{{ base_name }}`                         | Basename of `base_dir`.                    |
| `{{ archive_dir }}` / `{{ archive_dir_q }}` | Archive directory.                       |
| `{{ active_count }}`                      | Number of active projects in the workspace. |
| `{{ archive_count }}`                     | Number of archived projects.               |
| `{{ wip_count }}`                         | Number of WIP-marked projects.             |
| `{{ count }}`                             | Number of currently selected rows in the active view (0 if no selection). Reflects the visible selection independently of action `scope` — useful in `confirm:` strings on `scope: workspace` actions. |
| `{{ view }}`                              | Current view: `active` or `archive`.       |
| `{{ filter }}` / `{{ filter_q }}`         | Current filter expression text (empty if no filter). |
| `{{ now }}` / `{{ now_iso }}` / `{{ now_ts }}` | Wall-clock at dispatch time (`YYYY-MM-DDTHH:MM:SS` local / ISO with offset / unix). |
| `{{ today }}`                             | `YYYY-MM-DD` (local).                      |
| `{{ user }}`                              | `$USER` (or runtime equivalent).           |
| `{{ home }}` / `{{ home_q }}`             | `$HOME`.                                   |

> Variables defined in the `variables:` config section
> (e.g. `_COLOR_CORE`, `_NOTES_ROOT`) are **not** available as
> action template vars. Those are property/notes config interpolations
> only. Reusing them here would conflict with selection-derived
> variables and is intentionally avoided.

### Side panel: add a "context" view for live template variables

Today's `info` side tab holds cache/process data. Add a new sub-tab
that shows **every template variable that would resolve right now**
if an action dispatched against the current selection. Two columns:
variable name, current value. Group rows by availability — per-row,
joined, filepicker, always — so the user can see at a glance what's
available where. Updates live as the selection or filter changes.

Two equivalent placements; pick one (the user's preference, expressed
in the redesign comment, is the rename):

- **Add it as a sub-tab under the existing panel:** `info > stats`
  (action id `tab.info.stats`). Smallest change.
- **Rename the panel** `info` → `stats` and place the new view as
  `stats > context` (action id `tab.stats.context`). All current
  `info` sub-tabs (`cache`, `processes`, …) move under
  `tab.stats.*`. A bit more work, but the panel name then
  describes what's actually in there. Recommended.

Either way: this is the discovery surface for "which variables
exist". It beats grepping the README.

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

`confirm:` is overridable on **both** built-in and custom actions:
- **Built-ins** accept only a string (custom prompt text). Whether
  the action prompts at all is fixed in code (`delete` always
  prompts, `refresh_cache` never does). `true`/`false` on a built-in
  is a load-time error.
- **Custom actions** accept the full `true` / `false` / string form
  (`true` → default prompt, `false`/absent → no prompt, string →
  custom prompt).

```yaml
# built-in: rephrase the delete prompt in your own words
delete:
  label: Delete forever
  confirm: "Drop {{ count }} project(s) under {{ base_dir }}?"

# custom: opt into a prompt with a templated text
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

### `hotbar:` — Enter-dispatch chooser for the focused row

The hotbar is **not** a favorites bar. It's the row-default-action
selector: when the projects table has focus and the user presses
*Enter* on a row, the currently-active hotbar entry is dispatched
against that row. The active entry is cycled with `ctrl+@`. The
hotbar widget shows the currently-selected entry so it's obvious
what Enter will do.

Eligibility:

- **Only `scope: target` actions belong on the hotbar.** The whole
  point is "what should Enter do for *this row*" — a workspace-
  scope action (`open_base_in_editor`) or a tab-jump
  (`tab.info.events`) doesn't operate on a row, so putting one on
  the hotbar is meaningless. Such entries are rejected at
  config-load time.
- Built-in and custom target actions are both fine
  (`open_selected`, `notes_create`, `add_log_to_note`,
  `open_item_in_codium`, `pick_markdown_in_codium`, …).
- Filepicker and note actions are eligible — they're target-scope
  and have well-defined Enter semantics ("pick a file from this
  row" / "append a log to this row's note").

```yaml
hotbar:
  - open_selected
  - notes_create
  - add_log_to_note
  - { action: open_item_in_codium, label: codium }
```

- Position in the list = on-screen position (1, 2, 3, …).
- Item is either a string (action id) or a map with allowed
  overrides.
- Allowed overrides on a hotbar entry: `label` only.
- **Hotbar entries do not carry keys.** Keyboard shortcuts always
  live in the top-level `keys:` map. If you want a hotbar slot
  *and* a keyboard shortcut for the same action, list it in both
  (the action id is the only link they share).
- For workspace-scope and tab-jump actions, use `keys:` — those
  bindings fire regardless of which row is focused.

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
  (`when:` reserved for future, see *Future extensions*.)
- A key may appear at most **once** in `keys:`.
- The same action id may legally appear in both `hotbar:` and
  `keys:` — they are independent surfaces (the hotbar binds the
  action to *Enter* via the cycle selector; `keys:` binds it to a
  fixed key chord).

### Side-tab navigation

Side tabs are hierarchical (two levels). Today's dispatch uses
`tab:<top>/<child>` (e.g. `tab:side_main/selected` or
`tab:side_main` for a top-only jump). New: side tabs are
auto-registered as actions with stable, hierarchical, dotted ids
that mirror the menu structure:

- `tab.<top>` — jump to a top-level tab (no child reset).
- `tab.<top>.<child>` — jump to a top-level tab and select a child.

Concrete examples (real tab structure):

| Action id              | Where it lands                       |
|------------------------|--------------------------------------|
| `tab.selected`         | top: *Selected*                      |
| `tab.selected.overview`| top: *Selected*, child: overview     |
| `tab.info`             | top: *Info*                          |
| `tab.info.events`      | top: *Info*, child: events ("Log")   |
| `tab.info.cache`       | top: *Info*, child: cache            |
| `tab.settings`         | top: *Settings*                      |
| `tab.settings.global`  | top: *Settings*, child: global       |

Like other built-ins, only `label` is overridable on a tab action.
(Tabs never need `confirm`.) Tab actions are **not eligible for
the hotbar** — they don't operate on the focused row. Bind them via
`keys:` instead:

```yaml
actions:
  tab.info.events: { label: Log }

keys:
  'ctrl+l': tab.info.events
```

No magic prefixes anywhere; no `tab:` string-prefix routing.

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
  - { action: open_item_in_codium, label: codium }

keys:
  '†': tags_set
  'ç': open_item_in_codium

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
  on flag") is split into two clear families:
  - `{{ path_q }}` for `multi: per_row` actions — single absolute
    path, the row's own.
  - `{{ paths_q }}` for `multi: joined` actions — a list of
    quoted paths regardless of selection size: `"/p/a"` for one
    selected row, `"/p/a" "/p/b"` for two, etc. Same template, the
    right shape every time.
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
overridden  tab.info.events             Log                        -           -          -         -
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
   - Built-in id entries may carry only `label` and `confirm`; any
     other field is a load-time error with a clear message
     (e.g. *"`archive` is built-in; only `label` and `confirm` are
     overridable"*).
   - On built-in id entries, `confirm` must be a string. Bool
     `confirm: true` / `confirm: false` is rejected (the
     whether-to-prompt default is fixed in code).
   - Custom action entries must declare `kind`; kind-specific
     required fields present.
   - Template vars valid for given `scope`/`multi`; bare-form var
     in a `command:` template emits a quoting warning.
   - Each binding's `action` resolves to an action id.
   - Hotbar entries reference only `scope: target` actions (no
     workspace-scope, no `tab.*`). Load-time error otherwise:
     *"`<id>` cannot be on the hotbar — only target-scope actions
     are eligible. Bind it via `keys:` instead."*
   - Hotbar entries carry no `key:` field.
   - No duplicate keys in `keys:`.

2. **`core/constants.py`** — rename `ACTION_SHORT_HELP` to
   `BUILTIN_ACTIONS: dict[str, BuiltinActionMeta]` with
   `default_label`, `help_text`, `default_confirm`, `view_scope`
   etc. — these live in code (not YAML), and define the immutable
   behavior of each built-in. The user-facing override in YAML is
   limited to `label`.

3. **`ui/context.py`** — store the merged action map on
   `RuntimeContext`. Merge happens at config-load time so the rest
   of the UI consumes a single uniform shape:
   - Start with `BUILTIN_ACTIONS` (with their hard-coded behavior,
   including `default_confirm_prompt`).
   - For each entry in `actions:`:
     - Id matches a built-in: allowed only if the entry contains
       *only* `label` and/or `confirm` (presentation overrides).
       Any other field (`kind`, `scope`, `multi`, `command`, …) →
       load-time error.
     - Id is new: must declare `kind`; treated as a custom action.
   - `confirm` override semantics: replaces the prompt text only.
     Whether to prompt at all is fixed in code per built-in
     (e.g. `delete` always prompts; `refresh_cache` never does).

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
   the hierarchical `tab.<top>` / `tab.<top>.<child>` action ids
   (resolved by splitting the id on `.`).
   `_toggle_hotbar_target_from_palette` writes to the new ordered
   `hotbar:` list (insert/move/remove, preserving index for
   unchanged entries).

6. **`config/prefs.py`** — `save_custom_hotkeys` becomes
   `save_hotbar` + `save_keys` (or one combined `save_bindings`).

7. **CLI** — add `b help actions` (`commands/help.py` or
   `commands/actions.py`) producing the table sketched above.
   Filters: `--source`, `--bound`, `--unbound`, `--view`.

8. **`ui/side/`** — add a *context* view (`tab.info.stats` or, if
   renaming, `tab.stats.context`) that lists every available
   template variable and its currently-resolved value, grouped by
   availability (per-row / joined / filepicker / always). Live
   refresh on selection / filter change. The data source is the
   same context-builder used by `dispatch_action()`.

9. **`README.md`** — rewrite the `Custom Action Hotkeys` section
   end-to-end. Drop `loop_on_multi`, `scope: global`,
   `{{ full_path }}` magic. Document `kind`, `scope`,
   `multi`, `path` vs `paths`, `_q` rule, `per_row` selection
   ordering, filepicker dispatch semantics, the full template
   variable table, and the context side-tab.

10. **Migration** — none needed (user opted out of compatibility).
    Tests for the new schema replace the old ones.

## Behavior notes (must be documented)

These are decisions worth calling out explicitly in user-facing docs:

- **The hotbar is the Enter-dispatch chooser.** Each entry is a
  candidate for "what Enter does on the focused row". Cycle the
  active entry with `ctrl+@`. The widget shows the currently-active
  one. Only `scope: target` actions are eligible (workspace-scope
  actions and tab-jumps don't operate on a row). Use `keys:` for
  those.
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
- **Built-ins are immutable except for `label` and `confirm`.**
  No `view_scope` override, no `kind` override, no `command`
  override. The reasoning: built-ins ship with code that depends
  on those values; letting the user change them invites
  action-specific bugs that are hard to debug. The two presentation
  knobs that are safe to expose — what the action is called, and
  what the prompt asks — are user-overridable. If you need
  different *behavior*, define a custom action under a different
  id.

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

## Implementation plan

The redesign ships in 8 phases. Each phase is a self-contained
work unit:

- **Self-contained:** read the *Implementation status* section above
  to know which phase is active, then jump to that phase's heading.
  No prior context outside this file is needed. The phase's brief
  references other sections of this same file by name (e.g. *Field
  reference*, *Template variables*).
- **Testable in isolation:** every phase ends with a Done-when
  checklist that the suite + lint + manual smoke must satisfy.
- **Mergeable:** the app must boot and behave correctly between
  phases. No phase leaves the codebase broken.

**Working procedure for every phase:**

1. Read this file's *Implementation status* table — confirm you're
   on the active phase.
2. Read the phase's brief end-to-end before writing code.
3. Implement the listed tasks.
4. Add the listed tests; run `uv run pytest` (must be green).
5. Run `uv run ruff check src/homebase/ tests/` (must be clean).
6. Manual smoke per the phase's *Done when*.
7. **Update this TODO file** in the same commit as the code:
   - Mark the phase row as `done` in the status table.
   - Append a one-liner to the *Phase log*.
   - Set the next phase as the *Currently active phase*.
8. Commit.

Layering and style rules in `AGENTS.md` apply to every phase
without restating: `core/` imports nothing else from the package;
no bare `except`; no `from X import *`; tests use `tmp_path`, not
mocks of fs/sqlite; new pure-data helpers in `*_utils.py` /
`*_engine.py` get unit tests.

---

### Phase 1 — Built-in action registry

**Goal.** Build a single canonical metadata registry for every
existing built-in action. No user-visible behavior change. This
unlocks all later phases (label override, view-scope, confirm
defaults).

**Files.**
- `src/homebase/core/models.py`
- `src/homebase/core/constants.py`
- `src/homebase/ui/app.py`
- `src/homebase/ui/actions/action_items.py`

**Tasks.**

1. In `core/models.py`, add a `BuiltinActionMeta` dataclass:
   - `id: str`
   - `default_label: str`
   - `help_text: str`
   - `scope: Literal["target", "workspace"]`
   - `view_scope: tuple[str, ...]` — subset of `("active", "archive")`.
   - `default_confirm_prompt: str | None` — `None` means "never
     prompts"; non-`None` is the default prompt text. (User
     overrides under `confirm:` replace this string.)
   - `kind: Literal["builtin"]` (constant, for symmetry with the
     `Action` shape introduced in Phase 2).
2. In `core/constants.py`, replace `ACTION_SHORT_HELP: dict[str, str]`
   with `BUILTIN_ACTIONS: dict[str, BuiltinActionMeta]`. Move every
   id from today's `ACTION_SHORT_HELP` over with full metadata.
   Source of truth for `view_scope`: today's `_VIEW_CONFIG_DEFAULT`
   in `ui/app.py` (active-only / archive-only / both). Source for
   `default_confirm_prompt`: code paths that prompt before running
   (`delete`, etc.). Source for `scope`: target if the action runs
   on row(s); workspace if it doesn't.
3. Migrate consumers:
   - `ui/app.py` import `BUILTIN_ACTIONS` instead of
     `ACTION_SHORT_HELP`.
   - `action_help_text(action_id, label, *, action_short_help=…)`
     keeps its signature for now but the dict passed in is built
     from `BUILTIN_ACTIONS`'s `help_text` fields.
   - `valid_action_items` reads `default_label` from
     `BUILTIN_ACTIONS` (still merged with `_VIEW_CONFIG_DEFAULT`
     for the per-view extras until Phase 2 takes that over).
4. Don't touch `_VIEW_CONFIG_DEFAULT` yet — Phase 2 derives it
   from the registry. Keep both in sync this phase.

**Tests** (new file `tests/test_builtin_actions.py`):
- Every action id present in today's `ACTION_SHORT_HELP` has an
  entry in `BUILTIN_ACTIONS`.
- Every entry has non-empty `default_label` and `help_text`.
- `view_scope` matches what `_VIEW_CONFIG_DEFAULT` currently
  encodes for the same id.
- Existing tests stay green. Layering test stays green.

**Done when.**
- `uv run pytest` green.
- `uv run ruff check src/homebase/ tests/` clean.
- Manual smoke: `uv run b` opens, action menu (`ctrl+a`) shows the
  same items as before, hotbar still cycles, custom actions still
  dispatch.

**Update TODO.** Status table → Phase 1 = `done`; phase log entry;
*Currently active phase* → 2.

---

### Phase 2 — Action data model + merged action map

**Goal.** Define the unified `Action` shape and merge built-ins +
existing `custom_actions` into one map on `RuntimeContext`. UI
sites read from the merged map. The old YAML schema still loads —
this phase only changes the *shape* the app holds in memory.

**Files.**
- `src/homebase/core/models.py`
- `src/homebase/config/workspace.py` (or new `config/action_map.py`)
- `src/homebase/ui/context.py`
- `src/homebase/core/runtime_init.py`
- `src/homebase/ui/actions/action_items.py`
- `src/homebase/ui/app.py`

**Tasks.**

1. In `core/models.py`, add `Action` dataclass with the full schema
   per the *Field reference* tables: `id`, `label`, `kind`
   (`"builtin" | "shell" | "filepicker" | "note" | "tab"`),
   `scope`, `multi`, `command`, `list_command`, `op`,
   `confirm` (`bool | str | None`), `hidden`, `view_scope`,
   `source` (`"builtin" | "config" | "overridden"`).
2. Add `merge_actions(builtins, user_actions, custom_actions_legacy)
   -> dict[str, Action]`:
   - Start with built-ins → `Action(kind="builtin", source="builtin")`.
   - For each entry in `custom_actions_legacy` (the old YAML still
     parsed): if its `id` matches a built-in id, treat as a label
     override (`source="overridden"`). Otherwise build an `Action`
     with `kind` inferred from which fields are present (`command`
     → `shell`, `list_command`+`run_command` → `filepicker`,
     `note_command` → `note`).
   - Return the merged dict keyed by id. Custom actions inferred
     here use the legacy field names — Phase 5 cleans that up.
3. Add `RuntimeContext.actions: dict[str, Action]`. Populate in
   `runtime_init.runtime_init`.
4. Migrate consumers to read `app.ctx.actions`:
   - `valid_action_items()` builds its menu list from the merged
     map filtered by view-scope and target eligibility.
   - `custom_action_by_id(app, cid)` → `app.ctx.actions.get(cid)`
     (returns `Action`, not `dict`).
   - `custom_actions_for_scope(app, scope)` filters
     `app.ctx.actions` by `source != "builtin"` and matching
     scope.
5. Keep `app.custom_actions` as a derived list (Action objects with
   `source != "builtin"`) for any temporary callers; Phase 5
   removes it.
6. Build `_VIEW_CONFIG_DEFAULT` dynamically from `BUILTIN_ACTIONS`
   filtered by `view_scope`.

**Tests.**
- `tests/test_action_map.py` — merge with empty user actions
  returns built-ins; custom additions appear with `source="config"`;
  built-in id with a label override appears as
  `source="overridden"`.
- Existing tests stay green (action menu still shows same items,
  custom dispatch still works).

**Done when.**
- pytest green, ruff clean.
- TUI smoke: action menu unchanged; existing hotbar/custom_hotkeys
  still dispatch correctly.

**Update TODO.** Phase 2 = `done`; log; active phase → 3.

---

### Phase 3 — Template engine v2

**Goal.** Implement the per-row / list-form / filepicker / always
variable families, with quoting and load-time validation. Apply
to existing custom-action `command` / `list_command` / `run_command`
strings.

**Files.**
- `src/homebase/ui/actions/template.py` (new)
- `src/homebase/ui/actions/action_items.py`
- (later phases) `src/homebase/config/workspace.py` for validation

**Tasks.**

1. New module `ui/actions/template.py`:
   - `PER_ROW_VARS`, `LIST_VARS`, `FILEPICKER_VARS`, `ALWAYS_VARS`:
     the exact sets from the *Template variables* section of this
     file. Each variable has both a bare and (where shell-relevant)
     a `_q` form.
   - `build_per_row_context(app, row, base_dir) -> dict[str, str]`.
   - `build_list_context(app, rows, base_dir) -> dict[str, str]`
     (resolves `paths`, `paths_q`, `rel_paths`, `rel_paths_q`,
     `names`, `names_q`). Works for any selection size ≥ 1.
   - `build_filepicker_context(picked: str) -> dict[str, str]`.
   - `build_always_context(app, base_dir) -> dict[str, str]`
     (resolves `base_dir(_q)`, `archive_dir(_q)`, `archive_count`,
     `active_count`, `wip_count`, `count`, `view`, `filter(_q)`,
     `now(_iso/_ts)`, `today`, `user`, `home(_q)`, `base_name`).
   - `render_template(text: str, *contexts) -> str` — merge
     contexts, interpret `{{ var }}` and `${var}` via `string.Template.safe_substitute`. The `_q` variants come pre-quoted via `shlex.quote`.
   - `validate_template(text: str, allowed: set[str])
     -> list[str]` — return load-time error messages for any
     `{{ x }}` not in `allowed`. Also return a *warning* per bare
     (non-`_q`) variable found in a `command:` template (used at
     parse time to surface footguns; doesn't fail the load).
2. Migrate `custom_action_context` and `render_custom_command`
   from `action_items.py` to delegate to the new module.
3. Bridge for legacy `{{ full_path }}` (lives until Phase 5):
   - In a `multi: per_row` (or legacy `loop_on_multi: true`)
     context, expose `full_path` as an alias of `path_q` so
     existing user templates keep working.
   - In a `multi: joined` (legacy `loop_on_multi: false`) context,
     expose `full_path` as alias of `paths_q`.
   - Tag this bridge with a code comment `# REMOVE IN PHASE 5`
     so it's easy to find.

**Tests** (`tests/test_template.py`):
- Every variable name in each family resolves correctly for a
  representative row + workspace.
- `_q` quoting is `shlex.quote` style (round-trip safe).
- `validate_template` returns errors for unknown vars and the
  expected warning for unquoted vars.
- List context produces a list of one for one selected row, list of
  N for N — concrete:
  - 1 row `/p/a` → `paths_q` resolves to `"/p/a"`.
  - 2 rows `/p/a`, `/p/b` → `paths_q` resolves to `"/p/a" "/p/b"`.

**Done when.**
- pytest green, ruff clean.
- TUI smoke: every existing custom action still executes correctly.

**Update TODO.** Phase 3 = `done`; log; active phase → 4.

---

### Phase 4 — Dispatch refactor

**Goal.** One entry point for invoking any action:
`dispatch_action(app, action_id)`. Switches on `Action.kind`. The
old prefix-string `_dispatch_hotkey_target` collapses to a thin
shim that strips legacy prefixes and forwards.

**Files.**
- `src/homebase/ui/actions/dispatch.py` (new)
- `src/homebase/ui/app.py`
- `src/homebase/ui/actions/action_items.py`
- `src/homebase/ui/sync/git_refresh.py` and any other call sites
  for `run_custom_action`.

**Tasks.**

1. New module `ui/actions/dispatch.py`:
   - `dispatch_action(app, action_id: str) -> None`.
   - Resolve `Action` from `app.ctx.actions`; log error and bail
     on unknown id.
   - Switch on `action.kind`:
     - `builtin`: call `app._on_pick_actions(action_id)`.
     - `shell`: build context (per_row vs list-form per
       `action.scope`/`action.multi`), render template, launch via
       the existing `_start_managed_shell_command`. For `per_row`,
       loop in selection order.
     - `filepicker`: existing list-action flow (Phase 3 builders).
     - `note`: existing note flow with `op` enum.
     - `tab`: split `action_id` on `.` after the `tab.` prefix,
       call `app._jump_to_side_tab(top, child)`.
2. Replace `_dispatch_hotkey_target` body with a wrapper:
   - Accept `value` (legacy prefix-string OR plain action id).
   - Strip a leading `action:` or `action:custom:` prefix; strip
     `tab:<top>/<child>` → `tab.<top>.<child>`.
   - Call `dispatch_action(app, normalized_id)`.
3. Replace `run_custom_action` with `dispatch_action` at every
   call site.

**Tests** (`tests/test_dispatch.py`):
- Each kind dispatches correctly with a fake app providing the
  needed hooks.
- Legacy prefix strings (`action:archive`,
  `action:custom:open_item_in_codium`, `tab:side_main/selected`)
  normalize and dispatch the same as the new ids.

**Done when.**
- pytest green, ruff clean.
- TUI smoke: every existing binding (hotbar, custom_hotkeys keys)
  still triggers the correct effect.

**Update TODO.** Phase 4 = `done`; log; active phase → 5.

---

### Phase 5 — New schema: `actions:` / `hotbar:` / `keys:`

**Goal.** Replace the YAML shape. `custom_actions:` and
`custom_hotkeys:` are removed. Migrate the user's
`<base>/.homebase/config.yaml` in the same commit. Drop the
template bridge (`full_path` alias) from Phase 3.

**Files.**
- `src/homebase/config/workspace.py`
- `src/homebase/config/prefs.py`
- `src/homebase/cli/entry.py`
- `<base>/.homebase/config.yaml` (the user's actual config)
- `src/homebase/ui/actions/template.py` (remove the legacy bridge)

**Tasks.**

1. Implement `load_actions(data) -> dict[str, ActionDef]` per the
   *Field reference* tables in this file. Validation
   (load-time errors, exact-message guidance):
   - Built-in id entries may carry only `label` and `confirm`. Any
     other field → error
     (*"`<id>` is built-in; only `label` and `confirm` are
     overridable"*).
   - Built-in `confirm` must be a string (not bool).
   - Custom action entries require `kind`. kind-specific required
     fields present (`shell`→`command`, `filepicker`→`list`+
     `command`, `note`→`op`).
   - `note` `op` must be `add_log`. Each `op` value at most once.
   - `kind: filepicker` and `kind: note` require `scope: target`.
   - Template var availability: bare-form var in a command emits
     warning; unavailable var (per scope/multi) is an error.
2. Implement `load_hotbar(data) -> list[HotbarEntry]`. Each entry:
   `action: <id>`, optional `label:`. No `key:` field allowed.
   Validation: action exists; resolved `Action.scope == "target"`
   (else *"`<id>` cannot be on the hotbar — only target-scope
   actions are eligible. Bind it via `keys:` instead."*).
3. Implement `load_keys(data) -> dict[str, KeyEntry]`. Validation:
   no duplicate keys; action exists.
4. Delete `load_custom_actions` / `load_custom_hotkeys` and
   `validate_custom_hotkeys` once all callers are migrated.
5. Update `cli/entry.py` to load + validate the new shape.
6. `config/prefs.py`: add `save_hotbar(base_dir, list)` and
   `save_keys(base_dir, dict)`. Remove `save_custom_hotkeys`.
   `_toggle_hotbar_target_from_palette` now writes to the new
   ordered `hotbar:` list.
7. Migrate the user's config.yaml: rewrite `custom_actions:` /
   `custom_hotkeys:` into `actions:` / `hotbar:` / `keys:` per the
   *The current config rewritten* section above.
8. Remove the `full_path` bridge from `ui/actions/template.py`
   (the `# REMOVE IN PHASE 5` comments).

**Tests.**
- `tests/test_load_actions.py` — every validation error path,
  using `tmp_path` workspaces with synthetic config.yaml.
- `tests/test_load_hotbar.py` / `test_load_keys.py` — same.
- Update `tests/test_workspace_settings.py` (today's old
  `custom_actions` tests) — replace with new schema tests.

**Done when.**
- pytest green, ruff clean.
- TUI smoke against the migrated config: action menu, hotbar,
  keys all work as before.

**Update TODO.** Phase 5 = `done`; log; active phase → 6.

---

### Phase 6 — Side-tab auto-registration + binding eligibility

**Goal.** `tab.<top>` and `tab.<top>.<child>` ids are auto-
registered as built-in actions; built-in label/confirm overrides
applied at merge time; hotbar enforces scope=target eligibility at
runtime as well as load time.

**Files.**
- `src/homebase/core/constants.py`
- `src/homebase/ui/context.py`
- `src/homebase/config/workspace.py`
- `src/homebase/ui/app.py`

**Tasks.**

1. In `core/constants.py` (or a new `core/tab_actions.py` since
   tabs depend on UI structure), expose
   `discover_tab_actions(app_or_ctx) -> dict[str, BuiltinActionMeta]`.
   Walks the side-tab tree (the source of truth lives in
   `ui/side/`); produces an entry for each top-level tab and each
   child tab, with id `tab.<top>` or `tab.<top>.<child>` and
   `default_label` from the tab's existing label. `scope` is
   neither target nor workspace — add a third value
   `scope: "tab"` and document it in the *Field reference* (small
   schema patch — update *Field reference* in this file as part of
   this phase's commit).
2. Merge tab actions into `BUILTIN_ACTIONS` at runtime startup
   (not at module import — UI must exist).
3. Apply built-in label and confirm overrides during
   `merge_actions` (Phase 2's merge stub — flesh it out fully now).
4. Hotbar runtime safety net: if `_toggle_hotbar_target_from_palette`
   is asked to add an ineligible action (`scope != "target"`), log
   a runtime warning and refuse.
5. Update *Field reference* in this file: `scope` enum gains
   `"tab"`. Hotbar eligibility says only `scope: "target"` is
   allowed (already does).

**Tests.**
- `tests/test_tab_actions.py` — every visible tab produces an
  entry; ids match the documented `tab.<top>.<child>` format;
  dispatch routes to `_jump_to_side_tab` with the right args.
- `tests/test_action_map.py` (extend) — confirm override merges;
  ineligible hotbar candidates rejected.

**Done when.**
- pytest green, ruff clean.
- TUI smoke: pressing the key bound to `tab.info.events` jumps to
  the right place; hotbar palette refuses to add a tab.

**Update TODO.** Phase 6 = `done`; log; active phase → 7.

---

### Phase 7 — Discoverability surfaces

**Goal.** Two user-facing surfaces for "what actions exist and
where do they go":
- `b help actions` CLI command.
- Side-panel context view (live template-variable inspector).

**Files.**
- `src/homebase/commands/actions.py` (new) and CLI parser update
  in `cli/`.
- `src/homebase/ui/side/` — new sub-tab content module.

**Tasks.**

1. CLI: implement `b help actions` per the *`b help actions` —
   discoverability* section above. Filters: `--source`, `--bound`,
   `--unbound`, `--view`, `--show-defaults`.
   - Prints `SOURCE`, `ID`, `LABEL`, `KIND`, `SCOPE`, `MULTI`,
     `BOUND` columns.
   - `BOUND` reports `hotbar:N` (1-indexed) and any `keys:` entries
     bound to this id; hardcoded UI keys are excluded.
2. Side-panel context view: pick the placement (recommended:
   rename `info` → `stats`, add `tab.stats.context`). Reuse the
   Phase 3 context builders against the current selection. Two
   columns: variable name, current value. Group by per-row /
   list-form / filepicker / always.
3. Live update: rebind on selection change and filter change.

**Tests.**
- `tests/test_help_actions_cli.py` — snapshot the table for a
  representative config.
- `tests/test_side_context.py` — rendering against a mocked
  selection.

**Done when.**
- pytest green, ruff clean.
- `b help actions` runs and matches expectation; context tab
  shows live values that update with selection.

**Update TODO.** Phase 7 = `done`; log; active phase → 8.

---

### Phase 8 — README rewrite + final cleanup

**Goal.** User-facing documentation matches the implementation;
no vestigial code remains.

**Files.**
- `README.md`
- any code identified as dead during the previous phases.

**Tasks.**

1. Rewrite the `Custom Action Hotkeys` section of `README.md`:
   - Drop `loop_on_multi`, `scope: global`, `{{ full_path }}`.
   - Document `kind`, `scope` (`target` / `workspace` / `tab`),
     `multi`, the per-row vs list-form variable families, the
     `_q` rule, `per_row` selection ordering, filepicker dispatch
     semantics, hotbar's role as Enter-dispatch chooser.
   - Update top-level config sections list (replace
     `custom_actions` / `custom_hotkeys` with `actions` / `hotbar`
     / `keys`).
2. Refresh the *Full Config Example* in README to use the new
   shape end-to-end.
3. Search for and remove any code noted as dead in earlier
   phases (`run_custom_action` if all callers migrated; the
   `_HOTBAR_PALETTE_TAG` palette code if its semantics changed;
   etc.).
4. Final manual smoke against every example in the new README.

**Tests.**
- `tests/test_layering.py` still green.
- Any doctest-style example exercises (optional).

**Done when.**
- pytest green, ruff clean.
- README examples match the implementation; no broken references.
- No dead code remaining from the redesign.

**Update TODO.** Phase 8 = `done`; final phase log entry; mark
the redesign complete in the *Currently active phase* line
(*"Currently active phase: complete (date)"*).

---

## After Phase 8 — followups

These are explicitly out of scope for the redesign but worth
filing so they don't get lost:

- Implement the `when:` predicate (sketched in *Future
  extensions*).
- Implement `kind: chain` for action macros.
- Extend `confirm:` to the structured form (prompt + default +
  inputs).
- `label_by_view` / `icon` / `group` if/when needed.
