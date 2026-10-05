---
id: BUG-3736
type: BUG
title: Rebuild erases replay usage after raw retention pruning
priority: P1
status: done
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T18:19:36Z'
completed_at: '2026-10-05T21:04:43Z'
parent: EPIC-3562
labels:
- observability
- history
- usage-retention
testable: true
blocks:
- ENH-3732
- ENH-3671
- ENH-3672
- ENH-3673
- ENH-3674
- ENH-3675
- ENH-3676
- ENH-3744
- ENH-3745
- ENH-3746
- ENH-3747
relates_to:
- ENH-3731
- ENH-3733
- BUG-3735
- BUG-3530
- BUG-3715
- ENH-3744
- ENH-3745
- ENH-3746
- ENH-3747
confidence_score: 95
verify_verdict: VALID
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
---

# BUG-3736: Rebuild erases replay usage after raw retention pruning

## Summary

After retention pruning removes compacted raw transcript rows, both full rebuild and incremental usage catch-up delete their already committed replay-derived usage observations. **Stage 1 (this issue)** stops that data loss with one conservative policy: prune never deletes part of a usage-bearing source, every destructive replay path skips held sources, and prune proves, counts and deletes in one transaction. Semantic candidate proof, freshness accuracy, retained-session reader admission and usage search preservation were split out as ENH-3744, ENH-3745, ENH-3746 and ENH-3747 after a 2026-10-05 scope review (Opus `/ll:advise`, confidence 0.75).

## Current Behavior

A temporary-database probe on 2026-10-05 used the committed Claude transcript-v2.1.284 fixture, production `backfill_raw_events`/`backfill_usage_incremental` and production `prune`. Marking the fixture's four raw rows compacted and old made them eligible for retention. Two usage observations remained immediately after pruning, then became zero after either rebuild or `backfill_usage_incremental`. Each mode used a separate temporary database; no project history data was changed.

Verified code facts in `scripts/little_loops/session_store/lifecycle.py`:

- `rebuild` deletes non-live usage through `_REBUILD_TABLE_PREDICATES = {"usage_events": "channel IS NOT 'live'", ...}`.
- `_derive_usage_incremental_conn` runs the same broad delete on a `usage_derive_version` mismatch or when `MAX(raw_events.id)` is below the checkpoint, then replays only surviving raw rows. On append it also deletes every rollout observation for a touched Codex `source_path` before replaying that source's surviving rows.
- `prune` is a plain COUNT then DELETE of compacted raw rows older than the cutoff: no usage-derive check, no `BEGIN IMMEDIATE`.
- `usage_refresh.refresh_raw_events` guards only on compacted surviving rows, so a partially pruned source with no compacted survivor can be replaced while orphaned retained usage exists.

`BEGIN IMMEDIATE` already protects derivation and checkpoint writes, and `raw_events` uses AUTOINCREMENT; neither needs redesign.

Further probes on 2026-10-05 showed that partial pruning is also destructive, which is why a surviving raw pointer is not proof of replayability:

- Pruning lines 3-5 of `transcript-changing-usage-observed.jsonl` leaves the latest observation (481 output tokens, line 5) next to older raw snapshots; rebuild and max-below-checkpoint replay replace it with 4 output tokens from line 2. Re-ingesting older pruned positions (new, larger raw IDs) does the same even when the latest raw survives.
- Pruning only the three `session_meta`/`turn_context` rows of `rollout-exec-resume-v0.158.0.jsonl` downgrades both retained measured observations to `unknown` on rebuild; after pruning all 11 Codex rows, `refresh_usage_source` reinserts all 11 pruned positions plus one append.

## Expected Behavior

Committed replay-derived usage that can no longer be faithfully reconstructed survives full rebuild, first-enable/version-mismatch/max-below-checkpoint catch-up, per-Codex-source append replay, explicit parser-upgrade refresh and repeated calls, with its components, provenance, contract, logical identity, run/state/cost attribution and as-of boundary intact. Missing raw is not a retraction or a fresh zero. No path reads original sources, requalifies or reprices.

Stage 1 achieves this by holding whole sources, not by proving per-record replayability (that is ENH-3744):

