---
id: FEAT-2261
title: omp hook adapter — hooks/adapters/omp/
type: feature
status: open
priority: P4
discovered_date: 2026-06-24
discovered_by: planning-assessment
parent: EPIC-2258
depends_on: [FEAT-1850]
labels: [host-compat, omp, hooks]
---

# FEAT-2261: omp hook adapter — hooks/adapters/omp/

## Summary

Create `hooks/adapters/omp/` translating oh-my-pi (`omp`) lifecycle events into
`LLHookEvent` and invoking the host-agnostic ll hook handler. Analogous to
`hooks/adapters/codex/`.

## Motivation

oh-my-pi exposes richer hook events than vanilla pi-mono, so the parity gap
that plagued the cancelled Pi adapter (FEAT-1715) is expected to be narrower.
The exact event set is established by FEAT-2263 (hook-event parity audit).

## Acceptance Criteria

- `hooks/adapters/omp/` exists with an event→handler mapping.
- A `session_start`-equivalent omp event triggers the `session_start` ll intent.
- At least one tool-lifecycle omp event triggers `pre_tool_use`/`post_tool_use`.
- `hooks/adapters/omp/README.md` documents activation + the event mapping table.
- Tests in `scripts/tests/test_omp_adapter.py` pass.

## Reference

- `hooks/adapters/codex/` — pattern to follow.
- FEAT-2263 — supplies the omp→ll event mapping.

## Impact

- **Effort**: S–M.
- **Risk**: Low — additive.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-24 | Priority: P4
