---
id: ENH-2218
title: ll-ctx-stats learning test coverage dashboard section
type: enhancement
priority: P4
status: open
parent: EPIC-2207
captured_at: '2026-06-18T15:38:06Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
---

# ENH-2218: ll-ctx-stats learning test coverage dashboard section

## Summary

`ll-ctx-stats` shows context-window analytics and cache hit rates but nothing about learning test health. Add a `## Learning Tests` section to its output that summarizes registry coverage: total records, proven/stale/refuted breakdown, packages imported in `scripts/` with no record (gap list), and the last audit date.

## Current Behavior

`ll-ctx-stats` provides context-window analytics (per-tool bytes, cache hit rates) and skill-health signals but does not surface any learning test registry information. Users must run the full audit loop (`ll-loop run`) or query the registry CLI (`ll-learning-tests list`) manually to check registry coverage, stale records, or gaps.

## Expected Behavior

`ll-ctx-stats` output should include a `## Learning Tests` section that summarizes registry coverage (total records, proven/stale/refuted counts, gap list, last audit date) whenever `learning_tests.enabled: true`. The section should be omitted entirely when `learning_tests.enabled: false`.

## Motivation

There's currently no at-a-glance view of registry health without running the full audit loop or querying the CLI manually. `ll-ctx-stats` is already the health dashboard for the session; learning test coverage belongs there.

## Implementation Steps

1. In `ll-ctx-stats` CLI handler, add a `learning_tests_stats()` function:
   - Call `list_records()` → compute proven/stale/refuted counts and last record date
   - Grep `scripts/` for all imported packages → cross-reference against registry slugs
   - Compute gap list: packages imported but not in registry
2. Render as a `## Learning Tests` section in the stats output:
   ```
   ## Learning Tests
   Records: 12 total (9 proven, 2 stale, 1 refuted)
   Last record: 2026-06-10
   Coverage gaps (imported, no record): boto3, stripe
   ```
3. Gate behind `learning_tests.enabled`.

## Success Metrics

- `ll-ctx-stats` output includes the learning tests section when `learning_tests.enabled: true`
- The gap list matches packages found in imports but absent from the registry
- Stale records are counted separately from refuted
- Section is omitted (not an empty block) when `learning_tests.enabled: false`

## Scope Boundaries

- **In scope**: Adding a `## Learning Tests` section to `ll-ctx-stats` output; computing proven/stale/refuted counts from the registry; detecting coverage gaps via import scan of `scripts/`; gating behind `learning_tests.enabled`
- **Out of scope**: Automated remediation of stale or refuted records; deep audit of individual learning tests; modifying the `ll-learning-tests` CLI itself

## Impact

- **Priority**: P4 - Dashboard improvement, not blocking any current workflow, tracked under EPIC-2207
- **Effort**: Small - Adds one function call and a render section to existing `ll-ctx-stats` output
- **Risk**: Low - Gated behind `learning_tests.enabled` config flag; no risk to existing stats output
- **Breaking Change**: No - New optional section, gated by config

## Labels

`enhancement`, `captured`, `learning-tests`, `dashboard`

## Session Log
- `/ll:format-issue` - 2026-06-18T19:33:27 - `0f6c8504-40cd-42d9-863b-234192efbe8e.jsonl`

- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`

**Open** | Created: 2026-06-18 | Priority: P4
