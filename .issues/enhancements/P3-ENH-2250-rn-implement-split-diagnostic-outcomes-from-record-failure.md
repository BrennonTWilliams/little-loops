---
id: ENH-2250
title: "rn-implement conflates SCORES_MISSING / SIZE_REVIEW_FAILED diagnostics with implementation failures"
type: ENH
priority: P3
status: done
confidence_score: 100
outcome_confidence: 85
discovered_date: "2026-06-20"
discovered_by: audit
completed_at: 2026-06-20T20:22:03Z
relates_to: [ENH-2247]
labels: [loop, fsm, rn-implement, observability, enhancement]
---

# ENH-2250: rn-implement splits diagnostic outcomes out of the generic failure bucket

## Summary

`rn-implement.yaml` collapsed two **diagnostic** sub-loop outcomes —
`SCORES_MISSING` (emitted by `rn-remediate`) and `SIZE_REVIEW_FAILED` (emitted by
`rn-decompose`) — into the generic `record_failure` state, conflating tooling /
diagnostic errors with genuine implementation failures. This obscured operator
triage: a run's `failed` count mixed real `ll-auto` crashes with "scores could not
be read" and "size review was inconclusive" conditions, which have different causes
and remedies. This enhancement splits both outcomes into distinct diagnostic record
states with separate tallies in the run summary.

Surfaced during the ENH-2247 audit of `rn-remediate` and its loop family, and
implemented in the same session. Tracked separately because it is a `rn-implement`
(parent orchestrator) change, distinct from ENH-2247's `rn-remediate` refine-variant
split.

## Current Behavior (before)

Both diagnostic tokens fell through the parent's routing chain to `record_failure`:

- `route_rem_rate_limited.on_no → record_failure` caught `IMPLEMENT_FAILED` **and**
  `SCORES_MISSING` (inline comment acknowledged the conflation).
- `route_dec_rate_limited.on_no → record_failure` caught `SIZE_REVIEW_FAILED`.

`record_failure` writes an untagged line to `failures.txt`, so `report` counted all
three conditions as `failed` with no way to distinguish them.

## Implemented Behavior (after)

Each diagnostic outcome is routed to a dedicated record state that writes a **tagged**
line to `failures.txt` and continues the queue (`next: dequeue_next`) — mirroring the
existing `record_sub_loop_crash` convention (ENH-2005). `report` tallies each tag
separately and subtracts it from the headline `failed` count.

### States added (`scripts/little_loops/loops/rn-implement.yaml`)

- `route_rem_scores_missing` — `output_contains` router on `${captured.rem_outcome.output}`
  matching `SCORES_MISSING`; `on_yes → record_scores_missing`, `on_no/on_error → record_failure`.
- `route_dec_size_review_failed` — `output_contains` router on `${captured.dec_outcome.output}`
  matching `SIZE_REVIEW_FAILED`; `on_yes → record_size_review_failed`, `on_no/on_error → record_failure`.
- `record_scores_missing` — shell state; appends `<ts> <ID> SCORES_MISSING` to `failures.txt`; `next: dequeue_next`.
- `record_size_review_failed` — shell state; appends `<ts> <ID> SIZE_REVIEW_FAILED` to `failures.txt`; `next: dequeue_next`.

### Routing rewired

| Caller | Before | After |
|---|---|---|
| `route_rem_rate_limited.on_no` / `on_error` | `record_failure` | `route_rem_scores_missing` |
| `route_dec_rate_limited.on_no` / `on_error` | `record_failure` | `route_dec_size_review_failed` |

### `report` tally

`FAILURES = TOTAL_FAILURES − SUB_LOOP_CRASHES − SCORES_MISSING − SIZE_REVIEW_FAILED`,
with new `summary.json` keys `scores_missing` and `size_review_failed` and a matching
human-readable echo line.

## Motivation

`failures.txt` is the operator's triage surface for a `rn-implement` run. A scoring
read error (`/ll:confidence-check` ran but frontmatter scores could not be parsed) and
a size-review tooling error (`/ll:issue-size-review` errored or was inconclusive) are
infrastructure/diagnostic signals, not "the implementation failed" — they warrant a
different response (inspect tooling, not reopen the issue as un-implementable). Keeping
the headline `failed` count honest, the way `SUB_LOOP_CRASH` already is, restores that
distinction.

## Integration Map

### Files Modified
- `scripts/little_loops/loops/rn-implement.yaml` — 2 router states, 2 record states, `report` tally update.

### Similar Patterns
- `record_sub_loop_crash` (`rn-implement.yaml`) — the ENH-2005 precedent: tagged
  `failures.txt` line + separate `grep -c` tally in `report`. The new states follow it exactly.

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestRnImplementDiagnosticOutcomes`: asserts
  the rate-limit routers hand off to the new routers, the routers match the correct
  token and split to the record states, the record states tag `failures.txt` and
  continue via `dequeue_next`, and `report` tallies both diagnostics separately.
- `scripts/tests/test_rn_implement.py` — `TestValidation::test_state_count_is_orchestrator_sized`:
  orchestrator state-count ceiling raised 31 → 35 (+4 states) with documented rationale.

### Documentation
- N/A — internal orchestrator routing; the diagnostic split is self-documenting via `summary.json` keys.

## Scope Boundaries

- **In scope**: splitting `SCORES_MISSING` / `SIZE_REVIEW_FAILED` out of `record_failure`
  in `rn-implement.yaml`; adding routers, record states, and `report` tallies.
- **Out of scope**: changes to the tokens emitted by `rn-remediate` / `rn-decompose`
  (unchanged); changes to `record_failure`, `record_sub_loop_crash`, or the rate-limit
  paths; ENH-2247's `rn-remediate` refine-variant split (sibling work).

## Acceptance Criteria

- [x] `SCORES_MISSING` routes to `record_scores_missing`; `SIZE_REVIEW_FAILED` routes to `record_size_review_failed`.
- [x] Both diagnostic record states write a tagged line to `failures.txt` and continue the queue (`next: dequeue_next`).
- [x] `report` subtracts both from the headline `failed` count and exposes `scores_missing` / `size_review_failed` in `summary.json`.
- [x] Genuine `IMPLEMENT_FAILED` still routes to `record_failure` (unchanged).
- [x] `ll-loop validate rn-implement` passes with no new errors or warnings.
- [x] Full test suite green (`TestRnImplementDiagnosticOutcomes` + raised state-count ceiling).

## Impact

- **Priority**: P3 — observability/triage improvement; not blocking, but removes a long-standing conflation in the operator-facing failure surface.
- **Effort**: Small — 4 states + a `report` tally in one YAML file, mirroring an existing pattern.
- **Risk**: Low — additive routing; `record_failure` semantics unchanged; worst case reverts one YAML file.
- **Breaking Change**: No — internal FSM routing only; `summary.json` gains keys (additive).

## Resolution

Implemented 2026-06-20 alongside ENH-2247 (`rn-remediate` refine-variant split).
`ll-loop validate rn-implement` passes; full suite green (12,189 passed) after raising
the orchestrator state-count ceiling to 35.


## Session Log
- `hook:posttooluse-status-done` - 2026-06-20T20:23:26 - `9738b7dd-b6f3-4159-beb5-1d8c74a52054.jsonl`
