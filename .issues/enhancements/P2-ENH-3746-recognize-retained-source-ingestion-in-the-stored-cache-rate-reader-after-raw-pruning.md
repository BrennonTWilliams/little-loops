---
id: ENH-3746
type: ENH
title: Recognize retained-source ingestion in the stored cache-rate reader after raw
  pruning
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
- BUG-3735
- ENH-3731
relates_to:
- BUG-3735
- ENH-3731
- ENH-3732
- ENH-3744
- ENH-3745
testable: true
---

# ENH-3746: Recognize retained-source ingestion in the stored cache-rate reader after raw pruning

## Summary

Make the stored cache-rate reader recognize a selected session as ingested from verified, source-attributed retained usage after its raw evidence is pruned. Split from BUG-3736 because it is a reader-side admission repair that depends on the shared selector work in BUG-3735 and ENH-3731.

## Current Behavior

After production prune deletes all four Claude raw rows of the committed fixture, both retained observations still exist. A selected-session read yields the `session_not_ingested` absence diagnostic instead of the earlier 77% as-of rate. The raw-row existence check in `_compute_cache_rate_from_usage` (`scripts/little_loops/cli/ctx_stats.py`) runs before usage selection.

## Expected Behavior

- The reader admits ingestion from verified, source-attributed committed replay usage when raw evidence is gone, matching host, session and the selected source spelling/resolved path through the shared logical-channel/identity policy. An unrelated source, another host with the same session ID, a live-only row, an unverified legacy row or a cursor alone cannot establish it.
- This is an admission check, not a new source-only metric population: use a separate source-attributed existence/identity check and keep the shared host/session coverage selection, including the hidden ambiguity evidence from BUG-3735. A Stage 1 hold may corroborate retained source attribution, but `usage_replay_holds` has no session ID: it cannot by itself prove the selected host/session or establish ingestion. A wildcard population hold is never source/session evidence.
- Verified source-attributed unknown audit evidence may establish ingestion but never supplies a numeric figure.
- The four absence codes stay. `ingested_without_usage` still means surviving verified raw with no usage; a source with no usage whose raw is entirely pruned reports `session_not_ingested` even when a cursor remains. Document that limitation; do not retain arbitrary non-usage anchors.
- Source-cursor as-of and freshness semantics are unchanged.

## Impact

- **Priority**: P2 - follow-up split from BUG-3736 (Stage 1)
- **Effort**: Small - Admission check in one reader plus controls.
- **Risk**: Low-medium - Must not create a new metric population.
- **Breaking Change**: No

## Program Design

### Types

Reuse stored usage observations with source attribution, the shared logical-channel identity policy and the BUG-3736 hold marker as source-attributed evidence.

### Signatures

- `_compute_cache_rate_from_usage(handle: SessionHandle, db_path: Path) -> tuple[dict[str, Any] | None, str | None]` — keep the actual payload/diagnostic interface; admit retained source-attributed usage before the raw-only absence check. Preserve rate operands, counts, coverage, provenance and freshness/as-of metadata.

### Call Path

`ll-ctx-stats` cache-rate command → `_compute_cache_rate_from_usage` → retained-source admission → shared host/session coverage selection → text/JSON output.

### Decision Rules

- Admission is a separate source-attributed existence check, not a new metric population; the shared coverage selection and BUG-3735 ambiguity evidence stay authoritative.
- A cursor, live-only row, unverified legacy row or other host/source cannot establish ingestion; unknown audit evidence admits but never supplies a numeric figure.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/ctx_stats.py` — `_compute_cache_rate_from_usage` admission and existing text/JSON diagnostics; do not source-filter the subsequent coverage/qualification population.
- `scripts/little_loops/history_reader/usage.py` — add a bounded source-attributed existence helper here if needed to preserve the usage-selector SQL chokepoint. Reuse `row_channel` and verified identity; no new canonical selector.

### Dependent Files

- `scripts/little_loops/session_store/lifecycle.py::usage_source_freshness` — consume freshness unchanged. ENH-3745 owns its invalid-checkpoint and processed-floor repair; admission can be developed independently, with combined closeout tests after both land.
- `scripts/little_loops/session_store/writers.py` — v59 source/population hold shape and durable replay attribution; neither a hold nor cursor manufactures a session.

### Tests

- Extend `scripts/tests/test_enh3656_stored_cache_rate.py`, `test_enh3549_codex_stored_ctx_stats.py` and `test_bug3736_usage_replay_holds.py`; keep `test_usage_selection_chokepoint_gate.py` passing.
- Use real ingestion/derivation followed by production prune, both original spelling/resolved paths, rebuild and original-source loss. Add source-only/population-hold controls with no matching observation, and verify admission does not hide another in-session ambiguous/audit contributor from the actual figure.

## Acceptance Criteria

- [ ] Claude and Codex stored cache-rate text/JSON return the otherwise qualified retained as-of rate after all raw rows are pruned, with available and missing original-source cases. Source loss stays freshness stale/unknown with the actual as-of proof or unknown boundary, never current; a hold cannot certify freshness. Combined ENH-3745 tests cover the preserved processed floor.
- [ ] Same-ID other-host, other-source, live-only, unverified-legacy and cursor-only controls do not establish ingestion; logical NULL-channel identity and legacy-unknown controls pass.
- [ ] Unknown audit evidence establishes ingestion without a numeric rate; unavailable-vs-zero text/JSON semantics hold.
- [ ] BUG-3735 ambiguity evidence and shared coverage selection are unchanged.
- [ ] A hold with no matching verified source/host/session observation, including wildcard population holds, cannot admit the session. Admission does not hide other in-session contributors; the returned payload retains all existing metadata and no source-timestamp boundary is fabricated.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Implementation Steps

1. Add the separate retained-ingestion identity check through the allowed reader seam and preserve the existing payload/absence contract.
2. Prove Claude/Codex prune/rebuild/source-loss admission and negative identity/hold controls without narrowing the metric population.
3. Compose with ENH-3745's floor/invalid-checkpoint tests before the retained-reader closeout gate; run the local suite.

## Scope Boundaries

Out of scope: freshness boundary logic, prune/replay preservation, new selector metric populations.

## Status

**Open** | Created: 2026-10-05 | Priority: P2

## Session Log

- Pre-implementation epic review - 2026-10-05 - Reproduced `session_not_ingested` after production prune while both Claude observations survived (previous rate 77%). Corrected the payload signature, prohibited hold-only session proof and added concrete source-loss/as-of, identity, chokepoint and combined freshness tests. No implementation or new score is claimed.
