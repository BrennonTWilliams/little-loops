---
id: ENH-3464
title: Score harness runs on a named efficiency vector, not only on a pass/fail outcome
type: ENH
priority: P3
status: open
discovered_date: '2026-09-13'
labels:
- evals
blocked_by:
- 'ENH-3462'
parent: EPIC-3475
epic: EPIC-3475
---

## Summary

`ll-harness` reports one of pass, fail, or abstain. Two runners that both satisfy the same semantic criterion are therefore indistinguishable, even when one spent several times the tool calls, tokens, and wall-clock of the other. That is the wrong verdict shape for anything that feeds a selection decision: a wasteful winner reads identically to an efficient one, so promoting on the verdict alone will happily carry the expensive candidate forward.

Add a small, named set of efficiency dimensions to the verdict — tokens, tool calls, and wall-clock at minimum — reported alongside the outcome rather than folded into it. The dimensions must be named in advance and stable, so that a downstream post-mortem matches a run against a taxonomy instead of free-associating about why it was slow.

## Current Behavior

`ll-harness` reports one of pass, fail, or abstain per run. Two runners that both satisfy the same semantic criterion are indistinguishable in the verdict, even when one spent several times the tool calls, tokens, and wall-clock of the other. Most of the raw quantities are already logged, but not surfaced as named dimensions of the verdict.

## Expected Behavior

The verdict carries a small, named, stable set of efficiency dimensions — tokens, tool calls, and wall-clock at minimum — reported alongside (not folded into) the pass/fail/abstain outcome, attached to the run model shipped in ENH-3397 (an attempt recorded against task × repetition × subject). A run that passes expensively still passes; efficiency is reporting, not a second gate. A downstream post-mortem matches a run against this taxonomy instead of free-associating about why it was slow.

## Design

- Most of the raw quantities are already logged; the work is mostly surfacing them as dimensions of a specific run's verdict, and deciding what a comparison across two runs is allowed to conclude.
- **Efficiency must not silently become a gate.** A run that passes expensively still passes; the dimension is reporting, not a second pass/fail hiding behind one.
- The dimensions attach to the run model shipped as ENH-3397 — an attempt recorded against a named cell (task × repetition × subject) is the unit these measurements belong to.
- The precedent is a tournament fitness function that is deliberately multi-dimensional, with three of its four named criteria (resource efficiency, advancement speed, composition) existing to catch candidates that win wastefully — on the stated grounds that a wasteful winner is the wrong parent for the next generation. Naming the failure modes in advance is also what makes a post-mortem legible: the analyst matches observations against a known taxonomy rather than free-associating.

## Why it matters

The instrument that certifies runner correctness is today silent on cost. Downstream cost-trend analytics over `.ll/history.db` need exactly this per-run record as input; without it, a selection decision can carry forward a candidate that satisfies the criterion at multiples of the cost of its alternative.

## Program Design

### Types

- `HarnessEvent`: already tracks `duration_ms: int | None` (wall-clock, since ENH-2741); needs new `tokens: int | None`, `tool_calls: int | None` fields (`scripts/little_loops/history_reader/harness.py:53`)
- `RunnerResult.tool_trace: list[dict] | None` — ordered tool-call trace, currently trace-mode-only and not persisted to `harness_events` (`scripts/little_loops/runner_spec.py:100`)
- `HarnessEvalOutcome`: `passed: bool`, `verdict: str | None`, ... — where the new efficiency dimensions attach alongside the pass/fail/abstain outcome (`scripts/little_loops/cli/harness.py:863`)

### Signatures

- `authoritative_attempt(db_path, cell_key, repetition)` / `authoritative_attempts(db_path, cell_key)` (`scripts/little_loops/history_reader/harness.py:170`, `:198`) — the existing cell-keyed (task × repetition × subject) lookup the efficiency dimensions attach to
- `_grade(runner_label, result: RunnerResult, args, *, expected_grade=None, side_effects=None) -> tuple[int, HarnessEvalOutcome]` (`scripts/little_loops/cli/harness.py:1224`) — where tokens/tool-calls would be read off `result` and folded into the outcome

### Call Path

`_grade()` (`harness.py:1224`) reads `RunnerResult`/`tool_trace` -> populates new efficiency fields on `HarnessEvalOutcome` -> persisted onto `HarnessEvent` (`history_reader/harness.py:53`) -> read back via `authoritative_attempt()`/`authoritative_attempts()` for cross-run comparison.

## Impact

- **Priority**: P3 — the instrument that certifies runner correctness is currently silent on cost, and downstream cost-trend analytics over `.ll/history.db` need this per-run record as input, but no active selection decision is blocked on it yet.
- **Effort**: Small-Medium — most raw quantities (tokens, tool calls, wall-clock) are already logged per this issue's Design section; the work is surfacing them as named, stable verdict dimensions and defining what a cross-run comparison is allowed to conclude.
- **Risk**: Low — additive reporting; must not become a gate (see Design: "Efficiency must not silently become a gate").
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: naming and stabilizing tokens/tool-calls/wall-clock as verdict dimensions, attached to the ENH-3397 run model (attempt × task × repetition × subject).
- **Out of scope**: turning efficiency into a pass/fail gate — a run that passes expensively still passes; defining the downstream cost-trend analytics consumer over `.ll/history.db` (separate work).

## Status

**Open** | Created: 2026-09-13 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-09-14T20:15:11 - `94434fad-8258-433c-9701-ead707bb03a6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-13T21:28:47 - `23df08cc-836b-4f77-a1e2-bfb5aedb0f55.jsonl`
