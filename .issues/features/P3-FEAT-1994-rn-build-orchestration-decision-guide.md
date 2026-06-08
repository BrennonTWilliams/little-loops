---
id: FEAT-1994
title: "rn-build \u2014 Orchestration Decision Guide"
type: FEAT
priority: P3
status: done
parent: EPIC-1811
captured_at: '2026-06-06T00:00:00Z'
completed_at: '2026-06-08T02:35:05Z'
discovered_date: 2026-06-06
discovered_by: capture-issue
size: XSmall
testable: false
blocked_by:
- FEAT-1992
relates_to:
- FEAT-1990
- FEAT-1992
labels:
- loops
- docs
- greenfield
confidence_score: 90
outcome_confidence: 83
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 23
score_change_surface: 20
---

# FEAT-1994: `rn-build` — Orchestration Decision Guide

## Summary

Document where `rn-build` fits in the orchestration loop family so users know
when to reach for it vs. `goal-cluster`, `loop-composer`, or `rn-implement`
directly. The create-loop wizard integration was descoped — wizard entries for
built-in loops that can't be meaningfully customized add discoverability noise
without value; `ll-loop list` already surfaces it.

## Use Case

A developer has a React Native spec file and wants to build a project from scratch. They are unsure whether to use `rn-build`, `rn-implement`, `goal-cluster`, or `loop-composer`. They open `docs/guides/LOOPS_GUIDE.md`, find the decision table keyed by input shape, and immediately identify "spec file, zero-to-project → `rn-build`." They also check `docs/reference/API.md` to understand the key context knobs before running the loop.

## Current Behavior

No orchestration decision guide exists. Users must read individual loop YAML files or rely on trial-and-error to determine which loop fits their input shape (`goal-cluster`, `rn-implement`, `loop-composer`, `rn-build`, etc.). `LOOPS_GUIDE.md` and `API.md` have no entry for `rn-build`.

## Expected Behavior

`docs/guides/LOOPS_GUIDE.md` contains a decision table covering all orchestration loops keyed by input shape, with `rn-build` as the spec-file entry. `docs/reference/API.md` has an `rn-build` reference entry documenting CLI invocation, key phases, and context knobs. `ll-check-links` passes with no broken references.

## Parent Issue

Decomposed from FEAT-1990: `rn-build` — Recursive Spec-to-Project Builder.

## Prerequisites

FEAT-1992 (`rn-build.yaml`) merged.

## Proposed Solution

### 1. `docs/guides/LOOPS_GUIDE.md`

Add a "Which orchestration loop?" decision table covering
router / composer / adaptive-composer / goal-cluster / rn-implement / rn-build,
keyed by input shape:

| You have… | Use |
|-----------|-----|
| A natural-language goal | `loop-router` (classifies + dispatches) |
| One decomposable goal | `loop-composer` / `loop-composer-adaptive` |
| A list of goals / EPIC / sprint | `goal-cluster` |
| A single issue to implement | `rn-implement` |
| A spec file, zero-to-project | `rn-build` |

### 2. `docs/reference/API.md`

Add an `rn-build` loop reference entry: CLI invocation, key phases, context
knobs (`spec`, `max_issues`, `max_eval_retries`), `schedule_mode`, and
`propagate_context` flag.

## Files to Modify

- `docs/guides/LOOPS_GUIDE.md`
- `docs/reference/API.md`

## Acceptance Criteria

- `LOOPS_GUIDE.md` has a decision table distinguishing all orchestration loops
  by input shape, with `rn-build` as the spec-file entry.
- `docs/reference/API.md` has an `rn-build` entry covering CLI invocation, key
  phases, and context knobs.
- No broken references (`ll-check-links`).

## Impact

- **Priority**: P3 — Documentation only; does not block feature delivery but improves discoverability of `rn-build` for new users
- **Effort**: XSmall — Two targeted doc edits, no code changes
- **Risk**: Low — Documentation-only; no runtime impact, no breaking changes
- **Breaking Change**: No

## Session Log
- `/ll:ready-issue` - 2026-06-08T02:27:44 - `f78b9e74-067f-4988-ae03-4cff78299674.jsonl`
- `/ll:confidence-check` - 2026-06-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f945aa86-605c-4cbf-bb67-7303f3eadbea.jsonl`

## Status

- **State**: open
- **Created**: 2026-06-06