- **Prune eligibility.** A usage-capable source's raw rows are deleted only if every one of them is old, compacted and at or below a valid current-version derive checkpoint. If any row is ineligible, the whole source is held. A missing, malformed, negative or version-mismatched checkpoint holds every usage-capable source. Sources that are not usage-capable keep existing retention rules and the dual age/size gates.
- **Hold marker.** When a whole source is deleted, a hold marker for that source is written in the same transaction. The marker is what lets replay guards know that retained usage for that source is non-replayable, including the case where no usage pointer dangles (Codex header-only loss) and when pruned positions are later re-ingested.
- **Replay guard.** The rebuild usage predicate, the version/max-below-checkpoint reset delete, the per-Codex-source append delete and `refresh_raw_events` all skip held sources: no delete of their non-live usage, no replay of their raw rows, no cursor advance. Refresh of a held source is rejected with a bounded diagnostic before it invalidates usage, cursors or checkpoints. Because held sources are never replayed, re-ingested pruned positions cannot roll back or duplicate retained consumption.
- **Legacy seeding.** The schema migration seeds holds, over-holding rather than proving, for: a source with a dangling `source_raw_event_id`; any non-live usage with NULL `source_path` or `observation_key` (hold the whole host/session/channel population, widened if those identities are also missing); a source whose earliest surviving line is above the first line.
- **Atomic prune.** Prune takes its write transaction before reading mutable derive/source proof, counts safe and held rows, deletes, writes markers and commits together; roll back on pre-commit failure. Dry-run uses a consistent read snapshot, writes nothing and predicts both counts. VACUUM stays post-commit best effort.
- **Diagnostics.** The prune result keeps existing keys and adds `retained: {"raw_events": int}` and a sorted `retention_reasons` list drawn from `usage_derive_unverified` (missing/invalid/stale proof), `usage_derive_pending` (checkpoint lags) and `usage_replay_context_required` (whole-source hold). Held rows count once; zero/default fields are present on gated and no-op calls. Propagate through `compact(and_prune=True)` and render in `ll-session` text/JSON.
- **No `_USAGE_DERIVE_VERSION` bump.** Derivation output is unchanged. A schema bump for the marker is required. `REBUILD_DERIVE_VERSION` and the non-usage rebuild fingerprint stay unchanged.

Known accepted limits, to be documented: long-lived sources that keep appending are never pruned; a held source that keeps appending derives nothing new until ENH-3744; usage search rows for held usage are lost on rebuild until ENH-3747; a store pruned before this fix can contain loss that no seeding rule detects.

## Motivation

Retained observations are the accounting evidence for historical reports and quality windows. Routine retention followed by automatic replay must not erase that evidence.

## Proposed Solution

