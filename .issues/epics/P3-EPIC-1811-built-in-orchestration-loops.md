---
id: EPIC-1811
title: Built-in Orchestration Loops
type: EPIC
priority: P3
status: open
discovered_date: 2026-05-30
discovered_by: link-epics
labels:
- epic
- loops
- orchestration
- built-in
relates_to:
- FEAT-1808
- FEAT-1806
- FEAT-1807
- ENH-1912
- EPIC-1694
- FEAT-1983
- FEAT-1984
- FEAT-1987
- FEAT-1988
- FEAT-1989
- FEAT-1990
- FEAT-1991
- FEAT-1992
- FEAT-1993
- FEAT-1994
- ENH-2012
- BUG-2013
- ENH-2014
- ENH-2015
- ENH-2016
- ENH-2023
---

# EPIC-1811: Built-in Orchestration Loops

## Summary

Ship five new built-in FSM loops that operate above the single-loop level: a goal decomposer
that breaks complex objectives into sub-loops, an adaptive variant that re-plans on failure,
a multi-goal orchestrator for sprint/EPIC-shaped input, and two domain-specific loops
(market strategy optimization, adversarial figure redesign).

These loops extend the built-in loop catalog beyond the four EPIC-1694 loops
(which are proof/gate-focused) into higher-level orchestration and domain-specific
automation.

## Motivation

The loop catalog has grown to 57 loops, but all operate at the single-task level.
There's no built-in way to decompose a complex goal into sub-loops, orchestrate
multiple goals, or adapt when sub-goals fail. These five loops fill that gap:
three orchestration primitives (composer, adaptive composer, goal-cluster) and
two domain-specific exemplars that exercise the orchestration layer.

## Goal

When this epic is done, users can:
- Decompose a complex goal into sub-loops via `loop-composer`
- Re-plan automatically when a sub-goal fails via adaptive `loop-composer`
- Orchestrate sprint/EPIC-shaped input across multiple goals via `goal-cluster`
- Run opponent-aware market strategy optimization as a built-in loop
- Run adversarial figure redesign with AutoFigure as a built-in loop

## Scope

### In scope

- FEAT-1808: `loop-composer` — Goal Decomposer Built-in FSM Loop
- FEAT-1809: Adaptive `loop-composer` — Re-plan-on-Failure Variant
- FEAT-1810: `goal-cluster` — Multi-Goal Orchestrator for Sprint- or EPIC-Shaped Input
- FEAT-1806: Opponent-Aware Market Strategy Optimization Loop
- FEAT-1807: Adversarial-Redesign Figure Loop with AutoFigure

### Out of scope

- Modifications to the FSM executor/runtime itself
- Changes to existing loops
- General-purpose workflow engine (these are specific loop implementations)

## Children

- **FEAT-1808** — `loop-composer` — Goal Decomposer Built-in FSM Loop (One Level Above `loop-router`)
- **FEAT-1809** — Adaptive `loop-composer` — Re-plan-on-Failure Variant
- **FEAT-1810** — `goal-cluster` — Multi-Goal Orchestrator for Sprint- or EPIC-Shaped Input
- **FEAT-1806** — Opponent-Aware Market Strategy Optimization Loop
- ✅ **FEAT-1807** — Adversarial-Redesign Figure Loop with AutoFigure
- **FEAT-1990** — `rn-build` — Recursive Spec-to-Project Builder (integration capstone; greenfield-builder successor)
  - **FEAT-1991** — rn-implement — Value-Ranked Dequeue (`select_next` scheduler)
  - **FEAT-1992** — rn-build — Core Loop YAML, Loaders, and Integration
  - **FEAT-1993** — Deprecate `greenfield-builder` in favor of `rn-build`
  - **FEAT-1994** — rn-build — `create-loop` Wizard, Docs, and Guide
- **ENH-2012** — rn-build — Spec file format guide and sample spec
- **BUG-2013** — rn-build — `eval_gate` crashes with empty harness name when `eval_harness` errors
- **ENH-2014** — rn-build — E2E smoke test and sample spec for integration validation
- **ENH-2015** — rn-build — Add to "Cluster vs. Composer vs. Router" decision table
- **ENH-2016** — rn-build — Resume-from-epic path for continuing a partial build
- **ENH-2023** — Extract loop-authoring standards into docs/guides/LOOPS-GUIDELINES.md

## Verification Notes

_Added by `/ll:verify-issues` on 2026-05-31_

**Verdict: NEEDS_UPDATE** — adversarial-redesign.yaml now exists and FEAT-1807 is done. Still open: FEAT-1806 (market-strategy), FEAT-1808 (loop-composer), FEAT-1809 (adaptive loop-composer), FEAT-1810 (goal-cluster).

- `/ll:verify-issues` - 2026-06-05 - Epic is 20% complete (1/5 children done: FEAT-1807 `adversarial-redesign.yaml` confirmed at `scripts/little_loops/loops/`). Summary should acknowledge FEAT-1807 completion. Body references `loops/` at project root — actual loops directory is `scripts/little_loops/loops/`. Correct path references and update Summary to reflect that 1 of 5 loops is shipped.

## Session Log
- `/ll:verify-issues` - 2026-06-09T09:21:00 - `e40557ae-4da3-4ea7-b023-bf5e57e8b61a.jsonl`
- `/ll:verify-issues` - 2026-06-05T22:34:33 - `1a4d9590-60c8-47b0-9997-b0f543664183.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:verify-issues` - 2026-06-04T04:22:07 - `94e89e68-ddb3-448e-a123-eae4ee9ba582.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:49:02 - `21850d04-bdf9-4e28-bf74-f68eaaaed883.jsonl`
- `/ll:verify-issues` - 2026-05-31T00:00:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:19 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
