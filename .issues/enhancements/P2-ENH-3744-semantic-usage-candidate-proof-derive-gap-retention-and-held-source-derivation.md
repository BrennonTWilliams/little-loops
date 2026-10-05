---
id: ENH-3744
type: ENH
title: Semantic usage-candidate proof, derive-gap retention and held-source derivation
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T20:27:33Z'
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
- ENH-3745
- ENH-3746
- ENH-3747
testable: true
---

# ENH-3744: Semantic usage-candidate proof, derive-gap retention and held-source derivation

## Summary

Replace BUG-3736's conservative whole-source usage holdback with semantic proof where proof exists, and let held sources derive new appends again. Stage 1 (BUG-3736) stops the data loss by holding any source whose raw rows cannot all be safely pruned and by guarding every destructive replay path; this child makes that hold precise and releasable.

## Current Behavior

After BUG-3736, prune treats "checkpoint at or above the source's max raw ID" as derivation proof and holds a whole source when any of its rows is ineligible. A recognized usage candidate with no committed representation is not detected, and a held source that keeps appending derives nothing new until its hold is lifted.

## Expected Behavior

- Prune proof requires a committed observation or a proved native coalesced/dedup representation for each recognized usage candidate, using shared native normalization rather than a payload-key heuristic. Unproved candidates are retained with `usage_derive_gap`. Safely derived unknown/partial audit observations satisfy the proof without canonical qualification.
- Terminal non-candidates under the current normalizer (malformed/partial/all-zero Claude snapshots with a native message ID; Codex rate-limit-only notifications) need no fabricated usage row and no indefinite holdback. Unsupported usage-bearing evidence still fails closed.
- Replacement can be per record where proved: replayable records update under native identity/mutation rules; a later retained value is never replaced by an older surviving snapshot; native positions compare only within a proved compatible source (raw IDs and path aliases prove nothing).
- Codex supporting context (header/thread, model/turn/closed-span, adjacent-notification) is retained or the source stays held; a surviving request pointer does not prove it. Document the availability/storage tradeoff.
- A hold marker is lifted only by this proof; new appends to a held source derive without duplicating retained consumption. Legacy observations lacking source links or observation keys stay held conservatively (no value/timestamp matching).

## Impact

- **Priority**: P2 - follow-up split from BUG-3736 (Stage 1)
- **Effort**: Medium-large - Per-record proof needs native normalization sharing and Codex context handling.
- **Risk**: Medium-high - Wrong proof could duplicate or drop retained usage.
- **Breaking Change**: No

## Program Design

### Types

Reuse stored usage observations, source/raw links, logical observation keys and the BUG-3736 hold marker; no new persisted subsystem.

Add a pure, immutable candidate-proof result with a logical source/host/session/channel key and a bounded disposition: represented, missing representation, intentional no-observation, proved excluded channel, or unprovable. These are internal proof outcomes, not new observation provenance values. Representation can be a committed audit observation; canonical admission remains ENH-3731's separate decision. Expose only bounded status/reason through readers, never native keys or paths.

### Signatures

- `prune(db, *, config=None, dry_run=False) -> dict` — keep the interface; replace whole-source hold with candidate proof, adding the `usage_derive_gap` reason.
- `backfill_usage_incremental(db) -> int` — keep the interface; derive appends to held sources and lift holds only under proof.
- Proposed `inspect_usage_candidates(records: Iterable[UsageReplayRecord], observations: Iterable[Mapping[str, Any]], *, channel: str | None = None) -> tuple[UsageCandidateProof, ...]` — pure retained-evidence inspection shared by pruning/replay safety and ENH-3732's read-only reader. Inputs are an ordered retained window for one compatible source, not independent rows: source label + verified host + native stream/session identity; positions compare only within that proved scope. Factor recognition, keys, intentional omission and coalescing from existing producer logic; no SQL writes, native-file reads, pricing or derivation. Do not duplicate a parser/identity algorithm in quality.

### Call Path

`backfill_raw_events` → `backfill_usage_incremental` → `prune` candidate proof → hold lift → `rebuild` → retained usage readers.

### Decision Rules

- Share native normalization (recognition, intentional no-observation, coalescing) with the proof; never use a payload-key heuristic.
- Unsupported usage-bearing evidence fails closed; legacy unlinked usage stays held.
- Compare native positions only within a proved compatible source; raw IDs and path aliases prove nothing.
- Only a recognized ingest-time contract can prove non-usage or an excluded acquisition channel. An empty normalizer result for an unregistered host/version is unprovable, not affirmative absence. Known Claude terminal omissions require the actual verified host/version/native-ID rule; do not generalize malformed/zero omission to another producer.
- Lift a source hold only when every retained observation it protects remains represented or explicitly preserved and every pending candidate has a safe outcome. Inspect the entire held source, including candidates below an advanced global checkpoint; never clear a wildcard population hold on the strength of one source. Legacy unlinked populations remain held. ENH-3745 owns processed boundaries and cursor publication, consuming this outcome without changing semantic proof.

