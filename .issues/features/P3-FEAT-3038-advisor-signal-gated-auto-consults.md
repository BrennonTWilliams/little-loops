---
id: FEAT-3038
title: Advisor signal-gated auto-consults and per-task budget
type: FEAT
priority: P3
status: open
testable: true
discovered_date: 2026-08-03
depends_on:
- 3037
labels:
- planning-hub
---

# FEAT-3038: Advisor signal-gated auto-consults and per-task budget

## Summary

Slice 2 of the host-agnostic advisor (FEAT-3037). Wire the first two automatic
consult triggers — `confidence_gate` and `pre_done` — to measurable signals the
harness already computes, and add the `max_consults_per_task` budget plus the
per-task counter that makes it enforceable.

This is the slice where the advisor stops being a manual tool and becomes the
signal-gated escalation the design argues for. FEAT-3037 ships the CLI with a
required `--signal` argument precisely so this slice has a contract to fill in.

## Current Behavior

After FEAT-3037:

- `ll-advise` exists and requires `--signal`, but every consult is
  user/model-invoked. `user_requested` is the only signal ever passed.
- `advisor.triggers` is accepted in config but nothing reads it.
- `max_consults_per_task` is deliberately absent from the schema — enforcement
  needs task identity, which does not exist yet.
- `commands.confidence_gate.readiness_threshold` (85) blocks on a sub-threshold
  score and stops there; there is no escalation path.

## Expected Behavior

- A sub-threshold `confidence-check` readiness score auto-consults the advisor
  with the gap analysis, signal `confidence_gate`, instead of only blocking.
- The `Stop` hook, on the final diff, auto-consults with signal `pre_done`
  before a task is declared done.
- Each trigger fires only when listed in `advisor.triggers`; an unlisted trigger
  is inert.
- `max_consults_per_task` caps consults per task; the cap being reached is
  logged and the consult skipped, never silently dropped or retried.
- No consult path exists that does not cite a signal.

## Use Case

An `autodev` run finishes implementing FEAT-2xxx and `confidence-check` returns
a readiness score of 71 against a threshold of 85, with the gap being "test
coverage for the error path is unclear." Today the gate blocks and the operator
reads the gap by hand. With this slice, the sub-threshold score auto-consults an
Opus advisor with the gap analysis attached; the verdict's `recommendation` and
`risks[]` land in the transcript alongside the block, so the next iteration
starts from a stronger read rather than the same model's re-grade.

## Proposed Solution

### Task identity (the prerequisite)

`max_consults_per_task` needs a stable task key. Reuse the existing notion
rather than inventing one: the issue ID when running under `ll-auto`/`ll-sprint`
/`ll-parallel`, the loop run ID under `ll-loop`, and the session ID otherwise.
A small `resolve_task_key()` resolver with that precedence, plus a counter
persisted under the run directory, keeps the cap correct across the subprocess
boundaries these runners cross.

### Trigger dispatch

A single `should_consult(trigger, config)` predicate — checks
`advisor.enabled`, membership in `advisor.triggers`, and the budget — called
from both wiring points so the gating logic has one implementation.

- **`confidence_gate`** — hook into the sub-threshold branch of the
  confidence-gate evaluation, passing the gap analysis as the consult context.
- **`pre_done`** — a `Stop` hook entry in `hooks/hooks.json` dispatching to a
  host-agnostic handler under `scripts/little_loops/hooks/`, consistent with the
  existing handler layout.

Both call `little_loops.advisor.consult()` with an explicit signal. Failures are
non-fatal: a failed consult logs and proceeds, never blocking the primary path.

## Program Design

### Types

- `TaskKey: {kind: Literal["issue", "loop_run", "session"], value: str}`
- `ConsultBudget: {max_per_task: int, spent: int, task_key: TaskKey}`

### Signatures

- `resolve_task_key(env: dict[str, str] | None = None) -> TaskKey`
- `should_consult(trigger: str, config: BRConfig) -> bool`
- `record_consult(task_key: TaskKey) -> int` — returns the new count
- `consult_for_trigger(trigger: str, *, question: str, context: str) -> AdvisorVerdict | None`
- `AdvisorConfig.max_consults_per_task: int` (new field, default 3)

### Call Path

`confidence-gate evaluation` -> `should_consult("confidence_gate", ...)` -> `consult_for_trigger` -> `little_loops.advisor.consult`

`Stop hook` -> `main_hooks()` dispatch -> `pre_done handler` -> `should_consult("pre_done", ...)` -> `consult_for_trigger`

## Integration Map

### Files to Modify

- `scripts/little_loops/advisor.py` — `should_consult`, `consult_for_trigger`,
  `record_consult`, `resolve_task_key`.
- `scripts/little_loops/config/orchestration.py` — add
  `AdvisorConfig.max_consults_per_task`.
- `scripts/little_loops/config-schema.json` — add `max_consults_per_task`
  (deferred out of FEAT-3037 on purpose).
- `hooks/hooks.json` — `Stop` entry for the pre-done consult.
- `scripts/little_loops/hooks/` — new pre-done handler, registered in the
  dispatch table; update the `_USAGE` intent list in `hooks/__init__.py`.
- Confidence-gate evaluation site — add the sub-threshold consult branch.

### Dependent Files (Callers/Importers)

- `skills/confidence-check/SKILL.md` — document that a sub-threshold score may
  now attach an advisor verdict.
- `scripts/little_loops/cli/advise.py` — reuse `should_consult` so the manual
  path is budget-counted too.

### Tests

- `scripts/tests/test_advisor.py` — `should_consult` false when disabled /
  trigger unlisted / budget exhausted; `resolve_task_key` precedence.
- `scripts/tests/test_hook_intents.py` — Stop-hook pre-done dispatch, including
  the no-op path when the trigger is unlisted.
- Budget persistence across a simulated subprocess boundary.

### Documentation

- `docs/reference/CLI.md`, `docs/reference/API.md`, `.claude/CLAUDE.md` hooks
  section.

## Acceptance Criteria

1. A `confidence-check` readiness score below
   `commands.confidence_gate.readiness_threshold` triggers exactly one consult
   with signal `confidence_gate`, and the gap analysis is in the consult context.
2. The `Stop` hook triggers exactly one consult with signal `pre_done` when
   `pre_done` is listed in `advisor.triggers`.
3. A trigger absent from `advisor.triggers` fires no consult; `advisor.enabled:
   false` fires none at all.
4. `max_consults_per_task` is enforced: the Nth+1 consult for the same task key
   is skipped with a logged reason, not attempted.
5. The counter is correct across a subprocess boundary (a consult from a child
   runner increments the same task's count).
6. `resolve_task_key` prefers issue ID, then loop run ID, then session ID.
7. A failed or timed-out consult never blocks the primary path — the gate/hook
   completes with its original verdict and a logged warning.
8. No code path invokes `consult()` without an explicit signal (asserted).
9. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
   `python -m mypy scripts/little_loops/` pass.

## Impact

- **Priority**: P3 — matches FEAT-3037. Without this slice the advisor is an
  ungated manual tool, which is the design's stated failure mode.
- **Effort**: Medium — trigger wiring is small, but task identity spanning the
  runner subprocess boundaries is the real work.
- **Risk**: Medium — adds a synchronous network call to the confidence gate and
  the Stop hook, two hot paths. Mitigated by fail-soft semantics and
  off-by-default triggers.
- **Breaking Change**: No — inert unless `advisor.triggers` lists a trigger.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — MR-1 (pair LLM judgment with a
  non-LLM signal).

## Status

**Open** | Created: 2026-08-03 | Priority: P3
