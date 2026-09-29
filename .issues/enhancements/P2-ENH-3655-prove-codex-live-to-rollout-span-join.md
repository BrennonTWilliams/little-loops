---
id: ENH-3655
type: ENH
title: Prove Codex live-to-rollout span join
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T05:07:09Z'
parent: EPIC-3562
epic: EPIC-3562
labels:
- observability
- multi-host
relates_to:
- ENH-3532
- ENH-3647
- ENH-3543
blocks:
- ENH-3543
---

# ENH-3655: Prove Codex live-to-rollout span join

## Summary

Prove or refute a producer-backed join from Codex live invocations to rollout turn spans before implementing ENH-3543. Capture a current-version exec/resume/fork fixture, test thread-qualified span ordering and ambiguity, and record a conservative unresolved fallback. This research can run before ENH-3532 and ENH-3647 finish.


## Current Behavior

The committed Codex 0.152.1 captures show that a live `turn.completed` total can equal the sum of rollout `last_token_usage` records in one `task_started`–`task_complete` span. They do not prove how a live invocation identifies that span: the live event has no `turn_id`. ENH-3543 proposes an ordering join but is hard-blocked on rollout ingestion and live identity, while this evidence work can run now.

## Expected Behavior

Record a producer-backed **PROVEN** or **REFUTED** result for the exact live-to-span join before ENH-3543 implements coverage selection. A token-sum match is a consistency check, never identity by itself. Ambiguous, incomplete or concurrent activity yields `overlap_unresolved`; a refuted join does not block a conservative selector.

## Scope Boundaries

- **In scope**: paired live/rollout capture, the ordering-join spike, fixture-backed counterexamples, and a written contract for what correlation is safe.
- **Out of scope**: rollout ingestion and its request key (ENH-3532), live identity persistence (ENH-3647), production coverage selection and dashboard/export changes (ENH-3543).

## Integration Map

- `scripts/tests/fixtures/codex/` — add sanitized current-version paired `exec --json` and rollout captures, including resume and fork/subagent evidence where observable. Reuse ENH-3532's new fixtures rather than duplicating them; make join-critical captures here so this issue does not wait for ENH-3532.
- `scripts/little_loops/session_store/sessions.py` and Codex parser tests — verify that the rollout thread ID is `session_meta.payload.id` and distinguish it from a fork's parent `payload.session_id`.
- `scripts/tests/spike/` or a focused fixture-backed test — exercise completed spans, extra interactive turns, missing prefixes, concurrent or ambiguous resume, compaction/window changes and a current producer's `token_usage_record` fields.
- ENH-3543 — consume the recorded verdict and fixtures; no production migration belongs to this spike.

## Implementation Steps

1. Capture a versioned current Codex live invocation and its rollout, plus resume and fork/subagent cases; sanitize and document how each pair was identified. Coordinate fixture reuse with ENH-3532.
2. For each verified `(host, thread_id)`, test the candidate order of live invocations against closed rollout `turn_id` spans in native-ordinal order. Check pair counts and disjoint token sums; challenge ordering with interactive activity, incomplete capture, compaction and concurrent resume.
3. Record PROVEN/REFUTED, the exact evidence boundary, and any safe per-case match rule in this issue and ENH-3543. If unproven, specify the unresolved fallback and which producer field would be needed.

## Impact

- **Priority**: P2 — a false join silently drops or double-counts usage.
- **Effort**: Small to medium — evidence capture and a bounded spike.
- **Risk**: Medium — current producer behavior may refute the candidate join.
- **Breaking Change**: No.

## Acceptance Criteria

- [ ] Versioned, sanitized paired live/rollout fixtures include a current producer, resume and fork/subagent identity; fixture gaps are stated explicitly.
- [ ] The result is recorded as PROVEN or REFUTED with the exact conditions tested. Equal counts, timestamps, generated invocation UUIDs and run IDs alone never certify a match.
- [ ] Tests or a reproducible spike cover missing/incomplete spans, extra interactive turns, ambiguous concurrent activity, and a mismatched sum. Each such case remains unresolved.
- [ ] ENH-3543 cites the result and uses verified host + thread ID + turn span. If the join is refuted, its acceptance criteria permit a conservative unresolved selector without claiming complete match.

## Status

**Open** | Created: 2026-09-29 | Priority: P2
