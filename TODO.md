# TODO

## b setup hardening

- [x] Make `b setup` re-runnable and safe at any time.
  - [x] Keep success path when `~/.local/bin/b` already points to current target.
  - [x] If `~/.local/bin/b` points elsewhere, propose fix and report old/new target.
  - [x] If `~/.local/bin/b` is a regular file, propose safe fallback (rename with timestamp) before writing symlink.
  - [x] Make setup flow: validate first, then propose fixes one-by-one.
  - [x] Handle `Ctrl-C` as immediate setup abort.
  - [x] Enforce `y/n` confirmation loop for prompts.
  - [x] Add final summary with explicit PASS/WARN/FAIL counts.

- [x] Ensure `.homebase/` handling matches runtime behavior.
  - [x] Create `<base>/.homebase/` on setup run when missing.
  - [x] Do not pre-create runtime artifacts that are naturally created by commands (cache/report files).
  - [x] Do not auto-generate `config.yaml`; show next-step guidance instead.

- [x] Replace setup config generator with docs-first flow.
  - [x] Print post-setup next steps and point to README.
  - [x] Add README kitchen-sink config example with comments.

- [x] Enforce gitignore coverage for runtime state files.
  - [x] Ensure `<base>/.homebase/.gitignore` exists.
  - [x] Ensure `.homebase/.gitignore` contains only sqlite ignore entry `cache.sqlite3`.
  - [x] Keep operation idempotent (no duplicate lines).
  - [x] Do not add ignore rules for `config.yaml` or YAML report files.

- [x] Improve tmux setup checks and standardization.
  - [x] Keep current `bind-key t -> b tmux save` validation/rewrite flow.
  - [x] Detect conflicting tmux bindings and show concrete diff-like suggestion.
  - [x] Validate that tmux/uv paths used in binding actually exist.
  - [x] Provide explicit post-step command: `tmux source-file ~/.tmux.conf`.

- [x] Add full setup validation pass as phase 1 of setup.
  - [x] Print start banner with resolved base dir and how to change it (`--base-folder`, `BASE_FOLDER`).
  - [x] Always print setup status details, even when parts are already configured.
  - [x] Show explicit "already configured" vs "missing" vs "needs change" wording for each check.
  - [x] Validate symlink target correctness.
  - [x] Validate PATH includes `~/.local/bin`.
  - [x] Validate tool/dependency availability: `uv`, `git`, `tmux` (`tmuxp` optional).
  - [x] For missing dependency checks, include concrete fix hint text.
  - [x] Validate `.homebase` directory exists.
  - [x] Validate `.homebase` writability explicitly.
  - [x] Validate `config.yaml` YAML shape when present.
  - [x] Decide whether missing `config.yaml` should remain warning or fail (warning).
  - [x] Validate gitignore entry presence.
  - [x] Validate tmux binding presence/recommendation status.
  - [x] Present fix plan and apply fixes one-by-one with explicit prompt per fix.
  - [x] Tighten return-code policy so warnings are non-fatal and only hard failures fail.

- [x] Add tests for setup behavior.
  - [x] Unit tests for symlink scenarios (correct link, wrong link, plain file).
  - [x] Unit tests for gitignore insertion/idempotency.
  - [x] Unit tests for prompt interrupt behavior (`Ctrl-C` abort path).
  - [x] Unit tests for validation report + return code rules.
  - [x] Unit tests for tmux binding detection edge cases.
  - [x] Unit tests for tmux binding rewrite path.
  - [x] Integration-style test for validate-first + fix-order flow.

## Optional improvements to decide

- [x] Add `--dry-run` for setup (show changes without writing).
