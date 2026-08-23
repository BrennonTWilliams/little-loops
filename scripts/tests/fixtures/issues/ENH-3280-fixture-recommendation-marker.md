---
id: ENH-9810
title: Fixture — Phase 7c recommendation-marker category
type: enhancement
status: open
priority: P3
decision_needed: false
---

# ENH-9810: Fixture — Phase 7c recommendation-marker category

## Summary

Golden fixture for `/ll:decide-issue` Phase 7c (ENH-3280) rewrite category 1 —
a recommendation marker naming the rejected option survives in `## Program Design`
after Option A was selected.

## Proposed Solution

**Option A**: Use `alpha_writer` for the write path.

**Option B**: Use `beta_writer` for the write path.

> **Selected:** Option A — simpler, reuses an existing helper.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-23.

**Selected**: Option A

**Reasoning**: `alpha_writer` reuses an existing helper; `beta_writer` would add a new one.

## Program Design

**Recommendation: Option B.** Wire the write path through `beta_writer`, since it
composes more cleanly with the batching layer.

## Status

**Open** | Created: 2026-08-23 | Priority: P3
