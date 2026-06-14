# Integrations

`integrations/` contains optional standalone projects that depend on
Homebase. Homebase does not depend on them.

| Path | Purpose | Tooling |
| --- | --- | --- |
| `integrations/raycast/` | Raycast extension for `b ls` / `b cd` project search | `mise run setup`, `mise run dev`, `mise run check` |
| `integrations/browser-tab-sync/` | Browser tab-group desired-state controller | `mise run dev`, `mise run test`, `mise run lint`, `mise run build` |

Boundary rules:

- Root `pyproject.toml`, `uv.lock`, build output, and QA cover only
  `src/homebase/` and `tests/`.
- Integration deps stay in integration-local manifests and lockfiles.
- Integration tasks run from that integration directory. Mise may also
  show inherited root tasks while the integration lives inside this
  monorepo; the integration-local manifests are complete on their own.
- `src/homebase/` must not import from, shell out to, package, or test
  against `integrations/`.

Common commands:

```sh
mise tasks ls
mise run qa

cd integrations/raycast
mise tasks ls
mise run check

cd ../browser-tab-sync
mise tasks ls
mise run test
```
