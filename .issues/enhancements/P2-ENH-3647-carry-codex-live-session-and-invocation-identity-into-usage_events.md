---
id: ENH-3647
type: ENH
title: Carry Codex live session and invocation identity into usage_events
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
completed_at: '2026-09-29T08:22:44Z'
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
- **Which id.** `thread.started.thread_id` equals the rollout's `payload.id` and, in non-forked sessions, `payload.session_id` (fixtures). In forked rollouts `payload.session_id` is the parent's id, so this issue follows ENH-3532 gate 1 rule c: store the thread id (`payload.id`) in `usage_events.session_id`. The 0.158.0 `codex exec fork` capture confirms the new fork's own `thread.started.thread_id`; ENH-3543's correlation must also require verified host, not thread ID alone.
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
- Fixtures: `scripts/tests/fixtures/codex/exec-json-turn.jsonl`, `exec-json-resume.jsonl`, and the paired 0.158.0 exec/resume/fork captures.
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

The original interim reader-sum expectation applied before ENH-3543. Both changes land together; ENH-3543 now qualifies canonical totals.

## Acceptance Criteria

- [x] `thread_id` and a local invocation ID survive parser → runner → executor → `usage_events`; locally generated IDs are distinguishable from host-observed ones (fixture-driven test on `exec-json-turn.jsonl` and `exec-json-resume.jsonl`).
- [x] Existing `session_id`/`invocation_id` columns are reused; old schemas and pre-change rows keep conservative (unverified) behavior.
- [x] Live Codex rows gaining a `session_id` do not change `quality_regressions` model-composition output or `agent_quality` cost-per-issue output (regression tests).
- [x] This identity stage adds no coverage policy; the separately implemented ENH-3543 selector qualifies live + rollout before canonical reporting.

## Status

**Done** | Created: 2026-09-29 | Priority: P2

## Implementation Evidence (2026-09-29)

- The existing FSM runner callback now receives `thread.started.thread_id`; the live parser stamps `session_id`, `identity_basis='host_observed'`, and one local UUID per process onto Codex `TokenUsage`. A missing `thread.started` leaves both host identity fields `None`; it never substitutes the local invocation UUID. `usage_from_event` remains unchanged.
- Codex 0.158.0 resume and fork live totals include earlier requests, so the parser stamps `scope_kind='unknown'`, even though the observation arrives during one invocation. The local UUID supports correlation only; it does not establish a producer request key or an overlap join.
- The 0.152.1 and 0.158.0 producer fixtures exercise own-thread capture, resume retaining the thread ID, fork acquiring a new own-thread ID, and a distinct local invocation ID per process. `record_usage_event` persists the native thread ID, basis and local invocation UUID; an identity-free legacy live row retains `NULL` IDs. The executor passes all three fields. The model-composition and cost-per-issue readers remain pinned to transcript rows even when a live Codex row now has a session ID.
- Focused verification: producer-backed parser/runner/executor/writer tests, 9 passed; existing subprocess and FSM runner tests, 238 passed; issue-history/chokepoint regressions, 4 passed; Ruff and targeted mypy passed. No full suite run in this wave.


## Resolution

- **Action**: Implement
- **Completed**: 2026-09-29
- **Status**: Done

### Changes Made

- Codex live thread and invocation identity persist with an explicit identity basis, while existing cost and quality readers retain their channel pins.

### Verification Results

- Full local suite: 27,525 passed, 301 skipped.
- Ruff lint and format, host-map verifier and private-reference verifier: passed. The configured mypy command is blocked by this environment's untyped `ruamel` dependency; a run with the project config and Python 3.12 target reports existing `no-any-return` and `unused-ignore` errors across the package.


## Session Log
- `/ll:manage-issue` - 2026-09-29T08:22:44 - `688ef729-26a9-43d5-8442-56084d826e08.jsonl`