One shared helper decides which sources are held (marker table plus the legacy seeds) and every destructive path consults it. Prune becomes a single `BEGIN IMMEDIATE` transaction that applies the whole-source rule and writes markers. Choose the marker shape in Step 1: a keyed row per `(host, channel, source_path)`, with a NULL `source_path` meaning a population-level hold; reuse existing `meta`/usage link columns where they suffice, and justify any new table with a failing control. Public call signatures are unchanged.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/schema.py` - schema bump, hold marker DDL and legacy seeding migration.
- `scripts/little_loops/session_store/lifecycle.py` - held-source helper; guards in `rebuild`, `_derive_usage_incremental_conn` (reset and per-Codex-source delete) and the replay cursor; transactional `prune`; `compact(and_prune=True)` propagation.
- `scripts/little_loops/session_store/usage_refresh.py` - `refresh_raw_events` held-source rejection before invalidation.
- `scripts/little_loops/cli/session.py` - render `retained`/`retention_reasons` in prune and compact-and-prune text/JSON.
- `scripts/tests/test_session_store_incremental_usage.py`, `scripts/tests/test_session_store_lifecycle.py`, `scripts/tests/test_session_store_usage_refresh.py`, `scripts/tests/test_ll_session.py` - production prune/replay controls below.
- `scripts/tests/rebuild_fingerprint.py`, `scripts/tests/test_enh3678_rebuild_derive_gate.py` - confirm the guard keeps usage-only mutation inside the usage boundary and the non-usage digest unchanged; add the new helper to `PRUNED_NAMES` only if the walker traverses it.
- `docs/reference/API.md`, `docs/reference/CLI.md`, `docs/guides/HISTORY_SESSION_GUIDE.md` - retention, whole-source hold and the accepted limits.

### Dependent Files

- ENH-3744, ENH-3745, ENH-3746, ENH-3747 build on the hold marker and are blocked by this issue.
- ENH-3732 and host adapters ENH-3671-3676 are blocked by this issue: any later `_USAGE_DERIVE_VERSION` bump must land after Stage 1, because the bump triggers the formerly destructive reset in every local-editable project.

### Similar Patterns

BUG-3530 preserved live usage that has no raw replay source. BUG-3715 preserved retention summary nodes after their raw rows were pruned. Both are done.

### Tests

Use temporary databases, committed fixtures and production ingestion/prune/rebuild. Remove copied originals before replay to prove no path reopens them. Compare the complete stored observation (cost, provenance/contract, source/logical identity, run/state, observed/as-of), not counts. Cover:

- Both all-raw-pruned paths (full rebuild and incremental), repeated calls, first-enable/missing metadata, normalizer mismatch, max-below-checkpoint and ordinary Codex-source append.
- Partial Claude prune keeping the 481-token snapshot while older positions are re-ingested with larger IDs: no rollback, no duplicate.
- Codex header/model/turn context pruned while usage raw survives: measured requests are not downgraded; refresh does not reinsert pruned positions.
- Prune eligibility: a source with one recent or uncompacted row is held whole; missing/NULL/malformed/negative/version-mismatched checkpoint holds all usage-capable sources; non-usage sources and the age/size gates are unchanged.
- Dry-run/apply parity, repeated prune, held rows counted once, source isolation, two-connection proof/delete serialization; injected failure before commit rolls back usage/raw/marker state and a post-commit VACUUM failure does not undo retention.
- Replay guard: each of the four destructive paths leaves a held source untouched; explicit refresh of a held source is rejected before invalidating anything; a fully replayable source still refreshes and recovers.
- Legacy seeding for each of the three conditions, including NULL-link population holds that block a second additive observation set.
- Live rows, unknown audit rows and conflicting copies never duplicate, disappear or downgrade; new raw appends keep AUTOINCREMENT ordering.
- `_USAGE_DERIVE_VERSION` and `REBUILD_DERIVE_VERSION` unchanged; non-usage fingerprint unchanged.

## Program Design

### Types

Reuse stored usage observations, source/raw links, logical observation keys and existing version/checkpoint metadata. The only new persisted state is the hold marker; legacy source/key gaps are treated as uncertainty, never as proof of replayability.

### Signatures

- `rebuild(db, *, config=None, max_sessions=None) -> dict[str, int]` — interface unchanged; replaces only usage of non-held sources.
- `backfill_usage_incremental(db) -> int` — interface unchanged; skips held sources in reset and append replay.
- `prune(db, *, config=None, dry_run=False) -> dict` — interface unchanged; adds `retained` and `retention_reasons` keys and applies the whole-source rule.
- `refresh_raw_events(db, source, ...) -> dict` — signature unchanged; rejects a held source with a bounded diagnostic.

### Call Path

`backfill_raw_events` → `backfill_usage_incremental` → committed raw/usage checkpoint → `prune` whole-source eligibility, marker write and delete in one transaction → `rebuild` or `backfill_usage_incremental` consulting held sources → retained usage → shared source/snapshot/session readers.

### Decision Rules

- **Hold, do not prove.** Stage 1 never judges whether an individual record is replayable. A source is deleted whole or held whole; payload keys, raw pointers, timestamps, token equality and line contiguity are never used as proof. Per-record proof belongs to ENH-3744.
- **One guard on every destructive path.** Full rebuild, version/reset replay, per-Codex-source append replay and explicit refresh all consult the same held-source helper. Held sources get no delete, no replay and no cursor or checkpoint advance. The global checkpoint may still advance; the marker, not the checkpoint, is the durable record of skipped work.
- **Over-hold on uncertainty.** Missing links, keys or checkpoint metadata hold the affected source or population; widen the hold when identities are also missing so same-channel double counting is impossible.
- **Markers are lifted only by ENH-3744.** Stage 1 never releases a hold.
- **Atomicity.** Prune acquires its write transaction before reading derive/source proof, counting, deleting and writing markers, then commits once; dry-run reads a consistent snapshot and writes nothing.
- **Version boundary.** No `_USAGE_DERIVE_VERSION` bump. Keep usage-only mutations in helpers already excluded from the non-usage fingerprint; do not exempt real non-usage changes or regenerate away a failing fingerprint.

### Deviations

- 2026-10-05 — Design said legacy seeding holds "any non-live usage with NULL `source_path` or `observation_key`". Implemented as NULL `source_path` or NULL `source_raw_event_id`: `observation_key` is legitimately NULL for every Codex rollout row and for unqualified Claude rows, so keying on it would hold those populations permanently. The population seed also applies only once a derive checkpoint (`usage_derive_version`) exists, because before the first catch-up unlinked legacy rows are expected and the one-time catch-up replaces them.
- 2026-10-05 — Design said `prune` "holds every usage-capable source". Capability is defined pessimistically: a source is non-capable only when the checkpoint is valid, the source has no linked non-live usage and all its rows are at or below the checkpoint; those keep row-level retention. Every other source is deleted whole or held whole.
- 2026-10-05 — The held-source guard for replay lives in `writers._backfill_usage_events` (skips held sources' records) plus the `_REBUILD_TABLE_PREDICATES["usage_events"]` literal and the two `_derive_usage_incremental_conn` deletes, so `rebuild`'s hashed body is unchanged and `REBUILD_DERIVE_VERSION` needs no bump.

## Implementation Steps

1. Add production prune -> full/incremental reproductions, then the partial-Claude, re-ingested-position and Codex missing-context controls. Fix the marker shape and the held-source predicate before touching deletion code.
2. Add the schema bump, marker DDL and legacy seeding migration.
3. Make `prune` transactional with the whole-source rule, markers, `retained`/`retention_reasons` and dry-run parity; propagate through `compact(and_prune=True)` and `ll-session`.
4. Wire the held-source guard into `rebuild`, both `_derive_usage_incremental_conn` delete paths and `refresh_raw_events`; confirm the fingerprint boundary.
5. Exercise concurrency/rollback, update the docs with the accepted limits, and run `python -m pytest scripts/tests/`.

## Impact

- Priority: P1 - routine replay can erase recorded consumption after pruning.
- Effort: Medium - one policy, four guarded paths, one transactional prune, one migration.
- Risk: Medium-high - conservative over-holding trades storage for safety; legacy stores carry residual undetectable loss.

## Steps to Reproduce

1. In a temporary directory, copy scripts/tests/fixtures/claude/transcript-v2.1.284.jsonl to session.jsonl. Create two temporary history databases, one for each replay mode.
2. For each database run ensure_db, backfill_raw_events with host claude-code, and backfill_usage_incremental. There are four raw rows and two measured transcript usage observations.
3. Set raw_events.compacted to 1 and raw_events.ts to 2020-01-01T00:00:00Z in the temporary database. Call prune with analytics.retention.raw_event_max_age_days=1, min_project_age_days=0 and min_db_size_mb=0.
4. Confirm raw count is 0 and usage count is still 2. On the first database call rebuild; on the second call backfill_usage_incremental. Both usage counts incorrectly become 0.

## Root Cause

- File: scripts/little_loops/session_store/lifecycle.py
- Anchors: `_REBUILD_TABLE_PREDICATES`, `rebuild`, `_derive_usage_incremental_conn`, `prune`
- Cause: a non-live channel or touched source is treated as proof of faithful replayability, while retention removes latest or supporting evidence. Prune has no derive coverage check and no proof/delete transaction.

## Acceptance Criteria

- [ ] Production prune followed by two full rebuilds or two incremental catch-ups preserves the complete logical usage snapshot when its raw evidence is gone, for the max-below-checkpoint and normalizer-mismatch paths.
- [ ] First-enable/missing metadata and ordinary per-Codex-source append replay preserve retained usage; mixed live, retained, unknown/conflicting and replayable rows never duplicate, disappear or downgrade; legacy missing links/keys are held, not deleted.
- [ ] Partial pruning cannot replace the retained 481-token Claude snapshot with its 4-token predecessor or downgrade measured Codex requests; re-ingesting older pruned positions cannot roll back, duplicate or reprice retained consumption.
- [ ] Prune deletes a usage-capable source only whole and only when all its rows are old, compacted and at or below a valid current-version checkpoint; missing/malformed/negative/version-mismatched proof holds every usage-capable source; non-usage sources and the age/size gates keep their contract.
- [ ] Prune proof, count, delete and marker write share one write transaction; a concurrent derive or refresh cannot invalidate the proof; pre-commit failure rolls everything back and post-commit VACUUM failure does not undo retention.
- [ ] `retained` and `retention_reasons` (three codes) reach prune and compact-and-prune text/JSON, count held rows once and match dry-run, which writes nothing.
- [ ] `refresh_raw_events` rejects a held source with a bounded diagnostic before invalidating anything; a fully replayable source still refreshes and recovers.
- [ ] Legacy seeding holds sources with dangling raw pointers, NULL-link populations and a missing first line.
- [ ] No automatic path reads original sources, requalifies, reprices or infers a fresh zero; `_USAGE_DERIVE_VERSION` and the non-usage fingerprint are unchanged; docs state the accepted limits; `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- In scope: usage-preserving prune and replay guards across the shared lifecycle.
- Out of scope, tracked separately: semantic candidate proof, per-record replacement and held-source derivation (ENH-3744); freshness/checkpoint reads and cursor writers (ENH-3745); retained-session reader admission (ENH-3746); usage search preservation (ENH-3747). Also out: requalifying unknown history, repricing stored costs, generic derived-table retention, native-source retraction without evidence.

