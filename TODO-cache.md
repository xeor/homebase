# TODO cache

Goal: one unified cache system for the whole app (all views, all cache users),
configured only via `cache_profile.*` + local overrides.

## Existing behavior to preserve

- Row cache in sqlite (`cache/api.py`, `cache/store.py`):
  - persisted row state (`cached_at`, `reconciled_at`, `stale`, `cache_age_s`)
  - boot loads cache first, background refresh later
- Reconcile scheduler (`ui/sync/reconcile.py`, `ui/sync/reconcile_worker.py`):
  - mode-aware cadence (`active` / `archive`)
  - chunking (`batch_size`), worker queue with priority
  - usage scoring (`row_usage_score`, `row_usage_hits`,
    `row_usage_last_used_ts`) + decay + persisted usage cache
- Packed archive caches (`archive/io.py`):
  - `_PACKED_META_MEMBER_CACHE`, `_PACKED_BASE_DATA_CACHE`
- UI dynamic caches (`ui/app.py`):
  - `dynamic_indicator_cache` (set-based)
  - `dynamic_indicator_row_cache` (row bool)

These are the right primitives. The issue is policy fragmentation and heavy
work running from fast UI callbacks.

## Problem confirmed by profiling

- Hot path still dominated by:
  - pane probe callback -> full property recompute
  - metadata health checks
  - packed archive tar/gzip parsing
- This bypasses chunked reconcile policy and hurts selection latency.

## Target architecture

One policy model for all cache users:

- `cache_profile.<view>.<name>` defines reusable cache profile presets
- `cache_profile.all.<name>` is base profile for all views
- `cache_profile.<view>.<name>` overrides `all` for the target view
- Every cache consumer references `cache_profile: <name>`
- Consumer-local `cache_profile_overrides` may override profile values
  using same structure (`all`, `active`, `archive`, ...)

No ad-hoc hardcoded cadence/TTL per subsystem once migrated.

## Config schema

```yaml
cache_profile:
  all:
    pri-1:
      update_interval_s: 0.5
      update_batch_size: 64
      update_priority: 10
      cache_mode: ttl
      cache_ttl_s: 5
      use_usage_score: true
      usage_weight: 1.0
      stale_boost: true
      max_parallelism: 1
    pri-2:
      update_interval_s: 10
      update_batch_size: 16
      update_priority: 40
      cache_mode: ttl
      cache_ttl_s: 30
      use_usage_score: true
      usage_weight: 0.7
      stale_boost: true
      max_parallelism: 1
    pri-3:
      update_interval_s: 600
      update_batch_size: 1
      update_priority: 90
      cache_mode: path_signature
      cache_ttl_s: 600
      use_usage_score: false
      usage_weight: 0.0
      stale_boost: false
      max_parallelism: 1
  active:
    pri-2:
      update_batch_size: 24
  archive:
    pri-2:
      update_interval_s: 300
      update_batch_size: 2
```

Property example:

```yaml
properties:
  PKG:
    cache_profile: pri-3
    cache_profile_overrides:
      archive:
        update_interval_s: 1200
  E:
    cache_profile: pri-2
    cache_profile_overrides:
      active:
        update_batch_size: 24
      archive:
        update_interval_s: 300
        update_batch_size: 2
```

Same pattern should be reusable in other domains later (`git refresh`,
`pane probe`, `reconcile`, metadata checks, etc.).

## Profile fields (common vocabulary)

Mandatory core:
- `update_interval_s`
- `update_batch_size`
- `update_priority`
- `cache_mode` (`ttl` | `path_signature`)
- `cache_ttl_s`

Scoring/scheduling (existing reconcile behavior, made configurable):
- `use_usage_score` (bool)
- `usage_weight` (float)
- `stale_boost` (bool)
- `max_parallelism` (int)

Optional extensions (for later migration):
- `min_interval_s` (throttle floor)
- `refresh_on_event` (list of event names)
- `jitter_pct` (spread spikes)

## Merge rules (single source of truth)

For an effective profile in view `<v>`:

1. hard defaults
2. `cache_profile.all.<name>`
3. `cache_profile.<v>.<name>`
4. consumer top-level explicit cache fields
5. consumer `cache_profile_overrides.all`
6. consumer `cache_profile_overrides.<v>`

Later layers override earlier layers.

## Scheduler model

Shared scheduler contract for all cache jobs:

- job key (domain + scope)
- selected `cache_profile`
- due timestamp per view
- candidate selector (chunk source)
- evaluator function
- apply function (only changed rows/UI parts)

Selection policy:

- order by `update_priority`, then due time
- process at most `update_batch_size` items per run
- apply usage score/stale boost when profile enables it
- respect `max_parallelism`

## Domain migration plan

Phase 1: foundation
1. Add loader + resolver for `cache_profile` inheritance.
2. Add shared profile merge utility used by all domains.
3. Add validation errors for invalid profile refs/keys.

Phase 2: properties (first consumer)
4. Add `cache_profile` + `cache_profile_overrides` support to property defs.
5. Move property refresh to chunked scheduler job(s).
6. Remove full `_apply_dynamic_properties_all_rows` from probe callback path.

Phase 3: reconcile migration
7. Map reconcile config fields to profile-backed equivalents.
8. Preserve existing scoring behavior, now driven by profile fields.
9. Keep existing persisted usage cache and decay logic.

Phase 4: remaining consumers
10. Move pane probe cadence/throttle to profile-backed policy.
11. Move git visible refresh cadence to profile-backed policy.
12. Move metadata-health polling cadence to profile-backed policy.

Phase 5: cleanup
13. Remove duplicate subsystem-specific cadence knobs after migration.
14. Keep one place for cache behavior: `cache_profile` + local overrides.

## Tests and verification

- Config parsing:
  - `cache_profile` inheritance (`all` + view)
  - override merge order
  - invalid profile names / invalid fields
- Scheduler:
  - priority ordering
  - batch limits
  - due handling
  - usage/stale weighting toggles
- Regression:
  - pane probe does not trigger full property recompute
  - active view stays responsive with large archive set
- Profiling gates (pyinstrument):
  - significant drop in cumulative time under probe callback path
  - no dominant tar/gzip churn on selection navigation

## Success criteria

- One cache policy system reused across domains and views.
- Archive work remains low-priority and low-frequency by default.
- Interactive selection remains responsive under background activity.
- New cache consumers can be configured without new hardcoded cadence logic.
