---
id: ENH-9812
title: Fixture — Phase 7c imperative-step category
type: enhancement
status: open
priority: P3
decision_needed: false
---

# ENH-9812: Fixture — Phase 7c imperative-step category

## Summary

Golden fixture for `/ll:decide-issue` Phase 7c (ENH-3280) rewrite category 3 —
an `## Implementation Steps` item instructs the rejected option's work directly
(no conditional wrapper) after Option A was selected.

## Proposed Solution

**Option A**: Use `alpha_writer` for the write path.

**Option B**: Use `beta_writer` for the write path.

> **Selected:** Option A — simpler, reuses an existing helper.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-23.

**Selected**: Option A

**Reasoning**: `alpha_writer` reuses an existing helper; `beta_writer` would add a new one.

## Implementation Steps

1. Implement `beta_writer` and wire it into the write path.
2. Update the tests to cover the write path.

## Status

**Open** | Created: 2026-08-23 | Priority: P3
