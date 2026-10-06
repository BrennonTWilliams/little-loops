---
id: ENH-3745
type: ENH
title: 'Usage derive freshness after retention: processed-boundary floor, per-source
  held status and safe checkpoint reads'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T20:27:34Z'
parent: EPIC-3562
labels:
- observability
- history
- usage-retention
blocked_by:
- BUG-3736
relates_to:
- BUG-3735
- ENH-3731
- ENH-3732
- ENH-3744
- ENH-3746
testable: true
---

# ENH-3745: Usage derive freshness after retention: processed-boundary floor, per-source held status and safe checkpoint reads

## Summary

Preserve validated scan progress and proved source completion after retention, diagnose malformed proof safely, and publish source freshness from source-local successful derivation rather than global ingestion progress. Separate ingestion and derived boundaries so skipped work cannot overwrite historical proof. A historical source boundary describes a current figure only when it covers all of that figure's contributors. Own the shared progress/generation storage used by ENH-3744 and deliver their completed writer integration together.

## Current Behavior

On inspected branch `main`, `_set_usage_derive_checkpoint` in `scripts/little_loops/session_store/lifecycle.py` overwrites the checkpoint with surviving `MAX(raw_events.id)` even after prune/rebuild. `_derive_usage_incremental_conn` parses metadata before validating its version and interprets max-below-checkpoint as a replay trigger. Malformed proof can raise `ValueError`. Both source-refresh cursor writers publish source max and complete ingestion witnesses even when holds caused derivation to skip work; one cursor boundary currently serves both ingestion and derived as-of roles.

## Expected Behavior

- Pruning already-processed current-version evidence cannot lower its proved processing floor or spuriously trigger destructive replay. A missing/malformed/version-changed checkpoint or actual skipped/new candidate remains unverified/pending. Allocation high-water, surviving raw max and a retained usage row are never positive processing proof.
- Every reader returns bounded unknown/stale diagnostics for invalid checkpoint or boundary metadata; every writer performs protected recovery or reports incomplete/failure without discarding retained usage or publishing unearned proof.
- Source completion comes from ENH-3744's candidate outcomes, independently of conservation-hold presence. A proved-safe Codex append may complete after pruning while older rows remain protected; missing/unprovable/pending candidates cannot publish complete. An unrelated completed source can be fresh while another remains incomplete.
- Treat `usage_derive_raw_id` as a scan high-water for scheduling. It may pass another source's unresolved work only when that source's generation/version-scoped pending/retry evidence commits alongside it. Completion is source-local semantic proof; no global minimum pending raw ID certifies completion or taints unrelated complete sources.
- Ingestion may advance while derivation is incomplete. Keep its offset/line/stat/tail witness separate from the last successfully derived boundary. Freshness/as-of fields refer to that derived boundary, not the later ingestion cursor or a row timestamp. An absent/unproved derived boundary remains unknown as-of.
- Admission, selected figure and source-boundary facts can be read in the same caller-owned committed revision. Source stat/tail comparisons remain external, against that revision's witness; source loss or change stays stale/unknown and never creates a fresh zero.

## Impact

- **Priority**: P2 — processing/freshness proof currently diverges after retention.
- **Effort**: Medium-large — validated floors, source-local outcomes, distinct boundary persistence and reader integration.
- **Risk**: Medium-high — falsely advanced as-of proof can label incomplete figures fresh; paired writer delivery is required.
- **Breaking Change**: No public call/return break; new optional reader keyword and append-only internal storage.

## Proposed Solution

Share safe checkpoint validation, preserve a justified same-version floor, and persist source-local successful completion separately from ingestion. Factor pure retained-state progress reads for quality and allow the selected cache reader to reuse its pinned read connection for source freshness. ENH-3744 owns semantic proof/retry/mutation, consuming shared generation state from this issue.

## Program Design

### Types

Factor `_valid_usage_checkpoint` into one pure current-version/non-negative-integer validation rule usable on committed state in pruning, catch-up, rebuild, freshness and quality. Check version before numeric conversion; catch malformed/type failures. Missing is distinct from proved zero. The validated value is scan progress only and needs source-local proof before any completion claim. Validate source-boundary offsets/raw IDs/version/status too, not just the global meta value.

