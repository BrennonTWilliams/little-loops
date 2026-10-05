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
---

# ENH-3746: Recognize retained-source ingestion in the stored cache-rate reader after raw pruning

## Summary

Make the stored cache-rate reader recognize a selected session as ingested from verified, source-attributed retained usage after its raw evidence is pruned. Split from BUG-3736 because it is a reader-side admission repair that depends on the shared selector work in BUG-3735 and ENH-3731.

## Current Behavior

After production prune deletes all four Claude raw rows of the committed fixture, the two retained observations still exist but `_compute_cache_rate_from_usage` in `cli/ctx_stats.py` returns `session_not_ingested` instead of the earlier 77% as-of rate: its raw-row existence check runs before usage selection.

## Expected Behavior

- The reader admits ingestion from verified, source-attributed committed replay usage when raw evidence is gone, matching host, session and the selected source spelling/resolved path through the shared logical-channel/identity policy. An unrelated source, another host with the same session ID, a live-only row, an unverified legacy row or a cursor alone cannot establish it.
- This is an admission check, not a new source-only metric population: use a separate source-attributed existence/identity check and keep the shared host/session coverage selection, including the hidden ambiguity evidence from BUG-3735. Stage 1's hold marker may serve as source-attributed evidence.
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

- `_compute_cache_rate_from_usage(selected, db_path) -> tuple[float | None, str | None]` — keep the interface; admit retained source-attributed usage before the raw-only absence check.

### Call Path

`ll-ctx-stats` cache-rate command → `_compute_cache_rate_from_usage` → retained-source admission → shared host/session coverage selection → text/JSON output.

### Decision Rules

- Admission is a separate source-attributed existence check, not a new metric population; the shared coverage selection and BUG-3735 ambiguity evidence stay authoritative.
- A cursor, live-only row, unverified legacy row or other host/source cannot establish ingestion; unknown audit evidence admits but never supplies a numeric figure.

## Acceptance Criteria

- [ ] Claude and Codex stored cache-rate text/JSON return the retained as-of rate after all raw/source loss.
- [ ] Same-ID other-host, other-source, live-only, unverified-legacy and cursor-only controls do not establish ingestion; logical NULL-channel identity and legacy-unknown controls pass.
- [ ] Unknown audit evidence establishes ingestion without a numeric rate; unavailable-vs-zero text/JSON semantics hold.
- [ ] BUG-3735 ambiguity evidence and shared coverage selection are unchanged.

## Scope Boundaries

Out of scope: freshness boundary logic, prune/replay preservation, new selector metric populations.

## Status

**Open** | Created: 2026-10-05 | Priority: P2
