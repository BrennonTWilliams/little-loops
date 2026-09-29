---
id: ENH-3543
type: ENH
title: Shared live/rollout coverage selection for Codex usage
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
- ENH-3647
- ENH-3655
blocks:
- ENH-3549
relates_to:
- ENH-3528
- ENH-3655
confidence_score: 70
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
---

# ENH-3543: Shared live/rollout coverage selection for Codex usage

## Summary

Implement one shared coverage-selection policy behind `select_usage_observations` that usage, cost, waste, quality and export readers all use, so that live invocation totals and historical rollout requests covering the same work are counted once where correlation is proven. Split out of ENH-3532 (rollout ingestion); live identity plumbing was further split to ENH-3647 on 2026-09-28, and the independent join spike to ENH-3655 on 2026-09-29. This issue keeps production correlation, selection and reader/export parity.

## Current Behavior

- `select_usage_observations` (`history_reader/usage.py`) yields every row (`ORDER BY id`) with only `since`/`require_run_id` filters — the unreconciled observation sum. It has no session filter.
- Once ENH-3532 ingests rollouts and ENH-3647 stamps live Codex identity, live totals and rollout requests for the same work coexist and are double-counted by every aggregate.
- `templates/dashboard.llat/template.html.j2` sums raw rows (`... FROM usage_events GROUP BY model ORDER BY cost_usd DESC`) and cannot run the Python selector.
- `issue_history/quality_regressions.py` (model-composition weights) and `issue_history/agent_quality.py::_usage_totals` (cost per issue) consume `usage_events` rows with a `session_id`; ENH-3647/ENH-3532 pin both to `channel = 'transcript'` as a holding measure.

## Expected Behavior

### Identity (delivered by ENH-3647)

Live Codex rows carry `session_id = thread.started.thread_id` and a locally generated `invocation_id`, with an identity-basis marker. Rollout rows carry that same **thread ID** from `session_meta.payload.id` plus the span `turn_id` (ENH-3532). The `payload.session_id` root/parent value equals the thread ID only in non-fork fixtures and is not the join key for forks. Every join is qualified by verified host.

### Coverage interval: accounting evidence and unresolved correlation

One `codex exec` invocation = one `turn.completed` (BUG-3531 Decision 6). Its live total equals the sum of the rollout `last_token_usage` records between that invocation's `task_started` and `task_complete` (fixture: 19404 + 19541 = 38945 input, 112 + 5 = 117 output). `exec resume` restarts the total, so each invocation maps to its own `task_started`…`task_complete` span in the same rollout file. Rollout spans have a native key: `task_started`/`task_complete` both carry `payload.turn_id` (e.g. `01a0d1da-dba9-…` and `01a0d1da-f7cb-…` in `rollout-exec-resume.jsonl`). Match on verified host + thread ID + span; equal token sums are a consistency check, not the identity.

The captures prove session identity and matching accounting totals, but not an automatic live-to-span join: live `turn.started` carries no turn ID, and `turn.completed` carries usage without a turn ID. A generated invocation UUID does not establish a rollout span. **Readiness gate owned by ENH-3655:** specify and prove how each live invocation acquires an exact rollout span, including resume, concurrent/ambiguous activity, incomplete transcripts and compaction. No timestamp-nearness, matching-count or run-ID heuristic may certify the join. If producer evidence cannot establish it, keep coverage unresolved; do not declare the complete-match criterion satisfied by synthetic IDs alone.

**ENH-3655 runs the spike now (2026-09-29).** It is unblocked by ENH-3532 and ENH-3647 and must not gate ENH-3647. Scope spans **by thread** (`payload.id`, ENH-3532 gate 1 rule c), never by a `session_id` that forks share with their parent; cross-check each span against `turn_id`; and add a current-version `exec --json` capture, since fixture-only evidence is from 0.152.1 while current producers are 0.154+ (which also emit `token_usage_record` with `turn_id`/`response_id` — check whether that removes the need for an ordering join).