| Pure outcome | Retention/replay action | Transcript quality action |
| --- | --- | --- |
| Represented candidate | Eligible for pruning only with preserved native context and atomic retained-usage protection | Correspondence passes; shared row qualification remains separate |
| Intentional no-observation under a recognized producer rule | No fabricated observation; retain any context another candidate needs | Not an observed zero; cannot conceal another missing candidate |
| Missing representation | Keep raw evidence; do not advance completion for skipped work | `derive_gap` |
| Unprovable identity/contract or missing required context | Keep raw/context and conservation holds | `derive_status_unavailable` |
| Proved channel excluded by this invocation's scope | No permission to prune or release a hold; prune uses all-channel scope | `out_of_scope` only when all session evidence is positively excluded |

Each logical candidate has exactly one outcome. A truncated source window or missing Codex header/model/turn/closure context cannot become intentional no-observation. The pure seam can evaluate only evidence that remains: persisted hold/boundary facts written by the same transaction govern protection and source progress after deletion, without retrospectively claiming a candidate inventory for older already-pruned history. Retained as-of row qualification remains the recorded ENH-3723 policy.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/writers.py` — factor pure native recognition/key/coalescing from `normalize_host_usage` and the Codex replay state; integrate held-source replay without replacing retained observations from incomplete context.
- `scripts/little_loops/session_store/claude_usage.py` — reuse the actual producer qualification/terminal-omission rules; do not requalify absent legacy ingest-time markers.
- `scripts/little_loops/session_store/lifecycle.py` — `_plan_raw_prune`, `_derive_usage_incremental_conn`, destructive replay guards and transactional hold release; preserve the v59 safety floor.
- `scripts/little_loops/session_store/usage_refresh.py` — consume the same safe-to-replace/held disposition in parser refresh; it must not independently clear holds.
- A small shared pure helper module under `session_store/` is permitted if factoring avoids circular imports; no new dependency, general registry framework or persisted candidate ledger is assumed.

### Dependent Files

- `scripts/little_loops/history_reader/usage.py` — ENH-3732 consumes the pure proof; this issue supplies its tested handoff, not the quality/report implementation.
- ENH-3745 owns checkpoint validation/floors, per-source completion/freshness and cursor publication; ENH-3746 owns reader admission, ENH-3747 search restoration. Coordinate shared lifecycle edits without circular scheduling edges.

### Tests

- Extend `scripts/tests/test_bug3736_usage_replay_holds.py` and `test_session_store_incremental_usage.py`; add focused pure-proof tests. Drive real fixture → ingest → derive → prune → append/recovery → rebuild, with original files removed during replay.
- Check parity between the writer's recognition and the pure proof for native valid, coalesced, intentionally omitted, unknown-contract and unsupported-host records. Run the proof with retained inputs only; quality must be able to call it without source reads or writes.

## Acceptance Criteria

- [ ] A recognized candidate without committed or proved-coalesced representation keeps its raw rows and reports `usage_derive_gap`; a current checkpoint alone does not hide it.
- [ ] Ignored malformed/partial/zero Claude snapshots (with and without a prior valid snapshot) and Codex rate-limit-only notifications are not held and produce no usage row; unsupported candidate evidence stays held.
- [ ] Claude latest snapshot pruned with an older survivor, and re-ingested older source positions with larger raw IDs, never roll back, duplicate or reprice the retained observation; repeated unchanged replay is idempotent and proved newer snapshots still update.
- [ ] Codex usage raw surviving with header/model/turn/closure context lost never downgrades a retained measured request or duplicates it.
- [ ] Appends to a held source derive after the hold is lifted or the context is retained, without double counting retained rows.
- [ ] Shared pure proof distinguishes represented audit observations, genuine missing candidates, intentional omissions and unprovable/excluded evidence; a writer's empty result alone cannot certify non-usage. Two snapshots coalesce without false gaps, while two logical candidates with one observation remain a gap. ENH-3732 can consume the result on a read-only connection without invoking derivation.
- [ ] Recovery revisits held candidates below an advanced checkpoint. Hold lifting, observation replacement and preservation commit atomically; a forced failure rolls them back together. Per-source release cannot clear a legacy wildcard hold or affect another source's protected rows.
- [ ] Prune computes proof, protects usage, deletes eligible raw and updates holds/progress under the existing `BEGIN IMMEDIATE` transaction. Pure proof totality/parity and missing-Codex-context tests pass; file reads, pricing and the write normalizer are forbidden in the pure proof test.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Implementation Steps

1. Specify and test the pure proof inputs/outcomes against the existing Claude/Codex producer behavior; hand the interface to ENH-3732/3745.
2. Apply it inside the existing write transaction to prune planning, safe retained replacement and hold release; keep unprovable evidence protected.
3. Replay pending held-source work regardless of the global high-water mark, coordinating per-source progress with ENH-3745; prove failure rollback and recovery.
4. Run the native fixture lifecycle and shared proof parity controls, then the local suite.

## Scope Boundaries

Out of scope: freshness/cursor semantics (ENH-3745), reader admission, search reindex, requalifying unknown history, repricing stored costs.

## Status

**Open** | Created: 2026-10-05 | Priority: P2

## Session Log

- Pre-implementation epic review - 2026-10-05 - Added the shared pure semantic-proof handoff, concrete lifecycle/refresh ownership, atomic hold-release and below-checkpoint recovery controls. A temporary-store probe with one deleted committed observation reproduced checkpoint-only pruning of all four raw rows; the missing candidate must remain protected. No implementation or new readiness score is claimed.
