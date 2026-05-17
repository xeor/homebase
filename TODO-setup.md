# TODO: `b setup` overhaul

Goal: make `b setup` significantly more useful for day-to-day maintenance, with clear status visuals, interactive fix selection, and reliable self-update support.

## Scope

- Rich status output with color-coded states (`PASS`, `WARN`, `FAIL`, `SKIP`).
- Interactive fix selection via keyboard:
  - arrow keys to move
  - `space` to toggle checkbox
  - `enter` to apply selected fixes
  - `a`/`n` optional: select all / select none
- Non-interactive fallback remains supported (CI, pipes, no TTY).
- Add self-update detection and fix action based on install method.
- Keep current safety semantics (no destructive/unexpected writes).

## Current baseline (observed)

- `cmd_setup` is in `src/homebase/core/setup_tools.py` and is monolithic (~670 lines).
- Validation + proposing + applying + re-validation are interleaved in one function.
- Output is plain text (`- [PASS] ...`) without styling.
- Fix flow is prompt-per-item (`prompt_yes_no`) rather than batched selection.
- No explicit self-update check/fix.

## Design targets

### 1) Internal model split

Refactor setup flow into structured data:

- `SetupCheck`
  - `id`, `name`, `status`, `detail`, `required`, `fix_id | None`
- `SetupFix`
  - `id`, `title`, `selected_default`, `enabled`, `reason_if_disabled`, `apply()`
- `SetupContext`
  - resolved binaries/paths/shell/install metadata

Status and fix computation should be pure-ish helpers where possible.

### 2) Rendering

- Add a rendering layer that can output:
  - ANSI-colored text for TTY
  - plain text for non-TTY
- Suggested palette:
  - PASS: green
  - WARN: yellow
  - FAIL: red
  - SKIP/info: dim cyan/gray

### 3) Interactive selector

Implement a small full-screen-ish selector (or line-based redraw) with:

- key handling for arrows/space/enter/q
- checkbox list bound to computed `SetupFix` entries
- persistent summary footer (selected count, warnings)

Decision: use Textual from the beginning (no raw terminal fallback for the interactive path).

Potential module split:

- `core/setup_model.py` (checks + fixes)
- `core/setup_render.py` (color + summaries)
- `core/setup_select.py` (interactive checkbox UI)
- keep `setup_tools.py` as orchestration entrypoint

### 4) Self-update support

Detect install origin and map to update command/action:

- editable local install (`uv tool install --editable ...`) -> suggest reinstall/update command
- `uv tool` managed install -> `uv tool upgrade homebase` (or reinstall if needed)
- pip editable/venv install -> `pip install -U -e <path>` where safe
- unknown install -> report detection details + manual guidance

Detection inputs:

- `which b`
- `sys.executable`
- `importlib.metadata` dist location
- known uv tool paths (`~/.local/share/uv/tools/...`)

Self-update should be a first-class check+fix pair:

- check: `homebase install/update path`
- fix: run/update command (or print exact command in dry-run)

### 5) Apply phase semantics

- Build a selected fix list first, then execute in stable order.
- Respect dependencies between fixes (e.g., create dir before writing file).
- Report per-fix result and total summary.
- Continue-on-error for independent fixes, but aggregate failures.

### 6) Backward compatibility

- Preserve `--dry-run` semantics.
- Preserve existing return code contract:
  - `0` when required checks pass
  - `1` when required checks fail
- Preserve non-interactive behavior with deterministic defaults.

## Implementation plan

1. **Extract models/helpers**
   - carve out check/fix dataclasses and status computation from `cmd_setup`.
2. **Colorized renderer**
   - central formatting helpers + tty detection.
3. **Interactive selector**
   - implement checkbox UI and integrate into `cmd_setup` when tty+interactive.
4. **Self-update detection**
   - implement install-mode probes and add a check/fix entry.
5. **Fix executor**
   - batch apply selected fixes and produce detailed result table.
6. **Final validation rewrite**
   - derive summary from model rather than duplicated local state.

## Test plan

Add/expand tests under `tests/test_setup_tools.py` (and new test modules if split):

- status model generation for representative environments
- renderer outputs (color/no-color)
- selector behavior (toggle/select/confirm) via injected input stream
- dry-run for all fix types
- self-update detection matrix (uv tool, editable local, unknown)
- self-update execution command selection
- return code behavior unchanged for required check failures

## Open questions

- Should interactive selector use raw terminal control or a minimal Textual screen?
  - Decision: Textual from the beginning for consistency with the rest of the project.

- For self-update, should setup directly execute update by default or require explicit selection?
  - Decision: explicit selection only.
  - Additional requirement: detect local editable installs and suggest reinstall/sync workflow; for remote/tool installs, prefer upgrade flow and surface uncertainty details when detection is ambiguous.

- How aggressive should install-method detection be?
  - Decision: conservative; if uncertain, show diagnostic details + manual command.

## Iteration status

- [x] Capture requirements and decisions in this file.
- [~] Extract setup validation model from `cmd_setup`.
- [x] Add colorized status renderer (TTY-aware).
- [x] Build Textual checkbox selector for fix actions.
- [x] Add install-mode detection + self-update check/fix.
- [x] Integrate selected-fix executor and final validation summary.

## Implemented so far

### UI / UX

- [x] Colorized status labels via `core/setup_render.py` (`PASS/WARN/FAIL/SKIP`, `NO_COLOR` respected).
- [x] Textual selector implemented in `core/setup_select.py`.
- [x] Selector supports: arrows, `space`, `enter`, `a`, `n`, `q`.
- [x] Selector is split into two panes:
  - left: selectable fix list
  - right: details for highlighted item (`What`, `Status`, `Will change`, extra details)

