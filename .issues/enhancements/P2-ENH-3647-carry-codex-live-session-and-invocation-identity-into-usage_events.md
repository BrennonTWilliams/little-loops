---
id: ENH-3647
type: ENH
title: Carry Codex live session and invocation identity into usage_events
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T01:55:16Z'
parent: EPIC-3562
epic: EPIC-3562
labels:
- observability
- multi-host
relates_to:
- ENH-3543
- ENH-3532
- ENH-3528
blocks:
- ENH-3543
---

# ENH-3647: Carry Codex live session and invocation identity into usage_events

## Summary

Capture the Codex host-observed session ID (`thread.started.thread_id`) and a locally generated invocation correlation ID on every live Codex usage observation, and persist both to `usage_events`. Split out of ENH-3543 (2026-09-28) because the plumbing does not depend on ENH-3532's rollout ingestion; ENH-3543 keeps the coverage selector and the live-to-span join.

## Current Behavior

- `record_usage_event` (`little_loops.session_store.writers`) has no `session_id` parameter; it accepts `invocation_id`, but `FSMExecutor._finish` never passes it. Live rows therefore carry neither identity.
- The FSM runners do not read `thread.started`.
- `usage_from_event` (`subprocess_utils.py`) parses only the terminal `turn.completed` usage block.
- The non-fork fixtures establish the identity: `exec-json-turn.jsonl` / `exec-json-resume.jsonl` emit `thread.started.thread_id = 01a0d1da-…`, equal to the rollout's `session_meta.payload.id` (and, only in those non-fork fixtures, `payload.session_id`) in `rollout-exec-resume.jsonl`.
- `issue_history/quality_regressions.py` weights model composition with `SELECT session_id, model, COUNT(*) FROM usage_events WHERE session_id IS NOT NULL GROUP BY session_id, model`. Today only transcript rows have a `session_id` (v53 set `channel='transcript'` exactly where `session_id IS NOT NULL`), so that predicate is a de-facto channel filter. `test_usage_selection_chokepoint_gate.py::test_quality_regressions_query_is_not_flagged` exempts it from the chokepoint.

## Expected Behavior

- The runner captures `thread.started.thread_id` and stamps it on the invocation's collected observations; `usage_from_event`'s signature is unchanged.
- Each live invocation gets a local UUID in the existing `invocation_id` column, marked as locally generated and never presented as host-observed.
- Live rows reuse the existing `usage_events.session_id` column, qualified by verified host plus an identity-basis marker (`host_observed` vs `local`), with field names agreed with ENH-3532 (see epic § Schema coordination). No `host_session_id` column and no second invocation column.
- **Which id.** `thread.started.thread_id` equals the rollout's `payload.id` and, in non-forked sessions, `payload.session_id` (fixtures). In forked rollouts `payload.session_id` is the parent's id, so this issue follows ENH-3532 gate 1 rule c: store the thread id (`payload.id`) in `usage_events.session_id`. `codex exec` cannot fork, so live rows only ever see thread ids; confirm against a 0.155 `exec --json` capture, since the fixtures are 0.152.1. ENH-3543's correlation must also require verified host, not thread ID alone.
- Rows written before this change stay unverified; nothing is backfilled.
- `quality_regressions.py` **and `agent_quality._usage_totals`** are pinned to their current meaning (`channel = 'transcript'`), so live rows that newly carry a `session_id` do not change model-composition weights or cost-per-issue totals (`_usage_totals` would otherwise double-count tokens and add unpriced rows that can drop priced coverage below the threshold and hide the verdict). If ENH-3532 lands first and already pinned them, this is a no-op. Whether rollout/live rows should contribute is ENH-3543's decision.
- Readers still treat live + rollout rows as an unreconciled observation sum (ENH-3528) until ENH-3543 lands.

## Scope Boundaries

- **In scope**: live Codex identity capture through runner → executor → writer; identity-basis marker; `record_usage_event` accepting `session_id`; the `quality_regressions.py` and `agent_quality.py` channel pins.
- **Out of scope**: the coverage selector, live-to-span correlation and dashboard/export parity (ENH-3543); rollout ingestion (ENH-3532); Claude session identity on live rows.

## Program Design

### Types

- Reuse `usage_events.session_id` and `usage_events.invocation_id`. Add an identity-basis column only via the append-only migration coordinated in the epic.

### Signatures

- `record_usage_event(db_path, *, run_id, ts, state, model, ..., invocation_id: str | None = None, session_id: str | None = None, identity_basis: str | None = None) -> None` — additive keyword-only parameters with conservative `None` defaults (exact basis field name fixed with ENH-3532).
- `usage_from_event(event, *, default_model)` — unchanged.

### Call Path

- `thread.started` → runner identity capture → per-invocation `TokenUsage` stamping → `FSMExecutor._finish` → `record_usage_event`

## Integration Map

- `scripts/little_loops/subprocess_utils.py`, `scripts/little_loops/fsm/runners.py`, `scripts/little_loops/fsm/executor.py` (`_finish`), `scripts/little_loops/session_store/writers.py` (`record_usage_event`), `session_store/schema.py` + `schema_manifest.json` if an identity-basis column is added.
- `scripts/little_loops/issue_history/quality_regressions.py`, `scripts/little_loops/issue_history/agent_quality.py` (`_usage_totals`) — channel pins.
- Tests: `test_subprocess_utils.py`, `test_fsm_runners.py`, `test_fsm_executor.py`, `test_session_store_writers.py`, schema/manifest tests, quality-regressions tests.
- Fixtures: `scripts/tests/fixtures/codex/exec-json-turn.jsonl`, `exec-json-resume.jsonl`.
- Docs: `docs/codex/usage.md`, `docs/reference/API.md` (`record_usage_event`).

## Implementation Steps

1. Agree the identity-basis field name/values with ENH-3532 and record them in both issues.
2. Capture `thread_id` in the runner; generate the local invocation ID; stamp both on collected observations.
3. Extend `record_usage_event` and the `_finish` call; add the migration if a basis column is needed.
4. Pin `quality_regressions.py` and `agent_quality._usage_totals` to `channel = 'transcript'` and update the quality-regressions gate-exemption test to assert the pinned predicate; add a cost-per-issue regression for `agent_quality`.

## Impact

- **Priority**: P2 — prerequisite for any live/rollout reconciliation.
- **Effort**: Small to medium.
- **Risk**: Low to medium — additive columns; the quality-regressions pin prevents a silent weighting change.
- **Breaking Change**: No.

## Acceptance Criteria

- [ ] `thread_id` and a local invocation ID survive parser → runner → executor → `usage_events`; locally generated IDs are distinguishable from host-observed ones (fixture-driven test on `exec-json-turn.jsonl` and `exec-json-resume.jsonl`).
- [ ] Existing `session_id`/`invocation_id` columns are reused; old schemas and pre-change rows keep conservative (unverified) behavior.
- [ ] Live Codex rows gaining a `session_id` do not change `quality_regressions` model-composition output or `agent_quality` cost-per-issue output (regression tests).
- [ ] Usage/cost readers still report live + rollout as an unreconciled sum; no selection change ships here.

## Status

**Open** | Created: 2026-09-29 | Priority: P2