## Related Key Documentation

- docs/ARCHITECTURE.md - raw-to-derived history lifecycle.
- docs/reference/API.md - history rebuild/prune and stored usage contracts.
- docs/reference/CLI.md - user-visible retained/as-of usage.

## Resolution

- **Action**: fix
- **Completed**: 2026-10-05
- **Status**: Completed

### Changes Made
- `session_store/schema.py`: schema v59 — `usage_replay_holds` marker table plus three over-holding legacy seeds (dangling raw link, unlinked usage once a checkpoint exists, missing first line); manifest regenerated.
- `session_store/writers.py`: shared hold helpers (`USAGE_NOT_HELD_SQL`, `load_usage_replay_holds`); `_backfill_usage_events` skips held sources, which covers rebuild, reset catch-up, per-Codex-source append and refresh replay.
- `session_store/lifecycle.py`: rebuild usage predicate and both `_derive_usage_incremental_conn` deletes skip held sources; `prune` is one `BEGIN IMMEDIATE` transaction with the whole-source rule, hold markers, `retained`/`retention_reasons` and dry-run parity; `compact(and_prune=True)` propagates them.
- `session_store/usage_refresh.py`: `refresh_raw_events` rejects a held source (`usage_replay_held`) before invalidating anything.
- `cli/session.py`, docs (`API.md`, `CLI.md`, `HISTORY_SESSION_GUIDE.md`): render and document retention, whole-source hold and the accepted limits.
- Tests: new `test_bug3736_usage_replay_holds.py` (37 tests); existing prune tests now establish a verified derive checkpoint; schema-version asserts bumped to 59. `_USAGE_DERIVE_VERSION`, `REBUILD_DERIVE_VERSION` and the non-usage fingerprint are unchanged.

