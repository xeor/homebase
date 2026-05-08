# TODO

## Feature: Favorites-driven Enter Action + Query Header Action Strip

### Goal

Implement a favorites workflow where:

- `ctrl+p` command palette supports favorite toggle on `tab`
- Favorited commands are shown with a red star suffix in command palette
- Top query/header area is split into 2 aligned regions:
  - left region width aligned with main projects table
  - right region width aligned with side/info panel
- Right region shows a horizontal action list (favorite commands)
- Left/right keys cycle selected favorite action
- `enter` executes selected favorite action (instead of default open behavior)

---

## Architecture / Design Plan

### 1) Data model + persistence

Reuse existing `custom_hotkeys` entries as the persistence model for hotbar selection.

Config shape update (`<base>/.homebase/config.yaml`):

- extend each `custom_hotkeys` item with optional `hotbar: bool`
- existing optional field remains: `hotkey`
- existing required field remains: `target`
- validation rule: at least one of `hotkey` or `hotbar` must be set
- `hotbar: true` means this target appears in the top-right hotbar

Notes:

- `hotbar` and `hotkey` may both be set on the same item
- avoid introducing a separate `command_palette_favorites` top-level key
- palette Tab toggle will update `custom_hotkeys` (`hotbar`) entries

Planned work:

- add load/save helpers in config layer for hotbar-enabled targets
- extend custom_hotkeys validation (`hotkey` xor/and `hotbar` allowed, but not both missing)
- dedupe by target for hotbar view state
- ignore unknown targets at runtime (do not crash)

Likely files:

- `src/homebase/config/prefs.py`
- `src/homebase/config/store.py`
- `src/homebase/ui/context.py` (if we carry through UIContext)
- `src/homebase/ui/app.py` (runtime state)

### 2) Unified command registry for palette + favorites

Decision: yes, still needed.

Reason:

- `custom_hotkeys` is persistence for user intent (what is pinned to hotbar)
- a registry is runtime resolution (which commands exist now, labels/help/callback/enabled)
- hotbar + palette star rendering + enter-dispatch all need consistent lookup by target id

Introduce one source of truth for command metadata so both command palette and header action strip use same command set.

Command record shape (internal):

- `id` (target id string)
- `title` (plain text)
- `help`
- `callback` (callable)
- `scope` (`target|global|tab`)
- `enabled` boolean (availability in current context)

Planned work:

- extract command-building logic from `get_system_commands`
- keep `get_system_commands` as renderer over this registry
- expose lookup by id for favorites execution

Likely files:

- `src/homebase/ui/app.py`
- optionally new helper module: `src/homebase/ui/query/favorite_actions.py`

### 3) Command palette favorite toggle (`tab`)

Behavior:

- In palette, pressing `tab` toggles favorite on currently highlighted command
- Command label updates immediately
- Favorited command names display ` ★` in red

Implementation strategy:

- create custom palette screen subclass (do not patch upstream internals)
- override palette launch action in app to open custom palette
- on toggle:
  - resolve selected command id
  - update/create `custom_hotkeys` entry with `hotbar: true|false`
  - preserve existing `hotkey` if present
  - persist config
  - refresh command list

Styling strategy for star:

- append rich text star to prompt/title in custom provider / command generation
- use explicit color token (red) consistent with app theme constants

Likely files:

- `src/homebase/ui/screens/` (new palette screen)
- `src/homebase/ui/app.py`
- `src/homebase/core/constants.py` (if adding color/token constants)

### 4) Query/header layout split

Current request: top query view split in two regions, width-aligned with main table and side panel.

Plan:

- create a top header container with two child widgets
  - left: existing query/status content
  - right: favorite action strip content
- use same width ratio source used by side/table layout (`_table_side_width_pct`) to keep visual alignment

Likely files:

- `src/homebase/ui/app.py` (compose + CSS)
- `src/homebase/ui/side/content.py` or `src/homebase/ui/query/runtime.py` (render text/state)

### 5) Favorite action strip behavior

Behavior:

- right strip shows favorite commands in deterministic order
- one command is selected (active index)
- left/right keys cycle active favorite command
- selection is view-state in app (optionally persisted)
- if no `hotbar: true` entries exist, hide hotbar entirely

Default item requirement:

