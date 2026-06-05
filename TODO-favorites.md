# TODO: Favorites (replaces "hotbar")

Goal: replace the "hotbar" concept with a generic **Favorite**. A
favorite is a starred target. Its visual surface is derived from the
target's kind:

- target-scope action  → bottom **hotbar bar** slot (current behavior)
- workspace-scope action → entry in a Favorites list / possibly a
  dedicated button surface
- tab / side-nav target → entry in Favorites list (jump shortcut)
- future kinds → derived from target prefix

Everything is anchored in one concept: **Favorite**.
"Hotbar" stops being a separate idea — it's just *the surface where
target-scope action favorites render*.

---

## 1. Storage model

Hard rename — no backwards compatibility (single user). YAML key
`custom_hotkeys` → `favorites`, row flag `hotbar: true` →
`favorite: true`:

```yaml
favorites:
  - id: fav_1
    target: set_desc           # action_id  → hotbar slot
    favorite: true
  - id: fav_2
    target: tab:projects/log   # tab nav    → list entry
    favorite: true
  - id: fav_3
    target: edit_global_config # workspace  → list entry
    favorite: true
```

In-code renames:

- `_toggle_hotbar_target_from_palette` → `_toggle_favorite_target`.
- `STATE_KEY_HOTBAR_SELECTED_INDEX` → `STATE_KEY_HOTBAR_SLOT_INDEX`
  (kept — refers to the *bar* surface specifically).
- Old `hotbar: true` rows / old YAML key are ignored on load. Any
  pre-existing data must be re-favorited.

Target prefix rules drive the surface:

```python
def favorite_surface(target: str, actions: dict[str, Action]) -> str:
    if target.startswith("tab:") or target.startswith("tab."):
        return "nav"
    action = actions.get(target)
    if action is not None and action.scope == "target":
        return "hotbar"
    if action is not None and action.scope == "workspace":
        return "global"
    return "nav"  # unknown → list-only
```

---

## 2. ctrl+a picker — new "Favorites" tab

Add to `ui/actions/catalog.py`:

```python
CATEGORY_FAVORITES = "favorites"
CATEGORY_ORDER = (
    (CATEGORY_NOTIFICATIONS, "Notifications"),
    (CATEGORY_BUTTONS, "Buttons"),
    (CATEGORY_FAVORITES, "Favorites"),   # new, before Target
    (CATEGORY_TARGET, "Target"),
    (CATEGORY_GLOBAL, "Global"),
)
```

`build_picker_catalog` adds the Favorites entries pulled from
`favorites` where `favorite: True`, in stored order, **flat list**
with a surface-suffix tag (the entry's name already conveys what it
is, so no sub-group headers):

```
Set description           [dim](hotbar slot 1)[/]
Archive                   [dim](hotbar slot 2)[/]
Edit global config        [dim](global)[/]
Selected / readme         [dim](nav)[/]
```

Dispatch on accept:

- `action_id` → existing `on_pick_actions(value)` flow.
- `tab:…`     → call `_jump_to_side_tab(top, child)` (new branch in
  `on_pick_actions`).

The screen's existing fuzzy filter (`_visible_actions`) works
unchanged.

---

## 3. Tab-switch hotkeys in ctrl+a

Add to `ActionPickerScreen.BINDINGS`:

```
ctrl+@   → action_jump_tab_favorites
ctrl+t   → action_jump_tab_target
ctrl+g   → action_jump_tab_global
```

`left` / `right` keep cycling tabs as today.

`tab` / `backtab` get re-purposed:

- `tab`     → `action_toggle_favorite` (matches ctrl+p semantics)
- `backtab` → unbound (use `left`/`right` for tab cycling)

---

## 4. `<tab>` toggle semantics (unified)

One helper, used by both `BCommandPalette.action_toggle_hotbar` and
the new `ActionPickerScreen.action_toggle_favorite`:

```python
def toggle_favorite(app, target: str) -> bool:
    """Add/remove a Favorite for the given target.

    - target-scope action → toggled, renders as hotbar slot.
    - workspace-scope action → toggled, renders in Favorites list.
    - tab:… / non-action → toggled, renders in Favorites list.
    - unknown action id with no prefix → reject + log.
    """
```

Rename `BCommandPalette.action_toggle_hotbar` →
`action_toggle_favorite` (key remains `tab`).

Remove the current gate in `hotbar.toggle_hotbar_target_from_palette`
that rejects `scope != "target"` actions.

---

## 5. Bottom hotbar bar

