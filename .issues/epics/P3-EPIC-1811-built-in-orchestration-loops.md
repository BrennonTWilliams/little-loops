---
id: EPIC-1811
title: Built-in Orchestration Loops
type: EPIC
priority: P3
status: open
discovered_date: 2026-05-30
discovered_by: link-epics
relates_to: [FEAT-1808, FEAT-1809, FEAT-1810, FEAT-1806, FEAT-1807]
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
- **FEAT-1807** — Adversarial-Redesign Figure Loop with AutoFigure

## Verification Notes

_Added by `/ll:verify-issues` on 2026-05-31_

**Verdict: VALID** — All 5 children still open; no loop files created yet:
- `loops/loop-composer.yaml`, `loops/goal-cluster.yaml`, `loops/market-strategy-optimize.yaml`, `loops/adversarial-redesign.yaml` do not yet exist ✓
- All child FEATs (1806, 1807, 1808, 1809, 1810) are open ✓

## Session Log
- `/ll:verify-issues` - 2026-05-31T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
