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
- FEAT-3561
confidence_score: 90
outcome_confidence: 64
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3678: Gate the auto-spawned history rebuild on a derive version instead of SCHEMA_VERSION

## Summary

Stop the SessionStart hook from spawning a full `backfill_worker --rebuild` on every `SCHEMA_VERSION` bump. Gate the auto-rebuild on a dedicated derive version that changes only when parser or `_REBUILD_TABLES` derivation semantics change, add a single-flight guard, and make the auto-spawn opt-in above a store-size threshold. Split out of ENH-3666 after its 2026-09-29 pre-implementation Opus review.

## Current Behavior

`hooks/session_start.py` (~`:213`) adds `--rebuild` whenever `meta.last_rebuild_version < SCHEMA_VERSION` (currently 58). About 20 bumps since June, several of which (e.g. the `harness_events` and harness-column bumps) change no `_REBUILD_TABLES` derivation, each force a full wipe-and-replay of a multi-GB store. There is no single-flight guard: every SessionStart during a multi-minute rebuild spawns another `--rebuild`. A ~9.6 GB store held the write lock for minutes and dropped concurrent `ll-*` telemetry rows.

## Expected Behavior

- A `REBUILD_DERIVE_VERSION` constant in `session_store/lifecycle.py` plus a `rebuild_derive_version` meta key (inline upsert, not in the `usage_derive_` namespace); the hook compares against it instead of `SCHEMA_VERSION`. `rebuild()` stamps it on success alongside `last_rebuild_version`.
- Migration (no write from the hook): `rebuild_needed()` treats "no `rebuild_derive_version` key **and** `last_rebuild_version >= _LEGACY_REBUILD_FLOOR`" (a literal, 58) as the **frozen legacy derive version** (a literal, initially equal to `REBUILD_DERIVE_VERSION`), never the current constant. A floor, not `== 58`: a `SCHEMA_VERSION` bump that lands first (FEAT-3561's `recommendation_events` is queued) leaves stores rebuilt at 59+ unmarked, and an equality rule would force a multi-GB rebuild on each of them, the exact failure this issue exists to prevent. Compare the frozen legacy value with the current version; a store first opened after a future derive-version bump must rebuild. Missing or `< floor` `last_rebuild_version` rebuilds once. Only a successful `rebuild()` writes `rebuild_derive_version` (alongside `last_rebuild_version`); the SessionStart hook never stamps. The floor rule makes the change order-independent with respect to other schema bumps.
- **Bump-rule guard (2026-09-30 review):** a test pins a fingerprint of `_REBUILD_TABLES`, `_REBUILD_SEARCH_KINDS`, `_REBUILD_TABLE_PREDICATES`, the rebuild-table DDL **and the source of the parser/replay functions `rebuild()` calls (the `_backfill_*` family)**, so changing any of them without bumping `REBUILD_DERIVE_VERSION` fails. Parser changes are the most common reason derivation changes, so omitting them leaves the guard blind to the common case. If hashing function source proves too noisy (formatting-only edits), pin a hash of `inspect.getsource` normalized through `ast.dump` and document the residual gap. The bump rule alone is human discipline.
- **Failed-rebuild backoff:** record the last failed attempt and skip auto-spawn for a cooldown so a persistently failing rebuild is not retried on every session start. Keep this state in a **sidecar file next to the rebuild lock** (e.g. `<db>.rebuild.lock` contents or `<db>.rebuild-state.json`), **not in `meta`**: `rebuild()` runs in one `BEGIN IMMEDIATE` transaction that rolls back on failure, so a `meta` write from the failing worker is a second contended write on a store that is already the problem.
- Usage-only derivation changes bump `_USAGE_DERIVE_VERSION` (incremental path), **not** `REBUILD_DERIVE_VERSION`. Bump `REBUILD_DERIVE_VERSION` whenever any non-usage `rebuild()` output or selection changes: parser/replay semantics, `_REBUILD_TABLES` or search-index derivation, corrections, summaries, or prompt-opt enrichment. Document and test the bump rule near the constant.
- A single-flight `fcntl.flock` on a dedicated `<db>.rebuild.lock`. Do not reuse `<db>.usage-refresh.lock`: Stop workers take it with blocking `LOCK_EX` and store throttle state in it. **Lock protocol (2026-09-30 Opus review; unproven, see Delivery Slices):** `rebuild()` runs its whole wipe-and-replay in one `BEGIN IMMEDIATE` transaction, so a concurrent worker's incremental ingest cannot write until it commits (it would hit the 5000 ms busy timeout and fail), and the local ingest watermark is one global wall-clock `last_raw_event_ts`, so an early-exiting worker can lose its transcript. Therefore: ingest takes `LOCK_SH` with a **bounded wait** (poll `LOCK_NB` up to a wait budget, then exit leaving the transcript for the next run rather than blocking indefinitely: blocking `LOCK_SH` for the whole multi-minute replay would pile up one detached blocked worker per SessionStart/Stop); replay takes `LOCK_EX`; after acquiring `LOCK_EX` the worker **re-checks `rebuild_needed()`** and skips the replay if another worker already completed it. A direct `ll-session rebuild` uses `LOCK_NB` on the exclusive lock and reports contention instead of silently claiming success.
- Above a size threshold the hook does not auto-spawn `--rebuild`; it reports "rebuild pending" (SessionStart output / `ll-doctor`) and the user runs `ll-session rebuild` explicitly. Document what a pending rebuild means to readers (derived tables — sessions, tool/skill events, summaries, corrections, search index — keep pre-bump derivation until rebuilt; raw events and usage tables stay current). The threshold is a **module constant (1 GB)**, not a config key, to avoid `config-schema.json` / dataclass / `test_config_schema.py` churn; promote it to config only if a user asks.

## Delivery Slices (2026-09-30 Opus review)

Ship as two slices of this one issue (keeps FEAT-3561/ENH-3666 edges intact); convert to separate issues only if they need independent scheduling.

- **3678a — gate (P2, ships first, unblocks FEAT-3561):** `REBUILD_DERIVE_VERSION` + `rebuild_derive_version` meta key, floor-based `rebuild_needed()`, the SessionStart gate swap, the size gate with the "rebuild pending" notice (`ll-doctor` + SessionStart), the fingerprint test, and docs. No lock-protocol change.
- **3678b — single-flight (after the spike):** the flock protocol, failed-rebuild backoff sidecar, and the direct `ll-session rebuild` contention report. Gated on the spike below; ENH-3666's `blocked_by` moves here (3666 is deferred, so this costs nothing today).

**Interim risk accepted:** until 3678b lands, stores under the 1 GB threshold can still see duplicate concurrent `--rebuild` workers. That is acceptable only if those replays are short, which is unmeasured, so record a replay-duration measurement on a sub-1 GB store in the 3678a PR.

**Hook read path:** the hook's `rebuild_needed()` check must open the store read-only (`connect_readonly`), not `connect()`. `connect()` runs `ensure_db`/migrations; the hook already calls `ensure_db` earlier in `handle`, so this is pre-existing, but the new check should not add a second migration-capable open inside the 5 s hook budget.

## Open Questions (2026-09-30 review)

- **Lock protocol is unproven (tracked task: run `/ll:spike` for 3678b; do not start 3678b until the outcome is recorded here).** The `LOCK_SH` ingest / `LOCK_EX` replay / re-check-under-exclusive protocol is Opus's proposal, not yet validated. Before implementing, prove it with a spike (`/ll:spike`) or a test that holds a real replay open while a second worker ingests: confirm the second worker's ingest completes after the replay commits, the re-check skips a second replay, and the watermark advances only on commit. Also confirm the premise that a hook worker usually carries a single transcript (so exiting early would lose it).
- **Stale stores above the threshold.** Above the 1 GB constant, derived tables stay at pre-bump derivation until a manual `ll-session rebuild`. This is accepted; the pending notice and the documented stale-consequence are the mitigation. Revisit the threshold (or promote it to config) only if users report it.

## Scope Boundaries

- **In scope**: `REBUILD_DERIVE_VERSION` + `rebuild_derive_version` meta key, the SessionStart gate, a single-flight flock for `--rebuild`, the size-threshold opt-in and its pending notice.
- **Out of scope**: restructuring `rebuild()` (ENH-3666), telemetry-writer resilience (ENH-3679), remote stores (never rebuild from a hook).

## Impact

- **Priority**: P2 - stops multi-GB full rebuilds (and their write-lock stalls) on schema bumps that change no derivation
- **Effort**: Small - a version constant, one meta key, a flock, and a size gate in the SessionStart hook
- **Risk**: Medium - a wrong legacy-baseline rule could skip a needed rebuild
- **Breaking Change**: No

## Integration Map

- `scripts/little_loops/hooks/session_start.py` (`handle`, ~`:189-214`) — swap the `SCHEMA_VERSION` comparison for `REBUILD_DERIVE_VERSION`; add the size gate and pending notice; keep remote stores and `LL_NON_INTERACTIVE` suppression.
- `scripts/little_loops/session_store/lifecycle.py` — `REBUILD_DERIVE_VERSION`; `rebuild()` stamps `rebuild_derive_version` alongside `last_rebuild_version` (inline meta upsert; not `usage_derive_*`; no migration or `SCHEMA_VERSION` bump).
- `scripts/little_loops/cli/backfill_worker.py` / `session_store/lifecycle.py` — separate incremental ingest from the replay lock so a contending `--rebuild` worker does not discard its transcript; protect direct rebuild calls too.
- `scripts/little_loops/cli/doctor.py` — surface "rebuild pending".
- Tests: `test_hook_session_start.py::TestSessionStartRebuild` (gate), a two-worker flock test (3678b) (one replay, second re-checks under `LOCK_EX`, both transcripts ingested), a fingerprint test for the bump rule, a failed-rebuild cooldown test, a size-gate test, migration tests (unmarked `>= floor` — including a simulated 59/60 store — reads as the frozen legacy value without a write; `57`/missing rebuild; an unmarked store first opened after a simulated future derive bump rebuilds); `test_session_store_usage_refresh.py` asserts no `usage_derive_%` meta keys after refresh — keep the new key out of that namespace.

## Program Design

### Types

- `REBUILD_DERIVE_VERSION: str` constant in `little_loops.session_store.lifecycle`; `rebuild_derive_version` `meta` key (inline upsert, string value).

### Signatures

- `rebuild_needed(db: Path | str) -> bool` — opens the store read-only; True when `rebuild_derive_version != REBUILD_DERIVE_VERSION` after applying the implicit frozen-legacy rule for an unmarked `>= _LEGACY_REBUILD_FLOOR` store; version identifiers are compared for equality, not ordered as strings. Replaces the inline `SCHEMA_VERSION` comparison in `hooks/session_start.py`.

### Call Path

- `handle` (`little_loops.hooks.session_start`) → `rebuild_needed` → size gate → detached `little_loops.cli.backfill_worker` `--rebuild` → incremental ingest → dedicated nonblocking replay lock → `rebuild` (or a named pending/contended outcome).

## Acceptance Criteria

- [ ] An unmarked store at `last_rebuild_version >= 58` (tested at 58, 59 and 60) is read as the fixed legacy derive version (no write); `57`/missing rebuilds once. When the current derive version is subsequently bumped, that same unmarked legacy store rebuilds rather than being treated as current.
- [ ] A `SCHEMA_VERSION` bump that does not change derivation does not trigger a rebuild; a `REBUILD_DERIVE_VERSION` bump does.
- [ ] Two concurrent `--rebuild` workers perform exactly one replay (the second re-checks `rebuild_needed()` under the exclusive lock and skips); each worker's transcript is ingested (the second waits under `LOCK_SH`/`LOCK_EX` rather than exiting). A direct `ll-session rebuild` reports contention. Stop usage-refresh workers use their existing lock without sharing the rebuild lock file.
- [ ] The lock-protocol open question is resolved by a spike or test before **3678b** starts, and the outcome is recorded here. Ingest workers use a bounded `LOCK_SH` wait (no unbounded pile-up of blocked workers).
- [ ] The SessionStart hook writes no meta stamp; `rebuild_derive_version` is written only by a successful `rebuild()`. A fingerprint test fails when `_REBUILD_TABLES`/`_REBUILD_SEARCH_KINDS`/predicates/DDL/`_backfill_*` parser source change without a `REBUILD_DERIVE_VERSION` bump.
- [ ] A failed rebuild is not retried until its cooldown expires (state in the lock sidecar, not `meta`); the "rebuild pending" notice explains the stale-derived-tables consequence.
- [ ] Above the size threshold the hook spawns no `--rebuild` and surfaces a pending notice.
- [ ] `test_hook_session_start.py::TestSessionStartRebuild` updated to the new gate; remote stores still never rebuild from a hook.
- [ ] Docs (`HISTORY_SESSION_GUIDE.md`, `CLI.md`, `API.md`, `ARCHITECTURE.md` `last_rebuild_version` wording) updated in end-user shape.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-30_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 64/100 → MODERATE

### Concerns
- Scope is really 3678a (gate) plus 3678b (lock protocol); readiness reflects 3678a. 3678b is explicitly gated on an unrun spike, so do not start it from this score.
- `rebuild_needed()` does not exist yet (the hook currently inlines the `SCHEMA_VERSION` comparison at `session_start.py:203-214`), and `doctor.py` has no rebuild surface. Both are new code, not swaps.
- The "hook worker usually carries a single transcript" premise behind the bounded `LOCK_SH` wait is unverified.

### Outcome Risk Factors
- Moderate per-site complexity: the flock protocol (`LOCK_SH` ingest, `LOCK_EX` replay, re-check under the exclusive lock) spans `backfill_worker.py` and `lifecycle.py` with shared watermark state, and is unproven.
- No existing test harness for a concurrent two-worker replay; the 3678b tests must be built from scratch.
- The fingerprint test over `_backfill_*` source may be noisy (formatting-only edits), with an `ast.dump` fallback already noted.

## Related

- ENH-3666 (structural fix; now blocked by this issue), ENH-3679 (telemetry writer resilience), FEAT-3561 (its `SCHEMA_VERSION` bump is why the legacy rule is a floor).

## Status

**Open** | Created: 2026-09-30 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-09-30T05:10:23 - `defb8cbc-fb4d-4d9b-9b95-eac7264d3124.jsonl`