**Candidate join evaluated by ENH-3655:** per verified `(host, thread_id)`, order live invocations by local capture order and rollout spans by native `ordinal` within each verified stream (ordinals are monotonic across `exec resume` within one file: the two spans in `rollout-exec-resume.jsonl` occupy ordinals 1–19 and 21–28). Accept the join only when (a) the thread's live invocation count equals its completed-span count, (b) every span is closed by `task_complete`, and (c) each positional pair's sums match. Any failure — including interactive TUI turns in the same thread that add spans without live rows — leaves the whole thread `overlap_unresolved`. The spike determines whether (a)–(c) suffice or whether an ordering hazard (concurrent `exec resume` on one thread) defeats the join. If it refutes the join and no producer field exists, ship the selector with conservative unresolved behavior only and record complete-match criteria as blocked on producer evidence.

### Selection policy

1. Complete matched coverage: select the rollout request set and suppress the matching live total. Keep per-channel subtotals for audit.
2. Only the live total covers the verified interval: select it.
3. Partial rollout coverage, unmatched legacy live rows, conflicting sums, ambiguous spans, uncertain `token_usage_record`/`token_count` overlap inside a mixed rollout, or mid-invocation compaction (never captured): `coverage='overlap_unresolved'` or `unknown`, with a reason. Do not drop a whole session's live rows because some rollout row exists, or certify a rollout request set while its internal old/new-shape coverage is uncertain.
4. Anything unresolved retains an **unreconciled observation sum** and per-channel subtotals for audit (ENH-3528's observation contract), with unknown aggregate provenance. That sum is not a canonical consumption total, cost/waste total or cache-hit-rate numerator/denominator. Canonical totals and derived rates for the unresolved coverage group are unavailable (`NULL`/`None`) with a reason. Independent proven coverage groups may contribute a labelled known subtotal, but an aggregate containing unresolved groups is partial and must not present that subtotal as a complete total. Cost/waste/export may not bypass this qualification with direct all-row sums. ENH-3549 applies the same rule to the Codex single-session cache rate before its stored-reader cutover.

### Attribution, filtering and export contract

Verified selection must preserve local invocation/run/state attribution. When the exact join proves that rollout requests belong to one live invocation, carry its local `invocation_id`, `run_id`, and `state` onto selected observations with an explicit attribution basis; do not use timestamp-window guesses as identity proof or overwrite conflicting metadata. Conflicts remain unresolved. Test state-level costs and waste reporting, not only global totals.

Reconcile complete candidate coverage before report filters such as `since`, model, or `require_run_id` discard potential counterparts. Define one observation-time/window policy for source reports and exports, including spans crossing the boundary; filtering must not make partial coverage appear complete or remove a matched request merely because its original `run_id` was absent. Keep audit subtotals separate from selected totals.

ENH-3580 independently exports additive provenance columns. This issue owns how a shared snapshot retains selection and unresolved-coverage qualification without exposing private source identifiers. Before implementation, specify a privacy-safe materialized selected-observation table or view plus audit metadata in `build_snapshot_db`, and version any additional allowlist change beyond ENH-3580's v2. Raw `usage_events` listings may retain all observations for audit, but built-in aggregate queries must read the selected representation and exclude unresolved groups from canonical numeric sums. Include `templates/dashboard.llat/template.html.j2`: its built-in cost query currently sums raw usage rows and cannot execute the Python selector inside the browser. Arbitrary user SQL against raw snapshot tables is a raw-data inspection surface, not a promised canonical aggregate; label that distinction in the dashboard.

### Session filter (shared with ENH-3549)

ENH-3656 needs one session's selected observations for the Claude `ll-ctx-stats` cache rate; ENH-3549 later extends the consumer to Codex. Add a paired `host` + `session_id` filter to `select_usage_observations` rather than having readers stream every row (the dashboard notes ~150k rows) and filter client-side. Require `host` whenever `session_id` is supplied; an ID-only call is an error rather than a cross-host read. Candidate correlation is restricted to the verified host/thread pair; reconcile all coverage candidates for that pair before applying report-window and attribution filters. A row with unverified/NULL host identity cannot be silently assigned to the requested host. Whichever of ENH-3543/ENH-3656 lands first adds the paired filter; the other reuses it.

### Quality regressions

Decide whether `quality_regressions.py` model-composition weights and `agent_quality._usage_totals` cost-per-issue should use selected observations (through the selector) or stay pinned to `channel = 'transcript'`. Either way, remove the chokepoint-gate exemption only if the reader moves behind the selector.

## Scope Boundaries

- **In scope**: the live-to-span join only where ENH-3655 proves it; the shared coverage selector; routing usage, cost, waste, quality and export aggregation through it; the `session_id` selector filter if ENH-3656 has not added it.
- **Out of scope**: live identity capture (ENH-3647); rollout ingestion (ENH-3532); Claude live/transcript reconciliation; ENH-3528's rendering contract.

## Program Design

### Types

- Reuse `usage_events.session_id` for the host-observed session ID and the existing `invocation_id` for local correlation (populated by ENH-3647). Qualify identity by verified host and an explicit identity-basis marker. Coordinate span/basis fields with ENH-3532 and ENH-3647 through the epic's migration plan; do not add `host_session_id` or a second `invocation_id`. Legacy unverified identities remain unverified.
- `CoverageSelection` (frozen dataclass): selected rows and basis, per-channel subtotals, unresolved rows with reasons.

### Signatures

- `select_usage_observations(conn, *, since=None, require_run_id=False, host=None, session_id=None)` — retain the existing shared aggregation entry point; the host/session pair is additive and `session_id` requires `host` (see § Session filter). Delegate to an internal coverage policy, such as `select_usage_coverage(rows: Iterable[UsageRow]) -> CoverageSelection`; consumers must not choose between two public selection paths. Record how qualification/audit metadata is carried alongside selected observations before implementation.

### Call Path

- `usage_events` rows → `select_usage_observations` (internal coverage selection) → `_aggregate_usage_events` / history readers / quality regressions / dashboard export

## Integration Map

- `scripts/little_loops/session_store/{schema,queries}.py`, `session_store/schema_manifest.json` (only if span/basis columns are not already added by ENH-3532/ENH-3647).
- `cli/ctx_stats.py`, `history_reader/{models,usage}.py`, `token_provenance.py`, `issue_history/quality_regressions.py`, `cli/artifact/dashboard.py`, `templates/dashboard.llat/template.html.j2` (all under `scripts/little_loops/`).
- Tests: `test_usage_selection_chokepoint_gate.py` (including `test_quality_regressions_query_is_not_flagged`), `test_history_reader_usage.py`, `test_cli_ctx_stats.py`, `test_feat3304_artifact_dashboard.py`, quality-regressions and migration tests. Extend bypass coverage to built-in dashboard aggregation.
- Fixtures: `scripts/tests/fixtures/codex/exec-json-turn.jsonl`, `exec-json-resume.jsonl`, `rollout-exec-resume.jsonl`.

## Implementation Steps

1. Apply ENH-3655's PROVEN/REFUTED join result. Specify the attribution, report-window, canonical-unavailable and materialized-snapshot contracts here; if correlation remains unproven, use conservative unresolved selection.
2. Add coverage selection and add or reuse ENH-3656's paired `session_id` filter behind `select_usage_observations`, preserving verified attribution and qualification metadata.
3. Route quality regressions per § Quality regressions.
4. Materialize privacy-safe snapshot selection and qualification; route built-in dashboard queries through it, label arbitrary raw SQL distinctly, add cross-reader/export regressions and run project checks.

## Impact

- **Priority**: P2.
- **Effort**: Medium.
- **Risk**: Medium — a wrong selection double-counts or drops tokens.

## Acceptance Criteria

- [ ] ENH-3655's producer-backed result is recorded and applied: only proven live invocation-to-rollout span joins suppress a counterpart; refuted or ambiguous joins remain unresolved, including resume and concurrent same-session activity.
- [ ] Existing session/invocation columns are reused; old schemas and unverified legacy identities retain conservative behavior.
- [ ] Selected request rows preserve verified run/state/invocation attribution; conflicting attribution is qualified, and per-state cost/waste totals remain consistent.
- [ ] Date-window boundaries, model filters and `require_run_id` cannot create false completeness; tests cover counterpart rows outside the reporting window and initially unattributed requests.
- [ ] Built-in dashboard aggregation and exported-snapshot queries use a materialized selected representation and agree with source selection, canonical totals, qualification and audit subtotals for matched (if ENH-3655 proves the join), partial and unresolved cases, without leaking private source identifiers. Arbitrary raw SQL is not mislabelled as selected accounting.
- [ ] `select_usage_observations(..., host=..., session_id=...)` limits candidates to the verified host/thread pair and reconciles before report filtering; a single-session read never reports partial coverage as complete, and a same-ID row from another host never enters its totals.
- [ ] `quality_regressions.py` and `agent_quality._usage_totals` either read through the selector or stay channel-pinned, with tests asserting the chosen behavior for sessions holding live + rollout rows.

- [ ] Matching uses verified host + thread ID + turn span, never root/parent ID, run ID, timestamp proximity or equal counts alone; a sum mismatch downgrades to unresolved.
- [ ] Complete matched coverage counts once; partial coverage, unmatched legacy rows, and conflicting or ambiguous observations stay qualified with channel subtotals.
- [ ] Unresolved coverage retains audit observation sums/subtotals but yields no canonical numeric total or derived rate for that group; independent proven groups remain countable as a labelled known subtotal, never a complete aggregate when unresolved groups are present. The Codex single-session cache-rate consumer in ENH-3549 uses this same qualification.
- [ ] A mixed rollout containing new-shape records and old-shape-only or ambiguous `token_count` events retains audit evidence; file-wide suppression cannot make incomplete request coverage appear complete.
- [ ] Usage, cost, waste and shareable-export tests assert the same selection/qualification, retaining ENH-3528's unreconciled-sum fallback for audit only while withholding a canonical total for unresolved coverage.

## Status

**Open** | Created: 2026-09-24 | Priority: P2

---

## Scope Boundary

ENH-3532 owns rollout ingestion and persisted source/span identity. ENH-3647 owns live identity capture. This issue owns verified correlation, attribution-preserving coverage selection, and source/export aggregation parity through the existing `select_usage_observations` entry point. ENH-3580 can land first; its raw-row metadata projection does not certify coverage. The shared schema uses existing `session_id` and `invocation_id` with explicit identity basis.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-24_

**Readiness Score**: 70/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 63/100 → MODERATE

### Concerns
- Epic review resolved column reuse; exact live-to-span correlation and the qualification/export representation remain readiness gates.
- Integration Map now names `scripts/little_loops/session_store/schema_manifest.json`.

### Gaps to Address
- Unresolved `blocked_by`: ENH-3532 and ENH-3647 are needed for production selection; ENH-3655 now owns the independent join spike. Re-run the confidence check after the spike and prerequisites.

### Outcome Risk Factors
- Deep per-site complexity: cross-module identity plumbing (parser → runner → executor → writer) plus a coverage policy behind the existing selector and snapshot/dashboard parity.
- Broad blast radius: usage, cost, waste and export must preserve one selection/qualification contract through `select_usage_observations`.

## Session Log
- `/ll:confidence-check` - 2026-09-25T01:02:49 - `f35cbaf1-740e-46e5-84c9-0ecf04a645f4.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-24T17:53:58 - `5250dd00-ed7b-4310-8dee-527fe13b2b07.jsonl`