Proposed frozen `SourceDeriveCompletion` records bounded source scope and `status` (`complete`, `pending`, `unprovable`), reason, successfully processed boundary/version and outstanding-work disposition. Keep conservation protection distinct from completion: held retained history can coexist with complete safe appends. Internal native positions/witnesses never become shareable reason strings.

Represent ingestion and derived witnesses separately: source host/session/generation, offset/line, tail witness, file identity/stat, version and boundary publication time. The current single `usage_source_cursors` witness cannot describe both a later ingested append and an older derived as-of boundary. This issue owns the next available append-only migration when separate persistence is needed, including `schema_manifest.json`; do not pin an issue-era version (inspected `main` is 60).

Use existing columns where their meanings remain valid; persist only the missing derived/generation/version/pending facts. Include a bounded per-source pending/retry lower bound (with host/session/generation/version scope) sufficient to revisit unresolved work below the scan high-water; it is a scheduling hint, never native order or processing proof. Preserve that marker while pruning resolved neighbors or replaying other sources; invalid scope/bound means unprovable, not complete. Never seed new successful-boundary fields from a legacy complete ingestion cursor/global checkpoint alone when it may have skipped held work. Backfill only with actual compatible completion proof or protected recovery; otherwise keep unknown. ENH-3744 adds no competing ledger/migration.

### Signatures

- Keep `backfill_usage_incremental(db) -> int` and existing refresh/rebuild public payloads; incomplete source outcomes must be represented internally and mapped truthfully to existing status returns.
- `usage_source_freshness(db, source, *, conn: sqlite3.Connection | None = None) -> dict[str, int | str | None]` — gains an optional caller-owned connection. Given `conn`, reuse its read transaction and never open/commit/close a separate history connection. Keep existing `status`, `reason`, `as_of` and `as_of_offset` keys/meanings.
- Proposed read-only `read_source_derive_completion(conn, source_path, *, schema="main") -> SourceDeriveCompletion` for committed state only; validate generated attached aliases. No source stat/parser/pricing. ENH-3732 consumes it alongside candidate proof; cursors are not mandatory for historical quality qualification.

### Call Path

`backfill_usage_incremental` → `_derive_usage_incremental_conn` → validated `_set_usage_derive_checkpoint` and source completion.

`refresh_usage_source` / `_refresh_codex_usage_source` → ENH-3744 proof → distinct ingestion/derived cursor publication → `usage_source_freshness` → `_compute_cache_rate_from_usage`. Quality consumes the pure retained-state completion read.

### Decision Rules

- Preserve the previously validated same-version scan floor and successful source boundaries across retention, including rebuild stamping. Replace the max-below-checkpoint replay trigger with validated continuity/recovery logic; a smaller surviving raw max alone is not a reset. Allocation sequence may expose a contradiction/reset, but never certifies processing or raises the floor. Missing/version-changed/contradictory progress cannot silently coerce to zero and publish complete.
- ENH-3744 owns retrying outstanding candidates below/equal to the global high-water mark. This issue owns source-local pending/completion evidence and both cursor writers. Global progress may advance for other sources; it cannot certify skipped work or make that work unreachable for retry.
- Publish a new derived boundary only for a proved-complete prefix under the matching version/generation; never jump over a missing candidate. Ingestion progress may advance independently while prior successful boundary and incomplete status remain intact. A conservation hold without outstanding unsafe work is not incompleteness.
- Commit the source pending/retry bound whenever scanning passes unresolved candidates; clear/advance it only from ENH-3744's resolved proof. Recovery must find those candidates after restart even with raw max equal to the global scan high-water. Missing legacy completion evidence remains conservative until real proof/recovery establishes it, rather than treating absent pending metadata as affirmative completion.
- Store successful-prefix boundaries as source facts, not snapshots of every current aggregate. Safe additive inserts or replacements beyond a gap may change stored figures while the prefix stays fixed; ENH-3746 suppresses the figure's `as_of`/`as_of_offset` unless all contributing applied-value witnesses are within that compatible selected-source boundary. Preserve the truthful older source fact internally. No arbitrary timestamp, first-seen request position or newer cursor can stand in for that check.
- Source-generation witnesses support compatible native ordering only within their verified scope. Same-path replacement, rotation, copied aliases or a larger newly allocated raw ID cannot certify that an old snapshot is newer. Missing legacy witnesses stay conservative; quality may still qualify recorded as-of observations.
- Source boundaries, observation changes, hold outcomes and validated global proof commit in the same existing `BEGIN IMMEDIATE` write transaction. Failure rolls them back together. Parser refresh invalidates relevant current-version completion without erasing a truthful historical boundary or treating a successful file read as successful derivation.
- Capture admission/usage/boundary under a caller-owned read transaction. A freshness call with no `conn` owns only its own read resources. Detect source change during file comparison and return unknown; absent/unreadable/changed source or absent cursor cannot fabricate freshness/as-of.
- Quality uses only pure retained-state progress and candidate proof. A cursor or current file is not required for retained historical row qualification; a conservation hold alone cannot blanket-reject it.

