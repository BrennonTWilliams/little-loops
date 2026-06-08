---
id: FEAT-1994
title: "rn-build — Orchestration Decision Guide"
type: FEAT
priority: P3
status: open
parent: EPIC-1811
captured_at: '2026-06-06T00:00:00Z'
discovered_date: 2026-06-06
discovered_by: capture-issue
size: XSmall
blocked_by: [FEAT-1992]
relates_to:
- FEAT-1990
- FEAT-1992
labels:
- loops
- docs
- greenfield
---

# FEAT-1994: `rn-build` — Orchestration Decision Guide

## Summary

Document where `rn-build` fits in the orchestration loop family so users know
when to reach for it vs. `goal-cluster`, `loop-composer`, or `rn-implement`
directly. The create-loop wizard integration was descoped — wizard entries for
built-in loops that can't be meaningfully customized add discoverability noise
without value; `ll-loop list` already surfaces it.

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

## Status

- **State**: open
- **Created**: 2026-06-06
