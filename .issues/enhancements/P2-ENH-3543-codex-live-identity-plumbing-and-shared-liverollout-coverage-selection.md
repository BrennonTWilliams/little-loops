---
id: ENH-3543
type: ENH
title: Codex live identity plumbing and shared live/rollout coverage selection
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T17:40:14Z'
labels:
- observability
- multi-host
blocked_by:
- ENH-3532
relates_to:
- ENH-3528
---

# ENH-3543: Codex live identity plumbing and shared live/rollout coverage selection

## Summary

Carry Codex live session/invocation identity through to `usage_events`, and implement one shared coverage-selection policy that usage, cost, waste and export readers all use, so that live invocation totals and historical rollout requests covering the same work are counted once. Split out of ENH-3532, which keeps rollout ingestion itself.

## Current Behavior

- Live observations persisted by `FSMExecutor._finish` → `record_usage_event` have no host-observed session or invocation identity.
- Readers sum every `usage_events` row regardless of channel, so live totals and rollout requests for the same work would be double-counted once ENH-3532 ingests rollouts.

## Expected Behavior

### Identity (fixture-established)

`codex exec --json` emits `thread.started.thread_id` first; it equals the rollout's `session_meta.payload.session_id` (`exec-json-turn.jsonl` / `rollout-exec-resume.jsonl`, both `01a0d1da-…`). Capture it as the host-observed session ID. Generate a separate local invocation correlation ID, marked as locally generated, never as host-observed.

### Coverage interval (fixture-established)

One `codex exec` invocation = one `turn.completed` (BUG-3531 Decision 6). Its live total equals the sum of the rollout `last_token_usage` records between that invocation's `task_started` and `task_complete` (fixture: 19404 + 19541 = 38945 input, 112 + 5 = 117 output). `exec resume` restarts the total, so each invocation maps to its own `task_started`…`task_complete` span in the same rollout file. Match on session ID + span; equal token sums are a consistency check, not the identity.

### Selection policy

1. Complete matched coverage: select the rollout request set and suppress the matching live total. Keep per-channel subtotals for audit.
2. Only the live total covers the verified interval: select it.
3. Partial rollout coverage, unmatched legacy live rows, conflicting sums, ambiguous spans, or mid-invocation compaction (never captured): `coverage='overlap_unresolved'` or `unknown`, with a reason. Do not drop a whole session's live rows because some rollout row exists.
4. Anything unresolved is an **unreconciled observation sum** with unknown aggregate provenance (ENH-3528's contract). Cost/waste/export may not bypass the selector with direct all-row sums.

## Scope Boundaries

- **In scope**: live Codex session/invocation identity through to `usage_events`; the shared coverage selector; routing usage, cost, waste and export aggregation through it.
- **Out of scope**: rollout ingestion (ENH-3532); Claude live/transcript reconciliation; ENH-3528's rendering contract.

## Program Design

### Types

- `usage_events` gains nullable `host_session_id` (host-observed, e.g. Codex `thread_id`) and `invocation_id` (locally generated), plus an identity-basis marker distinguishing host-observed from local IDs. Append-only migration.
- `CoverageSelection` (frozen dataclass): selected rows and basis, per-channel subtotals, unresolved rows with reasons.

### Signatures

- `select_usage_coverage(rows: Iterable[UsageRow]) -> CoverageSelection` — the only aggregation entry point for usage, cost, waste and export readers.
- `usage_from_event(event, *, default_model)` — unchanged signature; the runner captures `thread.started.thread_id` separately and stamps it on collected observations.

### Call Path

- `thread.started` → runner identity capture → `usage_from_event` → `FSMExecutor._finish` → `record_usage_event`
- `usage_events` rows → `select_usage_coverage` → `_aggregate_usage_events` / history readers / dashboard export

## Integration Map

- `scripts/little_loops/subprocess_utils.py`, `fsm/{runners,executor}.py`, `session_store/{writers,schema,queries}.py`, `schema_manifest.json`.
- `cli/ctx_stats.py`, `history_reader/{models,usage}.py`, `cli/artifact/dashboard.py`.
- Fixtures: `scripts/tests/fixtures/codex/exec-json-turn.jsonl`, `exec-json-resume.jsonl`, `rollout-exec-resume.jsonl`.

## Impact

- **Priority**: P2.
- **Effort**: Medium.
- **Risk**: Medium — a wrong selection double-counts or drops tokens.

## Acceptance Criteria

- [ ] `thread_id` and a local invocation ID survive parser → runner → executor → `usage_events`; locally generated IDs are distinguishable from host-observed ones.
- [ ] Matching uses session ID + turn span, never run ID, timestamp proximity or equal counts alone; a sum mismatch downgrades to unresolved.
- [ ] Complete matched coverage counts once; partial coverage, unmatched legacy rows, and conflicting or ambiguous observations stay qualified with channel subtotals.
- [ ] Usage, cost, waste and shareable-export tests assert the same selection/qualification, including ENH-3528's unreconciled-sum fallback.

## Status

**Open** | Created: 2026-09-24 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue owns live identity plumbing and shared coverage selection (split out of ENH-3532); ENH-3532 keeps rollout ingestion and ENH-3528 consumes the selector via a single replaceable aggregation function. Before adding `host_session_id`/`invocation_id` columns to `usage_events`, check the existing identity columns ENH-3528 says to reuse, and either reuse them with a basis marker or state why new columns are needed; also state how ENH-3532's `session_id` on rollout rows joins to live `host_session_id`.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-24T17:53:58 - `5250dd00-ed7b-4310-8dee-527fe13b2b07.jsonl`