### Setup execution model

- [x] Prompt-per-fix flow replaced by batched fix execution.
- [x] Fix actions represented with explicit fields (`id`, `title`, `selected_default`, `required`, `status`, `details`, `changes`, `apply`).
- [x] Selector labels show `[required]` vs `[optional]`.
- [x] Execution summary includes:
  - selected/skipped counts
  - succeeded/failed counts
  - selected, successful, failed fix lists
- [x] Selected fix failures now force setup exit code `1` (except dry-run).

### Self-update

- [x] Self-update check/fix integrated in setup flow.
- [x] Explicit-selection-only behavior (not auto-run by default).
- [x] Conservative install-mode detection with diagnostics:
  - local editable repo
  - uv tool runtime/path
  - site/dist-packages runtime
  - unclear mode with launcher/python details
- [x] Diagnostic block printed when update mode is unclear.

### Refactors completed

- [x] Extracted helpers:
  - `_select_fix_ids(...)`
  - `_apply_selected_fixes(...)`
  - `_print_fix_execution_summary(...)`
  - `_build_setup_fix_actions(...)`
  - `_compute_final_validation(...)`
  - `_print_self_update_check(...)`

### Tests added/expanded

- [x] `tests/test_setup_render.py` (color/no-color behavior).
- [x] `tests/test_setup_tools.py` expanded with:
  - self-update detection matrix tests
  - selector callback behavior tests
  - fix-apply failure aggregation tests
  - summary rendering tests
  - fix metadata coverage tests

## Current remaining work (v1 completion)

1. Finish validation model extraction from `cmd_setup` (remaining inline validation/check rendering).
2. Reduce `cmd_setup` to orchestration phases only:
   - gather context
   - render validation
   - build fixes
   - select fixes
   - apply fixes
   - final validation + exit decision
3. Ensure non-interactive fallback remains deterministic and unchanged in semantics.

## Missing / partial items (explicit)

### Still missing (not implemented yet)

- [ ] Dedicated `SetupCheck` data model is not in place yet.
  - Current state: validation checks are still assembled/printed inline in `cmd_setup`.
- [ ] Validation renderer is still procedural in `setup_tools.py`.
  - Current state: status label coloring is extracted, but full row rendering is not model-driven.
- [ ] No separate setup orchestration module yet.
  - Current state: orchestration still lives in `cmd_setup`.
- [ ] No structured serialization output (`--json`) for setup checks/fixes/results.
- [ ] No version lookup against remote release source yet.

### Partially implemented

- [~] `cmd_setup` decomposition is partial.
  - Extracted: fix build/select/apply/summary/final validation/self-update-check rendering.
  - Remaining: initial validation collection/rendering and some environment probing are still inline.
- [~] Self-update detection is conservative and useful but not exhaustive.
  - Handles local repo, uv tool runtime/path, site/dist-packages runtime, unknown.
  - Missing: deeper distinction for more install variants + version-aware upgrade recommendation.
- [~] Two-pane Textual selector works, but right-pane content is still generic for some fixes.
  - Missing: richer current-state -> desired-state diff text for every fix type.

## Files touched in this effort

### New files

- `TODO-setup.md`
- `src/homebase/core/setup_render.py`
- `src/homebase/core/setup_select.py`
- `tests/test_setup_render.py`

### Existing files changed

- `src/homebase/core/setup_tools.py`
- `src/homebase/cli/parser.py`
- `src/homebase/cli/entry.py`
- `src/homebase/cli/dispatch.py`
- `src/homebase/core/logging.py`
- `src/homebase/workspace/new/cmd.py`
- `src/homebase/workspace/new/sources/local.py`
- `src/homebase/commands/setup.py`
- `src/homebase/cli/shell_init.py`
- `src/homebase/workspace/new/detect.py`
- `tests/test_setup_tools.py`
- `tests/test_shell_init.py`
- `tests/test_core_logging.py`
- `tests/test_new_local.py`
- `tests/test_new_detect.py`
- `tests/test_project_create.py`
- `pyproject.toml`

Note: not all changed files are strictly setup-only; some are related fixes completed during the same iteration window.

## Planned next iterations

### v1.1 (near-term)

- [ ] Extract validation check rows into a structured model (`SetupCheck`) and renderer helper.
- [ ] Add tests for full validation row set and status transitions.
- [ ] Improve right-pane detail content with current-state -> desired-state snippets for key fixes.

### v2 (extra, but realistic)

- [ ] Add optional `--json` output mode for setup checks/fixes/results.
- [ ] Add optional "preview changes" view per selected fix (before apply).
- [ ] Add lightweight dependency graph/order metadata per fix (explicit prerequisites).
- [ ] Add "re-run failed fixes" action in selector after first apply pass.

### Stretch goals

- [ ] Full Textual setup app with tabs:
  - Overview
  - Fixes
  - Self-update
  - Diagnostics/log
- [ ] Background version lookup for remote releases (with timeout/cache) to preselect upgrade when a newer version exists.
- [ ] Plugin-style setup check registry so domains can contribute checks/fixes independently.
- [ ] Persist last setup run report under `.homebase/` for audit/history.

## Done criteria

- `b setup` provides colorized, scannable validation output.
- Interactive checkbox selection works in terminal.
- Non-interactive fallback remains functional.
- Self-update check/fix exists and behaves correctly for known install modes.
- Existing setup tests remain green and new coverage added.
- `uv run ruff check src/homebase/ tests/` and relevant pytest suites pass.
