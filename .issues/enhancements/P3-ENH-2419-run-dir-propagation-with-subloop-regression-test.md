---
id: ENH-2419
title: "Regression test for run_dir propagation across with: sub-loops"
type: ENH
priority: P3
status: open
parent: EPIC-2412
captured_at: '2026-06-30T00:00:00Z'
discovered_date: 2026-06-30
discovered_by: capture-issue
size: Small
relates_to:
- EPIC-2412
- EPIC-1811
labels:
- fsm
- executor
- testing
- regression
---

# ENH-2419: Regression test for run_dir propagation across with: sub-loops

## Summary

The `rn-build-failure-findings.md` analysis identified a framework bug where
runner-managed `run_dir` was **dropped across `with:` sub-loops**
(`FSMExecutor._execute_sub_loop`): the `with:` branch built
`child_fsm.context = {**child_fsm.context, **resolved}` without re-injecting the
parent's `run_dir`, so `goal-cluster`'s `load_goals` interpolated `${context.run_dir}`
to `''` → `os.makedirs('')` → `FileNotFoundError` in 0s, and the run still reported
`done` (6 no-op iterations). The described fix
(`child_fsm.context.setdefault("run_dir", self.fsm.context["run_dir"])`) affects **all**
`with:` sub-loop callers, but there is no dedicated tracked issue and — per the notes —
the fix requested a regression test that may not have landed.

## Motivation

This was a silent, cross-cutting failure that masqueraded as success. A regression test
prevents any future refactor of `_execute_sub_loop` from re-dropping `run_dir` and
reintroducing the "done but built nothing" class of bug.

## Current Behavior

The `run_dir` propagation fix (`setdefault("run_dir", …)` in the `with:` branch of
`FSMExecutor._execute_sub_loop`) has no dedicated tracked issue, and per the
`rn-build-failure-findings.md` notes the requested regression test may not have landed.
Nothing prevents a future refactor from re-dropping `run_dir` across `with:` sub-loops.

## Expected Behavior

A regression test in the standard `pytest scripts/tests/` suite asserts that a `with:`
sub-loop inherits the parent's `run_dir`, that an explicit `with: {run_dir: ...}`
override still wins (setdefault semantics), and confirms the fix is present in
`executor.py`.

## Proposed Solution

1. Confirm the `setdefault("run_dir", …)` fix is present in
   `scripts/little_loops/fsm/executor.py` (the `with:` branch, ~line 545); apply it if
   missing.
2. Add a unit/integration test: a parent loop with a `with:` sub-loop that references
   `${context.run_dir}` in a shell action asserts the child receives the parent's
   `run_dir` (not `''`), and that an explicit `run_dir` in `with:` still wins over the
   default.
3. Cover the contrast with the legacy `context_passthrough` branch, which already
   inherited `run_dir`.

## Acceptance Criteria

- A test fails if `run_dir` is not propagated to a `with:` child; passes with the fix.
- An explicit `with: {run_dir: ...}` override is respected (setdefault semantics).
- Test runs under the standard `pytest scripts/tests/` suite.

## Location

- `scripts/little_loops/fsm/executor.py` (`_execute_sub_loop`, `with:` branch)
- Reference: `rn-build-failure-findings.md` (item 1)

## Scope Boundaries

- **In scope**: Confirming/applying the `setdefault` fix and adding a regression test
  covering `with:` inheritance, explicit-override precedence, and the
  `context_passthrough` contrast.
- **Out of scope**: Broader refactoring of `_execute_sub_loop` or context-merge
  semantics beyond `run_dir` propagation.

## Impact

- **Priority**: P3 - Locks in a fix for a silent, cross-cutting failure that
  masqueraded as success; preventive rather than a live regression.
- **Effort**: Small - Confirm a one-line fix and add a focused unit/integration test.
- **Risk**: Low - Test-only addition (plus a one-line guard if the fix is missing);
  affects no runtime behavior when the fix is already present.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-30 | Priority: P3