### Delivery Contract

Implement validation first if useful, then integrate source-local publication with ENH-3744 on one branch and land completed writer changes together. No circular scheduling edges. ENH-3746's final reader integration depends on the optional-connection/boundary handoff; its standalone admission helper can be developed earlier without claiming closeout.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/lifecycle.py` — `_valid_usage_checkpoint`, `_set_usage_derive_checkpoint`, checkpoint recovery, both `_refresh_codex_usage_source`/`refresh_usage_source` cursor writers, rebuild stamping, pure completion read and `usage_source_freshness` connection ownership.
- `scripts/little_loops/session_store/usage_refresh.py` — targeted version/progress invalidation and historical-boundary preservation after parser refresh; do not certify skipped work.
- `scripts/little_loops/session_store/schema.py` and `schema_manifest.json` — next append-only migration for minimal separate derived/generation/pending state where existing columns are insufficient; no automatic legacy certification.

### Dependent Files

- `scripts/little_loops/session_store/writers.py` — ENH-3744 semantic outcomes and safe mutation; integrate shared source-generation proof.
- `scripts/little_loops/history_reader/usage.py` — ENH-3732 consumes validated retained-state proof, including attached-member scope.
- `scripts/little_loops/cli/ctx_stats.py` — ENH-3746 owns admission plus threading its existing connection through freshness; this issue supplies/test-drives the new keyword and semantics.

### Tests

Extend `scripts/tests/test_session_store_incremental_usage.py`, `test_session_store_usage_refresh.py`, `test_enh3549_codex_usage_refresh.py`, `test_bug3736_usage_replay_holds.py` and stored-cache-rate suites. Drive actual production prune/catch-up/rebuild, both cursor writers, invalid global and cursor metadata, source rotation/loss, mixed-source completion and failure rollback. Add migration controls for legacy cursor state that once claimed complete over skipped work. Exercise source A pending at raw ID 5 while B scans/derives through 10: A's retry marker survives restart/pruning of resolved neighbors, B can remain fresh, and A cannot become complete until native proof resolves its work. Fail between pending-marker and scan publication and assert both roll back. Include actual usage replacements beyond an older prefix, with applied-value witness checks through ENH-3746.

## Acceptance Criteria

