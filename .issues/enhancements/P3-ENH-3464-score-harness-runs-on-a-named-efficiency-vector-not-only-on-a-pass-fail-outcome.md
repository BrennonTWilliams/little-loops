---
id: 3464
title: Score harness runs on a named efficiency vector, not only on a pass/fail outcome
type: ENH
priority: P3
status: open
discovered_date: '2026-09-13'
labels:
- evals
blocked_by:
- '3462'
parent: EPIC-3475
epic: EPIC-3475
---

## Summary

`ll-harness` reports one of pass, fail, or abstain. Two runners that both satisfy the same semantic criterion are therefore indistinguishable, even when one spent several times the tool calls, tokens, and wall-clock of the other. That is the wrong verdict shape for anything that feeds a selection decision: a wasteful winner reads identically to an efficient one, so promoting on the verdict alone will happily carry the expensive candidate forward.

Add a small, named set of efficiency dimensions to the verdict — tokens, tool calls, and wall-clock at minimum — reported alongside the outcome rather than folded into it. The dimensions must be named in advance and stable, so that a downstream post-mortem matches a run against a taxonomy instead of free-associating about why it was slow.

## Design

- Most of the raw quantities are already logged; the work is mostly surfacing them as dimensions of a specific run's verdict, and deciding what a comparison across two runs is allowed to conclude.
- **Efficiency must not silently become a gate.** A run that passes expensively still passes; the dimension is reporting, not a second pass/fail hiding behind one.
- The dimensions attach to the run model shipped as ENH-3397 — an attempt recorded against a named cell (task × repetition × subject) is the unit these measurements belong to.
- The precedent is a tournament fitness function that is deliberately multi-dimensional, with three of its four named criteria (resource efficiency, advancement speed, composition) existing to catch candidates that win wastefully — on the stated grounds that a wasteful winner is the wrong parent for the next generation. Naming the failure modes in advance is also what makes a post-mortem legible: the analyst matches observations against a known taxonomy rather than free-associating.

## Why it matters

The instrument that certifies runner correctness is today silent on cost. Downstream cost-trend analytics over `.ll/history.db` need exactly this per-run record as input; without it, a selection decision can carry forward a candidate that satisfies the criterion at multiples of the cost of its alternative.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-13T21:28:47 - `23df08cc-836b-4f77-a1e2-bfb5aedb0f55.jsonl`
