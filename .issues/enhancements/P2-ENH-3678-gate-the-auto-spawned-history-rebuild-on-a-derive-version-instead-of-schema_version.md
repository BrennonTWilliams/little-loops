---
id: ENH-3678
type: ENH
title: Gate the auto-spawned history rebuild on a derive version instead of SCHEMA_VERSION
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T00:31:00Z'
blocks:
- ENH-3666
---

# ENH-3678: Gate the auto-spawned history rebuild on a derive version instead of SCHEMA_VERSION

## Summary

Stop the SessionStart hook from spawning a full `backfill_worker --rebuild` on every `SCHEMA_VERSION` bump. Gate the auto-rebuild on a dedicated derive version that changes only when parser or `_REBUILD_TABLES` derivation semantics change, add a single-flight guard, and make the auto-spawn opt-in above a store-size threshold. Split out of ENH-3666 after its 2026-09-29 pre-implementation Opus review.

## Current Behavior

`hooks/session_start.py` (~`:213`) adds `--rebuild` whenever `meta.last_rebuild_version < SCHEMA_VERSION` (currently 58). About 20 bumps since June, several of which (e.g. the `harness_events` and harness-column bumps) change no `_REBUILD_TABLES` derivation, each force a full wipe-and-replay of a multi-GB store. There is no single-flight guard: every SessionStart during a multi-minute rebuild spawns another `--rebuild`. A ~9.6 GB store held the write lock for minutes and dropped concurrent `ll-*` telemetry rows.

## Expected Behavior

- A `REBUILD_DERIVE_VERSION` constant in `session_store/lifecycle.py` plus a `rebuild_derive_version` meta key (inline upsert, not in the `usage_derive_` namespace); the hook compares against it instead of `SCHEMA_VERSION`. `rebuild()` stamps it on success alongside `last_rebuild_version`.
- Migration: stamp the current derive version without rebuilding **only when `last_rebuild_version == 58` exactly** (that store was rebuilt under current derivation code); any lower or missing value rebuilds once. Pin to `== 58`, not `>= 58`, so a later derivation change landing without a schema bump is not silently skipped.
- Usage-only derivation changes bump `_USAGE_DERIVE_VERSION` (incremental path), **not** `REBUILD_DERIVE_VERSION`. `REBUILD_DERIVE_VERSION` bumps only when parser or `_REBUILD_TABLES` derivation semantics change; document this rule next to the constant. This is what prevents a repeat of the 09-23/09-24/09-29 incident rebuilds (they changed usage derivation).
- A single-flight `fcntl.flock` (`LOCK_NB`) reusing the `backfill_worker` `<db>.usage-refresh.lock` pattern, so only one `--rebuild` runs at a time (a second spawn exits immediately without touching the DB). Hold it for the rebuild's whole run.
- Above a size threshold the hook does not auto-spawn `--rebuild`; it reports "rebuild pending" (SessionStart output / `ll-doctor`) and the user runs `ll-session rebuild` explicitly. The threshold is a **module constant (1 GB)**, not a config key, to avoid `config-schema.json` / dataclass / `test_config_schema.py` churn; promote it to config only if a user asks.

## Scope Boundaries

- **In scope**: `REBUILD_DERIVE_VERSION` + `rebuild_derive_version` meta key, the SessionStart gate, a single-flight flock for `--rebuild`, the size-threshold opt-in and its pending notice.
- **Out of scope**: restructuring `rebuild()` (ENH-3666), telemetry-writer resilience (ENH-3679), remote stores (never rebuild from a hook).

## Impact

- **Priority**: P2 - stops multi-GB full rebuilds (and their write-lock stalls) on schema bumps that change no derivation
- **Effort**: Small - a version constant, one meta key, a flock, and a size gate in the SessionStart hook
- **Risk**: Medium - a wrong migration stamp could skip a needed rebuild
- **Breaking Change**: No

## Integration Map

- `scripts/little_loops/hooks/session_start.py` (`handle`, ~`:189-214`) — swap the `SCHEMA_VERSION` comparison for `REBUILD_DERIVE_VERSION`; add the size gate and pending notice; keep remote stores and `LL_NON_INTERACTIVE` suppression.
- `scripts/little_loops/session_store/lifecycle.py` — `REBUILD_DERIVE_VERSION`; `rebuild()` stamps `rebuild_derive_version` alongside `last_rebuild_version` (inline meta upsert; not `usage_derive_*`; no migration or `SCHEMA_VERSION` bump).
- `scripts/little_loops/cli/backfill_worker.py` — single-flight flock for `--rebuild`.
- `scripts/little_loops/cli/doctor.py` — surface "rebuild pending".
- Tests: `test_hook_session_start.py::TestSessionStartRebuild` (gate), a two-worker flock test (second exits, DB untouched), a size-gate test, migration-stamp tests (`== 58` stamps; `57`/missing rebuilds); `test_session_store_usage_refresh.py` asserts no `usage_derive_%` meta keys after refresh — keep the new key out of that namespace.

## Program Design

### Types

- `REBUILD_DERIVE_VERSION: str` constant in `little_loops.session_store.lifecycle`; `rebuild_derive_version` `meta` key (inline upsert, string value).

### Signatures

- `rebuild_needed(db: Path | str) -> bool` — True when `rebuild_derive_version` is missing/older than `REBUILD_DERIVE_VERSION` after applying the `last_rebuild_version == 58` stamp rule; replaces the inline `SCHEMA_VERSION` comparison in `hooks/session_start.py`.

### Call Path

- `handle` (`little_loops.hooks.session_start`) → `rebuild_needed` → size gate → detached `little_loops.cli.backfill_worker` `--rebuild` → single-flight flock → `rebuild`.

## Acceptance Criteria

- [ ] A store at `last_rebuild_version == 58` is stamped without rebuilding; `57`/missing rebuilds once.
- [ ] A `SCHEMA_VERSION` bump that does not change derivation does not trigger a rebuild; a `REBUILD_DERIVE_VERSION` bump does.
- [ ] Two concurrent `--rebuild` workers: the second exits without touching the DB.
- [ ] Above the size threshold the hook spawns no `--rebuild` and surfaces a pending notice.
- [ ] `test_hook_session_start.py::TestSessionStartRebuild` updated to the new gate; remote stores still never rebuild from a hook.
- [ ] Docs (`HISTORY_SESSION_GUIDE.md`, `CLI.md`, `API.md`, `ARCHITECTURE.md` `last_rebuild_version` wording) updated in end-user shape.

## Related

- ENH-3666 (structural fix; now blocked by this issue), ENH-3679 (telemetry writer resilience).

## Status

**Open** | Created: 2026-09-30 | Priority: P2