### Verification Results
- Tests: PASS for every BUG-3736 and session-store suite. Full run: 6 failures and 8 errors outside this change — `test_libsql_integration` (8 errors, identical on a clean checkout) and `test_verify_evidence` (BUG-3738/ENH-3700 issue text); the 5 `test_session_store_writers` version asserts it also showed are fixed.
- Lint: PASS
- Types: PASS

## Status

**Completed** | Created: 2026-10-05 | Completed: 2026-10-05 | Priority: P1

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-05_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Concerns
- Marker shape is still an open Step 1 choice (keyed row vs. reuse of `meta`/usage link columns); `SCHEMA_VERSION` is 58 today, so confirm no other in-flight issue claims the next bump before landing the migration.

### Outcome Risk Factors
- Deep, cross-module change: transactional `prune` rewrite, schema migration with three legacy-seeding rules, and guards in four destructive paths (`rebuild`, both `_derive_usage_incremental_conn` deletes, `refresh_raw_events`). Land in the Step order (reproductions and marker shape first) and keep each guard its own commit.
- Wide blast radius: 11 issues are `blocks`-ed on this, `rebuild` has ~13 production call sites, and `prune` ~30 references; a held-source regression would silently stall every local-editable project. Run the full `python -m pytest scripts/tests/` plus the rebuild fingerprint gate after each guard.
- Over-holding trades storage for safety; verify the dry-run/apply parity and "held rows counted once" controls early.

