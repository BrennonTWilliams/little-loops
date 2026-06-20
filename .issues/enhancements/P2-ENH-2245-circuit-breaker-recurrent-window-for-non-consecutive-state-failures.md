---
id: ENH-2245
type: ENH
priority: P2
status: done
captured_at: '2026-06-20T00:00:00Z'
completed_at: '2026-06-20T17:59:41Z'
discovered_date: 2026-06-20
discovered_by: audit-loop-run
labels:
- enhancement
- fsm
- executor
- reliability
relates_to: FEAT-1637
confidence_score: 91
outcome_confidence: 88
score_complexity: 17
score_test_coverage: 25
score_ambiguity: 21
score_change_surface: 25
---

# ENH-2245: Circuit breaker recurrent-window for non-consecutive repeated state failures

## Summary

The FSM circuit breaker (FEAT-1637, now `done`) fires only on **back-to-back** visits
to the same `(state, exit_code, verdict)` triple. When the same state fails repeatedly
but with intermediate states between each visit, the stall goes undetected. In the
`2026-06-20T035602` general-task run, `run_final_tests` failed 18 times with identical
`(exit_code=1, verdict=no)` — but because 8 intermediate states separated each visit,
the circuit breaker never triggered, and the loop burned 144/201 iterations on the
same recurring failure.

## Current Behavior

`circuit.repeated_failure` tracks consecutive visits only. The `run_final_tests` failure
pattern:

```
run_final_tests(fail) → continue_work → select_step → do_work → verify_step →
mark_done → check_done → count_done → final_verify → run_final_tests(fail) → ...
```

...is never flagged because `run_final_tests` is never visited on two consecutive
global iterations.

## Expected Behavior

`circuit.repeated_failure` gains an optional `recurrent_window` key. When set, the
circuit breaker also fires when the same `(state, exit_code, verdict)` triple has been
seen ≥`recurrent_window` times across any iterations in the current run (not just
consecutive ones). This catches the "recurring failure with work cycles in between" pattern.

## Motivation

The consecutive stall detector (FEAT-1637) left a coverage gap: loops that rotate through a cycle of states can burn unbounded iterations on a recurring failure without triggering any guard. The `2026-06-20T035602` general-task run is the concrete proof — `run_final_tests` failed 18 times identically but the circuit breaker never fired, consuming 144 of 201 iterations on a known-bad state combination.

- **Reliability**: Prevents runaway loops that cycle through failing states indefinitely
- **Cost**: Reduces wasted token spend on iterations that will never succeed given the current state
- **Observability**: Emits a `circuit_stall` event so the non-consecutive failure pattern is recorded in the audit trail alongside consecutive failures

## Implementation Steps

1. In `scripts/little_loops/fsm/executor.py`, add a `recurrent_counts` dict alongside
   the existing consecutive-failure tracker. Key: `(state_name, exit_code, verdict_str)`,
   value: count of total occurrences.
2. After each evaluate event, increment `recurrent_counts[(state, exit_code, verdict)]`.
3. If `recurrent_counts` value reaches `circuit.repeated_failure.recurrent_window`,
   route to `on_repeated_failure` target (same as the consecutive case).
4. Expose `recurrent_window` in the circuit schema (`scripts/little_loops/fsm/fsm-loop-schema.json`) and document
   in `docs/reference/loops.md` under the `circuit` key.
5. Default: `recurrent_window` is `None` (disabled) so existing loops are unaffected.
6. Suggested default when enabled: 5 (aggressive enough to catch stalls early, permissive
   enough for loops where a state legitimately fails a few times before stabilising).

## Suggested general-task.yaml patch

```yaml
circuit:
  repeated_failure:
    on_repeated_failure: diagnose
    recurrent_window: 5        # NEW: fire after 5 total occurrences of same (state,exit,verdict)
    exclude_paths:
      - "${context.run_dir}/plan.md"
      - "${context.run_dir}/dod.md"
```

## Acceptance Criteria

- [x] `recurrent_window: N` in `circuit.repeated_failure` causes the circuit breaker to
  fire when a `(state, exit_code, verdict)` triple has been seen N times total (not
  necessarily consecutive)