`hotbar_targets()` becomes `hotbar_slot_targets()` and filters to
only those favorites whose surface is `"hotbar"`. Renders the bottom
bar unchanged.

`cycle_hotbar` / `selected_hotbar_target` / `STATE_KEY_HOTBAR_SLOT_INDEX`
operate on this filtered list. Workspace-scope favorites and nav
favorites never appear in the bar.

Legacy `hotbar: true` rows are ignored on load (§1), so no render-
time filter or auto-prune is needed.

---

## 6. Workspace-scope favorites — surface

List-only via the Favorites tab in ctrl+a. No footer chip row, no
side-panel "Quick actions" section.

Direct keys for triggering workspace favorites: punted until usage
proves it's needed.

---

## 7. ctrl+p (command palette) parity

Already supports `tab` to toggle. Update so:

- The toggle uses the unified `toggle_favorite` helper.
- Starred badge stays as today (`_HOTBAR_PALETTE_TAG`); rename
  internally to `_FAVORITE_PALETTE_TAG`. Public visible text:
  `\[@fav]` (was `\[@hotbar]`).
- Tab navigation entries (`tab:…`) become starrable. They already
  pass through; the gate removal in §4 makes this clean.

---

## 8. Naming sweep

| old                                  | new                                  |
| ------------------------------------ | ------------------------------------ |
| `hotbar` (concept)                   | `favorite` (concept)                 |
| `hotbar` (UI surface, bottom bar)    | `hotbar bar` / `hotbar slot`         |
| `hotbar_targets`                     | `favorite_targets`                   |
| `hotbar_visible`                     | `hotbar_bar_visible`                 |
| `selected_hotbar_target`             | `selected_hotbar_slot_target`        |
| `cycle_hotbar`                       | `cycle_hotbar_slot`                  |
| `_toggle_hotbar_target_from_palette` | `_toggle_favorite_target`            |
| `_target_is_hotbar`                  | `_target_is_favorite`                |
| `_hotbar_target_label`               | `_favorite_target_label`             |
| `bindings_from_ctx` (in hotbar.py)   | unchanged location, doc updated      |
| module `ui/actions/hotbar.py`        | `ui/actions/favorites.py`            |
| help text "alt+1..9 wip"             | unchanged (WIP is unrelated)         |
| palette tag `\[@hotbar]`             | `\[@fav]`                            |

`BuiltinHotkey("ctrl+@", "cycle_hotbar", "Next hotbar slot", …)` —
action name kept (it cycles the bar), label updated.

---

## 9. On-disk schema

Hard rename, no compat (see §1):

- YAML key `custom_hotkeys` → `favorites`.
- Row flag `hotbar: true` → `favorite: true`.
- Loader ignores the old keys entirely. Pre-existing entries must be
  re-favorited via ctrl+a or ctrl+p.

No deprecation comments in code per AGENTS.md §3.

---

## 10. Tests

New / updated test modules:

- `tests/test_favorites.py` — toggle semantics for action vs nav vs
  workspace targets; surface derivation; bottom-bar filtering.
- `tests/test_pick_actions.py` — Favorites tab present, ctrl+@/t/g
  jump to correct tabs, `tab` toggles favorite, accepting a `tab:…`
  entry triggers `_jump_to_side_tab`.
- `tests/test_command_palette.py` (if exists) — `tab` toggles work
  on `tab:…` entries; palette tag renamed to `\[@fav]`.
- `tests/test_config_*` — `favorites:` YAML loads; legacy
  `custom_hotkeys:` / `hotbar: true` are ignored (no crash, no
  carry-over).

---

## 11. Implementation order

1. Rename module + flag + YAML key (`hotbar.py` → `favorites.py`,
   `hotbar: True` → `favorite: True`, `custom_hotkeys:` →
   `favorites:`, no dual-read).
2. Add `favorite_surface(target, actions)` helper.
3. Filter bottom hotbar bar by surface == `"hotbar"`.
4. Catalog: add `CATEGORY_FAVORITES`, build entries (flat list),
   dispatch for `tab:…`.
5. `ActionPickerScreen`: new bindings (`ctrl+@`, `ctrl+t`, `ctrl+g`,
   `tab` → toggle), screen-level toggle helper.
6. Palette: switch toggle helper, rename tag, drop scope gate.
7. Naming sweep across labels and docs.
8. Tests (per §10) — green before each step lands.
9. `docs/QA/README.md` status snapshot refresh.

(Workspace-favorite "button" surface is dropped — list-only per §6.)