## Go/No-Go Findings

_Added by `/ll:go-no-go` on 2026-10-05_ — **GO**

**Deciding Factor**: A prune-only guard cannot protect usage from rebuild or incremental deletes on sources that are already partially pruned, so the hold guards on the derive paths are required; the P1 data loss blocks the usage roadmap.

### Key Arguments For
- Loss is reproducible from routine steps (2 observations → 0 after rebuild or incremental catch-up; 481-token snapshot rolled back to 4). Destructive sites: `lifecycle.py` `_REBUILD_TABLE_PREDICATES` (~1038-1041), `_derive_usage_incremental_conn` deletes (~1297, ~1313-1316), `prune` (~2151-2156).
- Follows the BUG-3530 / BUG-3715 pattern with existing infrastructure (`BEGIN IMMEDIATE` already in `backfill_usage_incremental`, `rebuild`, `refresh_raw_events`; v58 migration as template); conservative whole-source hold fails safe.

### Key Arguments Against
- Prune is manual-only and gated by default (365-day project age, 800 MB DB size; `config-schema.json` ~2155-2175, `config/features.py` ~1624-1626); the repro used `min_project_age_days=0` / `min_db_size_mb=0`, so default trigger likelihood is low. A one-clause "prune skips sources with linked non-live usage" guard is a simpler alternative, but only covers future prunes (not partially pruned sources, re-ingestion rollback, or header-only Codex downgrade).
- Scope is heavy and provisional: marker shape undecided (outcome confidence 63/100), `SCHEMA_VERSION` 58 bump contended (ENH-3733, EPIC-3710), seeding migration over a multi-GB `history.db` is slow/risky, and ENH-3744 will rework the hold.

### Rationale
The data loss is real and both sides confirm the cited code facts; the Against case disputes scope and trigger likelihood, not existence. The proposed prune-only guard would not stop rebuild/incremental erasure for already partially pruned sources, so the source-hold guards in rebuild, incremental derive and `refresh_raw_events` are needed. Reuses an established pattern, needs no derive-version bump, and unblocks ~11 downstream issues.

## Session Log

- `/ll:manage-issue` - 2026-10-05T21:04:43 - `275ebb58-903a-4210-9cb0-e88316d19a35.jsonl`
- `/ll:ready-issue` - 2026-10-05T20:46:11 - `220c3879-e2cb-432d-bde7-1606b14318cb.jsonl`
- `/ll:verify-issues` - 2026-10-05T20:43:16 - `e259c64f-4b41-4ee9-a980-9ce90e13acfc.jsonl`
- `/ll:go-no-go` - 2026-10-05T20:40:04 - `3f7a6770-0b20-46cd-bb50-8b8d35e47614.jsonl`
- `/ll:confidence-check` - 2026-10-05T20:36:15 - `7ae7d567-c248-415c-a7a3-57496874466d.jsonl`
- `/ll:advise` - 2026-10-05 - Opus (`claude-opus-5-5`, confidence 0.75) scope review: bundled three defects (usage loss, freshness, reader admission). Rewritten as Stage 1 (whole-source hold, four-path guard, atomic prune, legacy seeding, no usage-version bump); split ENH-3744..3747; made ENH-3671-3676 `blocked_by` this issue; removed ENH-3732 from `relates_to`. Dropped as moot: Codex supporting-context strategy, allocation-vs-chronology rules, accepted path spellings. Confidence scores reset; rerun `/ll:confidence-check`.
- `/ll:confidence-check` - 2026-10-05T20:19:00 - `3e2de759-3a68-4bde-a95a-631efbd7d020.jsonl`
- `/ll:capture-issue` - 2026-10-05T18:25:26 - `e0d3fb45-7fc3-4e7a-a2c8-9ad8bfdb517e.jsonl`
- Earlier pre-implementation reviews and three prior `/ll:advise` rounds (2026-10-05) established the probes above; their added requirements were carried into the split issues.