- [x] Existing loops without `recurrent_window` are unaffected
- [x] A `stall_detected` event is emitted on the event bus when the recurrent threshold
  is crossed (matching the existing consecutive-failure event format, using `recurrent` key)
- [x] `scripts/little_loops/fsm/fsm-loop-schema.json` updated with `recurrent_window` field
- [x] `docs/reference/loops.md` `circuit` section documents the new key
- [x] Tests in `scripts/tests/test_fsm_executor.py` cover the recurrent-window trigger (TestRecurrentWindowDetector)

## Context

Observed in loop run `2026-06-20T035602-general-task` (audit-loop-run assessment):
- `run_final_tests`: 19 visits, 18 failures (exit_code=1), 0 circuit-breaker fires
- Pattern: 8 intermediate states between each `run_final_tests` visit
- FEAT-1637 (consecutive stall detector) was in place but didn't catch this variant

## Scope Boundaries

- **In scope**: Adding `recurrent_window` to `circuit.repeated_failure`; tracking total occurrences of `(state, exit_code, verdict)` triples per run; routing to `on_repeated_failure` on threshold breach; emitting `circuit_stall` event; updating `scripts/little_loops/fsm/fsm-loop-schema.json`, `schema.py`, `validation.py`, and `docs/reference/loops.md`
- **Out of scope**: Modifying the existing consecutive-failure counter or its behavior; adding new circuit breaker categories (flapping, slow degradation); cross-run state persistence; changes to how `on_repeated_failure` handles the stall once triggered

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — add `recurrent_counts: dict` alongside consecutive tracker; increment on each evaluate event; check against `recurrent_window` threshold
- `scripts/little_loops/fsm/schema.py` — add `recurrent_window: int | None = None` field to `RepeatedFailureConfig` dataclass; update `from_dict` and `to_dict`
- `scripts/little_loops/fsm/validation.py` — add validation for `recurrent_window >= 2` in the `repeated_failure` validator
- `scripts/little_loops/fsm/fsm-loop-schema.json` — add `recurrent_window` integer-or-null field under `circuit.repeated_failure`; update `additionalProperties: false` is still satisfied
- `docs/reference/loops.md` — document `recurrent_window` key under the `circuit` section

### Dependent Files (Callers/Importers)
- TBD — use `grep -r "repeated_failure\|circuit_stall\|CircuitBreaker" scripts/little_loops/` to find all references

### Similar Patterns
- Existing consecutive-failure counter in `executor.py` — follow same dict + threshold pattern for `recurrent_counts`

### Tests
- `scripts/tests/test_builtin_loops.py` — add recurrent-window trigger tests (explicitly listed in Acceptance Criteria)

### Documentation
- `docs/reference/loops.md` — `circuit` section needs `recurrent_window` key documented
- `scripts/little_loops/fsm/fsm-loop-schema.json` — needs `recurrent_window` field with `null` default

### Configuration
- `scripts/little_loops/fsm/fsm-loop-schema.json` — `recurrent_window: integer | null` under `circuit.repeated_failure`
- `loops/general-task.yaml` — suggested opt-in patch shown in issue body (user-facing example)

## API/Interface

New optional field added to the `circuit.repeated_failure` config object (JSON Schema fragment):

```json
{
  "recurrent_window": {
    "type": ["integer", "null"],
    "minimum": 2,
    "default": null,
    "description": "Fire circuit breaker when the same (state, exit_code, verdict) triple has been seen this many times total in the run (non-consecutive). null = disabled."
  }
}
```

The existing `circuit_stall` event payload format is reused — no new event type required.

## Impact

- **Priority**: P2 — demonstrated in a production run; loops can consume 70%+ of their budget on a known-bad state combination with no guard firing
- **Effort**: Small — adds one `dict` counter alongside the existing consecutive tracker; reuses existing routing and `circuit_stall` event infrastructure
- **Risk**: Low — entirely opt-in via new optional key; `null` default leaves all existing loops unchanged
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-20 | Priority: P2


## Session Log
- `/ll:ready-issue` - 2026-06-20T17:41:15 - `bab42de1-1baf-476a-8d0b-59b760711e27.jsonl`
- `/ll:format-issue` - 2026-06-20T14:27:19 - `baebe263-e6b7-4ad2-8dea-f55423552373.jsonl`
