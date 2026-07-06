---
id: ENH-2473
title: Performance benchmarks for large repositories
type: ENH
priority: P4
status: deferred
captured_at: '2026-07-03T00:00:00Z'
discovered_date: 2026-07-03
discovered_by: capture-issue
parent: EPIC-1812
relates_to: []
labels:
- performance
- benchmarks
- captured
---

# ENH-2473: Performance benchmarks for large repositories

## Summary

CHANGELOG's Planned section has carried "Performance benchmarks for large
repositories" with no backlog issue behind it. This is that issue. Define and
automate a benchmark suite that measures little-loops' hot paths against a
large synthetic repo (thousands of issues in `.issues/`, large `.ll/history.db`,
deep loop-run history in `.loops/runs/`).

## Scope

- Synthetic fixture generator: N issues / M sessions / K loop runs, parameterized.
- Benchmarks (timed, asserted against generous ceilings so they run as ordinary pytest tests per the Testing & CI Policy): `ll-issues list`/`sequence`, `ll-deps` graph build, `ll-session search --fts`, `ll-history-context` render, `ll-loop validate` over the built-in loop set, hook dispatch overhead.
- Record baseline numbers in `docs/development/TROUBLESHOOTING.md` or a dedicated benchmarks doc.

## Current Behavior

No benchmarks exist for large-repo behavior; hot-path performance at scale (thousands of issues, large history.db) is unmeasured, and the item existed only as an untracked CHANGELOG Planned line.

## Expected Behavior

A parameterized synthetic fixture plus timed pytest benchmarks with generous ceilings, and documented baseline numbers for at least one large configuration.

## Acceptance Criteria

- Benchmark module under `scripts/tests/` (skippable via marker for slow runs) with ceilings that fail on order-of-magnitude regressions.
- Baseline numbers documented for at least one large-fixture configuration.
- CHANGELOG Planned line points at this issue.

## Scope Boundaries

- **In**: synthetic fixture generator, timed benchmarks with generous ceilings as pytest tests, documented baselines.
- **Out**: hosted CI or perf dashboards; micro-optimizations discovered by the benchmarks (file separately).

## Impact

- **Priority**: P4 — proactive; no current perf complaint
- **Effort**: Medium — fixture generator + benchmark module + baselines
- **Risk**: Low — test-only surface
- **Breaking Change**: No

## Status

**Open** | Created: 2026-07-03 | Priority: P4

## Session Log

- backlog-grooming - 2026-07-03T00:00:00Z - Filed from CHANGELOG § Planned (previously untracked line).
