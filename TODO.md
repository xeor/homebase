# TODO

- [ ] **Deterministic table width + tags fit**
  Current last-column stretching and tag fit logic is unstable across startup,
  side-panel width changes, terminal resize, column toggles/reorder, and
  scrollbar state.

  Required fix:
  - [ ] Remove hidden width assumptions in tag rendering (including separator/suffix overflow).
  - [ ] Make width math deterministic and geometry-driven for all visible columns.
  - [ ] Ensure last visible column fills remaining space without introducing horizontal scroll.
  - [ ] Keep `Settings > Table` width display in sync (`configured (effective-content-width)`).
  - [ ] Recompute on every relevant change: startup/layout settle, resize,
    settings toggles, reorder, width +/- and side-width changes.
  - [ ] Verify behavior with and without vertical scrollbar.

  Technical context for next AI:
  - Scope/files touched so far:
    - `src/homebase/ui/app_display.py` (`_configure_table_columns`)
    - `src/homebase/ui/table/render.py` (tag rendering + width budget)
    - `src/homebase/ui/side/settings.py` (`Settings > Table` WIDTH display)
    - `src/homebase/ui/app.py` (startup reflow timer)
  - Known user-facing failure patterns:
    - Startup shows better width for ~0.5s, then tags collapse / widths drift.
    - Last column sometimes overflows by 2 chars and creates horizontal scrollbar.
    - `Settings > Table` effective width in parentheses drifts across toggles.
    - Toggling last column (`tags`/`size`) yields inconsistent effective widths.
  - Attempts already tried (and why they were insufficient):
    - Added delayed reflow timer(s) after mount.
      - Helped partially, but not deterministic; behavior still changed after later refreshes.
    - Used `table.virtual_size.width - sum(configured_widths)` as dynamic overhead.
      - Caused drift/feedback when table content or scrollbar state changed.
    - Synced effective widths from `table.columns[i].width` after render.
      - Introduced unstable feedback loop; tags could shrink to ~10 chars.
    - Introduced fixed overhead constant (e.g. 12).
      - Rejected; not robust across terminal/theme/scrollbar/layout changes.
    - Tag renderer improvements (`++` suffix budgeting, no `#` prefix).
      - Better visuals, but does not solve core width determinism.
  - Current implementation assumptions likely wrong:
    - Effective width source is not single-truth; code mixes configured/effective/runtime measurements.
    - Last-column fill does not consistently include all chrome + padding + scrollbar impact.
    - Tag budget in `render.py` uses width map that can be stale or semantically mismatched.
  - Suggested robust fix direction:
    - Build one pure function: `solve_visible_column_widths(viewport, visible_cols, cell_padding, vscroll)`.
    - Use that same solver in all three places:
      - column setup (`_configure_table_columns`),
      - tags budget (`render.py`),
      - settings width display (`settings.py`).
    - Avoid post-render feedback loops (`virtual_size` / `columns[i].width`) for deciding next widths.
    - Explicitly include:
      - `DataTable.cell_padding`,
      - border/chrome,
      - vertical scrollbar occupancy.
    - Recompute on: mount settle, `Resize`, settings table ops, side panel width changes.
