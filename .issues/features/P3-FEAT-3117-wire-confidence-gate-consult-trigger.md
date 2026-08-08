---
id: FEAT-3117
title: Wire confidence_gate consult trigger into the ll-auto readiness gate
type: FEAT
parent: FEAT-3038
priority: P3
status: open
testable: true
discovered_date: 2026-08-08
depends_on:
- FEAT-3116
labels:
- planning-hub
---

# FEAT-3117: Wire confidence_gate consult trigger into the ll-auto readiness gate

## Summary

Child 2 of 3 decomposed from FEAT-3038 (Advisor signal-gated auto-consults and
per-task budget). Wires the `confidence_gate` signal into the single Python
call site FEAT-3038's refinement scoped it to: `issue_manager.py`'s
pre-Phase-1 readiness gate. Depends on FEAT-3116 for `should_consult` and
`consult_for_trigger`.

## Parent Issue

Decomposed from FEAT-3038: Advisor signal-gated auto-consults and per-task
budget. See that issue's "Proposed Solution" → "Trigger dispatch" →
`confidence_gate` subsection and its Option A/B codebase research (2026-08-08)
for the full scoping rationale.

## Current Behavior

`scripts/little_loops/issue_manager.py:788-816` — the ll-auto pre-Phase-1
confidence gate — prints `CONFIDENCE_GATE_BLOCKED <id>` and
`PHASE1_NOT_STARTED <id> confidence_gate` on a sub-threshold readiness score,
then returns `below_readiness_threshold`. No consult happens on this path.

**Scope note (Option A, from FEAT-3038's refinement)**: five FSM loop YAMLs
(`autodev.yaml`, `rn-remediate.yaml`, `rn-implement.yaml`,
`refine-to-ready-issue.yaml`, `recursive-refine.yaml`) each compare against
the same `readiness_threshold` in their own shell/subprocess step via
`ll-issues check-readiness`, never through `issue_manager.py`'s
`readiness_status()`. This child intentionally does **not** wire those —
FEAT-3038's Acceptance Criteria #1 only requires the ll-auto Python call site,
and extending to `ll-issues check-readiness` itself would consult on every
invocation (including read-only/diagnostic ones), which is a larger,
separately-scoped change better suited to its own future issue.

## Expected Behavior

A sub-threshold `confidence-check` readiness score in the ll-auto pre-Phase-1
gate auto-consults the advisor with the gap analysis attached, signal
`confidence_gate`, without changing the existing blocking outcome. The
consult is skipped (not attempted) when `confidence_gate` is absent from
`advisor.triggers`, when `advisor.enabled` is `false`, or when the task's
`max_consults_per_task` budget is exhausted. A failed or timed-out consult
never blocks the gate — it completes with its original
`below_readiness_threshold` verdict and a logged warning.

## Proposed Solution

In `scripts/little_loops/issue_manager.py`'s sub-threshold branch (`:788-816`):
call `should_consult("confidence_gate", config)`; if `True`, call
`consult_for_trigger("confidence_gate", question=..., context=<gap analysis
from readiness_status()/ReadinessStatus>)` (both from FEAT-3116's
`advisor.py`) before returning `below_readiness_threshold`. The consult result
(when present) is logged/attached alongside the existing block output; the
return value and blocking behavior are unchanged either way.

## Acceptance Criteria

1. A `confidence-check` readiness score below
   `commands.confidence_gate.readiness_threshold`, evaluated through
   `issue_manager.py`'s pre-Phase-1 gate, triggers exactly one consult with
   signal `confidence_gate`, and the gap analysis from `readiness_status()` is
   in the consult context (FEAT-3038 AC #1).
2. `confidence_gate` absent from `advisor.triggers` fires no consult on this
   path; `advisor.enabled: false` fires none either (FEAT-3038 AC #3,
   confidence_gate half).
3. A failed or timed-out consult never blocks the gate — it completes with
   its original `below_readiness_threshold` verdict and a logged warning
   (FEAT-3038 AC #7, confidence_gate half).
4. The FSM-embedded readiness gates (`autodev.yaml` and the other four loop
   YAMLs) are unchanged by this issue — out of scope per Option A above.
5. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
   `python -m mypy scripts/little_loops/` pass.

## Tests

- `scripts/tests/test_issue_manager.py` (or nearest existing suite covering
  the pre-Phase-1 gate) — sub-threshold score triggers exactly one consult
  with signal `confidence_gate` and the gap analysis in context; trigger
  unlisted / advisor disabled fires none; a mocked consult failure leaves the
  gate's `below_readiness_threshold` return and logging unchanged.

## Documentation

- `skills/confidence-check/SKILL.md` — document that a sub-threshold score may
  now attach an advisor verdict.

## Impact

- **Priority**: P3 — matches parent FEAT-3038.
- **Effort**: Small — one call site, one branch; the hard budget/identity work
  is already available from FEAT-3116.
- **Risk**: Medium — adds a synchronous network call to a hot gating path;
  mitigated by fail-soft semantics and off-by-default triggers (unchanged from
  parent's risk assessment).
- **Breaking Change**: No — inert unless `advisor.triggers` lists
  `confidence_gate`.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — MR-1 (pair LLM judgment with a
  non-LLM signal).

## Status

**Open** | Created: 2026-08-08 | Priority: P3


## Session Log
- `/ll:issue-size-review` - 2026-08-08T21:18:49 - `5955cc74-6f18-496f-9ff9-59d7e836977d.jsonl`
