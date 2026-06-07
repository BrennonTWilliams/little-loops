---
id: FEAT-1994
title: "rn-build — create-loop Wizard, Docs, and Guide"
type: FEAT
priority: P3
status: open
parent: FEAT-1990
captured_at: '2026-06-06T00:00:00Z'
discovered_date: 2026-06-06
discovered_by: capture-issue
size: Small
blocked_by: [FEAT-1992]
relates_to:
- FEAT-1990
- FEAT-1992
labels:
- loops
- docs
- create-loop
- greenfield
---

# FEAT-1994: `rn-build` — create-loop Wizard, Docs, and Guide

## Summary

Surface `rn-build` in the `skills/create-loop/` wizard as the recommended
spec-to-project builder, and document the cluster-vs-composer-vs-router-vs-builder
decision in the loops guide. Mirrors the goal-cluster wizard split (FEAT-1989).

## Parent Issue

Decomposed from FEAT-1990: `rn-build` — Recursive Spec-to-Project Builder.

## Prerequisites

FEAT-1992 (`rn-build.yaml`) merged so the wizard references a real loop.
Independently shippable in parallel with FEAT-1993.

## Proposed Solution

### 1. `skills/create-loop/SKILL.md`

Add an `Orch: Builder (spec → project)` wizard option and an `rn-build` type
mapping entry. The "Optimize a harness" / greenfield branch should now point to
`rn-build` rather than `greenfield-builder`.

### 2. `skills/create-loop/loop-types.md`

Add an `### Orch Builder` section under `## Orchestration Loops`:
- When to use: a single high-level project spec md, zero-to-working-project.
- Differentiator vs. `goal-cluster` (fan a *list* of goals) and `loop-composer`
  (decompose *one* goal): `rn-build` owns the full spec→design→decompose→
  implement→evaluate arc and composes both beneath it.
- Key phases: `scope_project`, `cluster_execute`, `eval_gate`.

### 3. `skills/create-loop/templates.md`

Add an `rn-build` shape/template stub showing the phase skeleton and
`${context.run_dir}/` artifact paths.

### 4. `docs/guides/LOOPS_GUIDE.md`

Add a "which orchestration loop?" decision table covering
router / composer / adaptive-composer / goal-cluster / rn-implement / rn-build,
keyed by input shape (1 goal / list of goals / issue IDs / project spec).

## Files to Modify

- `skills/create-loop/SKILL.md`
- `skills/create-loop/loop-types.md`
- `skills/create-loop/templates.md`
- `skills/create-loop/reference.md` (if config knobs need a row)
- `docs/guides/LOOPS_GUIDE.md`

## Acceptance Criteria

- `create-loop` wizard presents `Orch: Builder (spec → project)` and maps it to
  `rn-build`.
- `loop-types.md` has an `### Orch Builder` section with when-to-use guidance.
- `LOOPS_GUIDE.md` has a decision table distinguishing all orchestration loops by
  input shape.
- No broken references in updated skill/doc files (`ll-check-links`).

## Status

- **State**: open
- **Created**: 2026-06-06