- [ ] An unchanged available source with current-version successful proof remains fresh after all/partial raw pruning, catch-up and rebuild; no surviving-max regression or allocation sequence manufactures a processing boundary.
- [ ] Missing/invalid/negative/NULL/non-integer/version-mismatched checkpoint and malformed cursor boundary metadata produce bounded diagnostics in freshness and actual stored-reader text/JSON; writers recover safely or report incomplete without damaging retained usage/holds.
- [ ] Both cursor writers keep ingestion separate from derived offset/version/witness/publication time. Missing/unprovable/pending work cannot advance successful proof; safe Codex/Claude appends can complete while conservation guards remain.
- [ ] Mixed-source and same-source mixed-candidate cases preserve the last derived prefix/as-of boundary while ingestion/global progress advances. Recovery revisits old pending candidates under ENH-3744; unrelated completed sources can remain fresh.
- [ ] Validated scan progress is never used alone as processing proof. Generation-scoped pending/retry bounds commit atomically with it, survive restart/retention of resolved neighbors, and drive below/equal-checkpoint recovery; a pending source cannot taint an unrelated complete source via a global completion floor.
- [ ] Source rotation/restore/aliases cannot make older native snapshots safe replacements; invalid legacy generation/boundary state is not automatically certified by migration. Normalizer/parser invalidation remains distinct from raw retention.
- [ ] Forced failure rolls back global/source proof, observation changes and hold outcomes. Rebuild cannot stamp a new version over skipped old-version work or silently lower valid retention progress.
- [ ] Optional-connection freshness reads use the caller's revision without committing/closing it. A concurrent append/derive between figure and boundary acquisition cannot stamp old figures with a newer boundary. Source loss/changes retain truthful old as-of or unknown, never fresh zero.
- [ ] A retained successful source prefix is not published as the whole figure's as-of when safe later inserts/replacements or other-source contributors lie outside it. Internal historical proof remains preserved; ENH-3746 owns bounded unknown/null figure publication without filtering contributors.
- [ ] Quality can read bounded source completion on query-only attached/local connections without stat/parse/write/pricing or mandatory cursors for retained as-of history.
- [ ] ENH-3744/3745 completed writer integration lands together; combined ENH-3746 reader controls and `python -m pytest scripts/tests/` pass.

## Implementation Steps

1. Factor safe global/source metadata validation and optional-connection committed-state reads; reproduce reader/writer invalid-proof controls.
2. Define the shared source outcome and minimal separate derived/generation/pending storage with conservative legacy migration.
3. Preserve justified same-version scan floors/source boundaries and replace retention-induced replay triggers; integrate both cursor writers and durable pending bounds with ENH-3744's prefix-completion/retry outcomes.
4. Prove prune/rebuild/append/mixed-source/source-loss and reader-revision cases plus atomic failure recovery; land paired writer integration and run the local suite.

## Scope Boundaries

No semantic prune eligibility, candidate recognition, hold-release/mutation algorithm or retry iteration (ENH-3744); no ingestion-admission logic (ENH-3746) or search restoration. This issue owns the shared durable boundary/generation state and freshness connection seam.

## Status

**Open** | Created: 2026-10-05 | Priority: P2

## Session Log

- Pre-implementation handoff review - 2026-10-06 - Defined scan-high-water versus source completion, durable generation-scoped retry bounds and atomic restart/retention recovery. Clarified that a preserved prefix is an internal source fact, not necessarily an as-of certificate for later changed figures; applied-value witnesses feed ENH-3746's publication check. Opus confidence 0.74 supported persistent pending evidence; its global-minimum completion floor was rejected because it would unnecessarily taint unrelated sources and uses ingestion order as processing proof. Targeted existing policy/lifecycle/reader/quality/workspace/dashboard/chokepoint suites: 293 passed. No implementation or readiness score claimed.

- Pre-implementation epic review - 2026-10-05 - Reproduced unchanged-source `stale/derive_pending` after all four raw rows were pruned and catch-up ran, plus `ValueError` on malformed checkpoint metadata. Added shared validation, protected writer recovery, both cursor writers and the ENH-3744/3732 per-source handoff; no implementation or new score is claimed.

- Pre-implementation review - 2026-10-06 - Reconciled source completion versus conservation protection, separated ingestion/derived as-of boundaries and assigned minimal migration/generation ownership. Added malformed cursor metadata, conservative legacy backfill, retention replay-trigger recovery and caller-owned freshness reads; required paired ENH-3744 writer delivery. Opus confidence 0.72; allocation sequence remains a contradiction hint, never processing proof. Existing related suites: 188 passed; no implementation/readiness claim.
