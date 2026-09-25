---
id: ENH-3543
type: ENH
title: Codex live identity plumbing and shared live/rollout coverage selection
priority: P2
status: open
parent: EPIC-3562
epic: EPIC-3562
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
confidence_score: 70
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
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

### Coverage interval: accounting evidence and unresolved correlation

One `codex exec` invocation = one `turn.completed` (BUG-3531 Decision 6). Its live total equals the sum of the rollout `last_token_usage` records between that invocation's `task_started` and `task_complete` (fixture: 19404 + 19541 = 38945 input, 112 + 5 = 117 output). `exec resume` restarts the total, so each invocation maps to its own `task_started`…`task_complete` span in the same rollout file. Match on session ID + span; equal token sums are a consistency check, not the identity.

The captures prove session identity and matching accounting totals, but not an automatic live-to-span join: live `turn.started` carries no turn ID, and `turn.completed` carries usage without a turn ID. A generated invocation UUID does not establish a rollout span. **Readiness gate:** specify and prove how each live invocation acquires an exact rollout span, including resume, concurrent/ambiguous activity, incomplete transcripts and compaction. No timestamp-nearness, matching-count or run-ID heuristic may certify the join. If producer evidence cannot establish it, keep coverage unresolved; do not declare the complete-match criterion satisfied by synthetic IDs alone.

### Selection policy