- default action is always `open_selected` when no hotbar entries are configured
- `open_selected` is execution default, not a visible hotbar item
- when at least one hotbar entry exists, `enter` executes selected hotbar command
- when no hotbar entries exist (hotbar hidden), `enter` behaves exactly like today (`open_selected`)

Execution behavior:

- `enter` executes currently selected hotbar item
- if selected favorite is unavailable in current context, show runtime status warning and no-op
- fallback path only applies for exceptional states (e.g. hotbar resolution failure)

Likely files:

- `src/homebase/ui/query/key_input.py` (route key behavior)
- `src/homebase/ui/app.py` (state, execute dispatch)
- `src/homebase/ui/query/runtime.py` (strip rendering)

### 6) Key routing conflicts + focus rules

Need to avoid conflicts with existing left/right behavior:

- when main table focus is active and strip mode is enabled, left/right currently affects query cursor / settings reorder
- define explicit precedence:
  1. modal screens own keys
  2. settings-table views keep current left/right behavior
  3. if favorite strip is visible and has favorites, left/right cycles favorite action
  4. else existing route behavior unchanged

### 7) Error handling / resilience

- no bare exceptions; catch concrete config I/O/parsing failures
- on config save failure: show runtime error, keep in-memory state consistent
- if favorite id points to removed command: skip gracefully

---

## Implementation Steps (ordered)

1. Extend `custom_hotkeys` parsing/validation with optional `hotbar`
2. Add app runtime state for favorites + selected favorite index
3. Extract command registry builder and command lookup by id
4. Implement custom palette class with `tab` favorite toggle
5. Wire app `action_command_palette` to custom palette
6. Add star rendering in palette list for favorited commands
7. Split top header into left/right aligned regions
8. Render favorite action strip in right header region
9. Add left/right key handling to cycle favorite strip selection
10. Add `enter` behavior to execute selected hotbar command
11. Add runtime hints/messages for empty/unavailable favorites
12. Add tests and run lint/tests

---

## Test Plan

### Unit tests

- config read/write roundtrip for `custom_hotkeys.hotbar`
- invalid favorites entries are filtered
- command registry includes stable ids
- favorite toggle add/remove idempotency
- validation fails when both `hotkey` and `hotbar` are missing
- no-hotbar state hides strip and keeps `enter=open_selected`

### UI logic tests (non-Textual heavy)

- left/right cycling wraps correctly
- selected index repair when favorites shrink
- `enter` dispatch calls expected callback for selected favorite
- unavailable favorite command results in warning/no-op

### Regression tests

- palette favorites survive app restart (via config)
- toggling favorite in palette updates query strip content
- existing non-favorite `enter` behavior still works when no favorites selected

Likely test files:

- `tests/test_ui_context.py` (extend if useful)
- `tests/test_ui_palette_favorites.py` (new)
- `tests/test_ui_query_favorite_strip.py` (new)
- `tests/test_config_prefs.py` (new/extend)

---

## Resolved Decisions

1. `enter` behavior scope:
   - Use hotbar selection whenever main projects table has focus.
   - If no hotbar entries exist, keep existing `enter=open_selected` behavior.

2. Hotbar order:
   - Preserve config order (`custom_hotkeys` list order).
   - No automatic sorting.

3. Quick clear/reset hotkey:
   - No dedicated hotkey.
   - Clearing is done by toggling in `ctrl+p` (Tab) or editing config.

4. Selected hotbar index scope:
   - Shared between views (`active` and `archive`), not per-view.

---

## Acceptance Criteria

- `tab` inside command palette toggles favorite on highlighted command
- favorited commands show red star suffix in palette
- hotbar persistence reuses `custom_hotkeys` with `hotbar: true`
- query/header shows right-side favorite action strip aligned with side panel width
- left/right cycles strip selection
- hotbar item order matches `custom_hotkeys` config order
- hotbar is hidden when no `hotbar: true` entries exist
- when hotbar is hidden, `enter` remains `open_selected`
- when main table has focus and hotbar exists, `enter` executes selected hotbar command
- `enter` executes selected hotbar command correctly
- hotbar entries persist in `<base>/.homebase/config.yaml`
- no writes to `cwd/.homebase` for this feature
- lint and tests pass