1. Complete matched coverage: select the rollout request set and suppress the matching live total. Keep per-channel subtotals for audit.
2. Only the live total covers the verified interval: select it.
3. Partial rollout coverage, unmatched legacy live rows, conflicting sums, ambiguous spans, or mid-invocation compaction (never captured): `coverage='overlap_unresolved'` or `unknown`, with a reason. Do not drop a whole session's live rows because some rollout row exists.
4. Anything unresolved is an **unreconciled observation sum** with unknown aggregate provenance (ENH-3528's contract). Cost/waste/export may not bypass the selector with direct all-row sums.

### Attribution, filtering and export contract

Verified selection must preserve local invocation/run/state attribution. When the exact join proves that rollout requests belong to one live invocation, carry its local `invocation_id`, `run_id`, and `state` onto selected observations with an explicit attribution basis; do not use timestamp-window guesses as identity proof or overwrite conflicting metadata. Conflicts remain unresolved. Test state-level costs and waste reporting, not only global totals.

Reconcile complete candidate coverage before report filters such as `since`, model, or `require_run_id` discard potential counterparts. Define one observation-time/window policy for source reports and exports, including spans crossing the boundary; filtering must not make partial coverage appear complete or remove a matched request merely because its original `run_id` was absent. Keep audit subtotals separate from selected totals.

ENH-3580 independently exports additive provenance columns. This issue owns how a shared snapshot retains selection and unresolved-coverage qualification without exposing private source identifiers. Specify a privacy-safe selected view/selection result plus audit metadata (or an equivalent representation) and version any additional allowlist change beyond ENH-3580's v2. Raw row listings may retain all observations, but built-in aggregate queries must use the canonical selection. Include `templates/dashboard.llat/template.html.j2`: its built-in cost query currently sums raw usage rows and cannot execute the Python selector inside the browser.

## Scope Boundaries

- **In scope**: live Codex session/invocation identity through to `usage_events`; the shared coverage selector; routing usage, cost, waste and export aggregation through it.
- **Out of scope**: rollout ingestion (ENH-3532); Claude live/transcript reconciliation; ENH-3528's rendering contract.

## Program Design

### Types

- Reuse `usage_events.session_id` for the host-observed session ID and the existing `invocation_id` for local correlation. Qualify identity by verified host and an explicit identity-basis marker. Coordinate new span/basis fields with ENH-3532 through an append-only migration; do not add `host_session_id` or a second `invocation_id`. Legacy unverified identities remain unverified.
- `CoverageSelection` (frozen dataclass): selected rows and basis, per-channel subtotals, unresolved rows with reasons.

### Signatures

- `select_usage_observations(conn, *, since=None, require_run_id=False)` — retain the existing shared aggregation entry point. Delegate to an internal coverage policy, such as `select_usage_coverage(rows: Iterable[UsageRow]) -> CoverageSelection`; consumers must not choose between two public selection paths. Record how qualification/audit metadata is carried alongside selected observations before implementation.
- `usage_from_event(event, *, default_model)` — unchanged signature; the runner captures `thread.started.thread_id` separately and stamps it on collected observations.

### Call Path

- `thread.started` → runner identity capture → `usage_from_event` → `FSMExecutor._finish` → `record_usage_event`
- `usage_events` rows → `select_usage_observations` (internal coverage selection) → `_aggregate_usage_events` / history readers / dashboard export

## Integration Map

- `scripts/little_loops/subprocess_utils.py`, `fsm/{runners,executor}.py`, `session_store/{writers,schema,queries}.py`, `session_store/schema_manifest.json`.
- `cli/ctx_stats.py`, `history_reader/{models,usage}.py`, `token_provenance.py`, `cli/artifact/dashboard.py`, `templates/dashboard.llat/template.html.j2` (all under `scripts/little_loops/`).
- Tests: `test_usage_selection_chokepoint_gate.py`, `test_history_reader_usage.py`, `test_cli_ctx_stats.py`, `test_feat3304_artifact_dashboard.py`, runner/executor and migration tests. Extend bypass coverage to built-in dashboard aggregation.
- Fixtures: `scripts/tests/fixtures/codex/exec-json-turn.jsonl`, `exec-json-resume.jsonl`, `rollout-exec-resume.jsonl`.

## Implementation Steps

1. Close the producer-backed correlation gate and coordinate session/span/basis fields with ENH-3532; record attribution, filter and snapshot contracts before implementation.
2. Carry live session and local invocation identity through runners/executor to the writer, using existing identity columns.
3. Add coverage selection behind `select_usage_observations`, preserving verified attribution and qualification metadata.
4. Integrate privacy-safe snapshot selection and built-in dashboard queries; add cross-reader/export regressions and run project checks.

## Impact

- **Priority**: P2.
- **Effort**: Medium.
- **Risk**: Medium — a wrong selection double-counts or drops tokens.

## Acceptance Criteria

- [ ] A captured producer-backed test establishes the live invocation-to-rollout span join; absent/ambiguous joins remain unresolved, including resume and concurrent same-session activity.
- [ ] Existing session/invocation columns are reused; old schemas and unverified legacy identities retain conservative behavior.
- [ ] Selected request rows preserve verified run/state/invocation attribution; conflicting attribution is qualified, and per-state cost/waste totals remain consistent.
- [ ] Date-window boundaries, model filters and `require_run_id` cannot create false completeness; tests cover counterpart rows outside the reporting window and initially unattributed requests.
- [ ] Built-in dashboard aggregation and exported-snapshot queries agree with source selection, totals, qualification and audit subtotals for matched, partial and unresolved cases, without leaking private source identifiers.

- [ ] `thread_id` and a local invocation ID survive parser → runner → executor → `usage_events`; locally generated IDs are distinguishable from host-observed ones.
- [ ] Matching uses session ID + turn span, never run ID, timestamp proximity or equal counts alone; a sum mismatch downgrades to unresolved.
- [ ] Complete matched coverage counts once; partial coverage, unmatched legacy rows, and conflicting or ambiguous observations stay qualified with channel subtotals.
- [ ] Usage, cost, waste and shareable-export tests assert the same selection/qualification, including ENH-3528's unreconciled-sum fallback.

## Status

**Open** | Created: 2026-09-24 | Priority: P2

---

## Scope Boundary

ENH-3532 owns rollout ingestion and persisted source/span identity. This issue owns live capture, verified correlation, attribution-preserving coverage selection, and source/export aggregation parity through the existing `select_usage_observations` entry point. ENH-3580 can land first; its raw-row metadata projection does not certify coverage. The shared schema uses existing `session_id` and `invocation_id` with explicit identity basis.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-24_

**Readiness Score**: 70/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 63/100 → MODERATE

### Concerns
- Epic review resolved column reuse; exact live-to-span correlation and the qualification/export representation remain readiness gates.
- Integration Map now names `scripts/little_loops/session_store/schema_manifest.json`.

### Gaps to Address
- Unresolved `blocked_by`: ENH-3532 (open). Wait for it, or drop the edge if rollout ingestion is not truly a prerequisite for the live-identity half.

### Outcome Risk Factors
- Deep per-site complexity: cross-module identity plumbing (parser → runner → executor → writer) plus a coverage policy behind the existing selector and snapshot/dashboard parity.
- Broad blast radius: usage, cost, waste and export must preserve one selection/qualification contract through `select_usage_observations`.

## Session Log
- `/ll:confidence-check` - 2026-09-25T01:02:49 - `f35cbaf1-740e-46e5-84c9-0ecf04a645f4.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-24T17:53:58 - `5250dd00-ed7b-4310-8dee-527fe13b2b07.jsonl`
