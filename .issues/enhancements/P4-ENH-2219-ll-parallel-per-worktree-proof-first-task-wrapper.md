---
id: ENH-2219
title: ll-parallel per-worktree proof-first-task wrapper for issues with learning_tests_required
type: enhancement
priority: P4
status: open
parent: EPIC-2207
captured_at: '2026-06-18T15:38:06Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
---

# ENH-2219: ll-parallel per-worktree proof-first-task wrapper for issues with learning_tests_required

## Summary

`ll-parallel` dispatches issues to isolated git worktrees for concurrent implementation but doesn't wrap those invocations with `proof-first-task`. For issues that declare `learning_tests_required`, inject a `proof-first-task` loop call as the first step in the worktree's claude invocation, so assumption-firewall runs per-worktree before implementation begins.

## Current Behavior

`ll-parallel` dispatches issues to isolated git worktrees for concurrent implementation but does not wrap those invocations with `proof-first-task`. For issues that declare `learning_tests_required`, the per-worktree gating is bypassed — assumption-firewall never runs in the worktree before implementation begins. This means a worktree can start implementing against an API or library that has untested assumptions.

ENH-2210 gates the sprint-level pre-flight for `ll-sprint`, but `ll-parallel` is a separate code path that currently bypasses learning test gating entirely.

## Expected Behavior

When `ll-parallel` builds a claude invocation for a worktree, it should check if the issue's frontmatter contains `learning_tests_required`. If it does and `learning_tests.enabled: true`, the command sequence should be prepended with a `proof-first-task` invocation:

```
ll-loop run proof-first-task --context issue_file=<path>
```

If `proof-first-task` returns `blocked` (exit 1), the worktree should skip the main implementation invocation and log the skip. If it returns `done` (exit 0), implementation proceeds normally. Each worktree's gate must be independent — parallel execution across worktrees is unaffected.

## Motivation

ENH-2210 gates the sprint-level pre-flight for `ll-sprint`. `ll-parallel` is a separate path that also bypasses learning test gating. The per-worktree wrapper is the right granularity: it's more precise than a batch pre-flight because it only invokes assumption-firewall for the specific issue being worked on in that worktree.

## Implementation Steps

1. In `ll-parallel` (or the `ParallelRunner`), when building the claude invocation for a worktree, check if the issue's frontmatter contains `learning_tests_required`.
2. If yes and `learning_tests.enabled: true`, prepend the command sequence with a `proof-first-task` invocation: `ll-loop run proof-first-task --context issue_file=<path>`.
3. If the proof-first-task loop returns `blocked` (exit 1), skip the main implementation invocation for that worktree and log the skip.
4. If `proof-first-task` returns `done` (exit 0), proceed with the normal implementation.
5. Add `--skip-learning-gate` flag to `ll-parallel` to bypass this behavior for emergency runs.

## Acceptance Signals

- A worktree for an issue with `learning_tests_required: [httpx]` runs assumption-firewall before the implementation prompt
- If assumption-firewall blocks, the worktree exits cleanly without starting the implementation
- Parallel execution of multiple worktrees is unaffected: each worktree's gate is independent
- `--skip-learning-gate` bypasses all per-worktree gating

## Scope Boundaries

- **In scope**: Modifying `ll-parallel` (or `ParallelRunner`) to detect `learning_tests_required` in frontmatter and prepend `proof-first-task` invocation; adding `--skip-learning-gate` flag; logging for blocked/skipped worktrees
- **Out of scope**: Changes to the `proof-first-task` loop itself; batch pre-flight for learning tests in `ll-sprint` (covered by ENH-2210); other types of per-worktree gating beyond learning tests

## API/Interface

`ll-parallel` CLI:

```
ll-parallel [--skip-learning-gate]
```

- `--skip-learning-gate` — Bypass per-worktree learning test gating for emergency runs

## Consolidation Note

**Note** (added by EPIC-2207 scoping review): Per-worktree gating shares code with ENH-2210's sprint-level pre-flight. Both must call a shared utility at `scripts/little_loops/learning_tests/gate.py` rather than implementing independent gating logic. See ENH-2210 for the shared API design.

When implementing this issue:
1. The shared utility (`gate.py`) must be built first (owned by ENH-2210).
2. This issue then calls the utility per-worktree rather than reimplementing the gate check.
3. The `--skip-learning-gate` flag at the `ll-parallel` CLI level bypasses the per-worktree call.

### Files to Modify
- `scripts/little_loops/cli/parallel.py` — `ParallelRunner` worktree invocation builder
- `scripts/little_loops/cli/parallel.md` — CLI documentation update

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/parallel.py` — direct callers of worktree construction

### Similar Patterns
- ENH-2210 sprint-level pre-flight for `ll-sprint` — similar learning test gating pattern

### Tests
- `scripts/tests/test_parallel.py` — existing parallel runner tests
- New tests for `--skip-learning-gate` flag

### Documentation
- `docs/reference/API.md` — `ll-parallel` CLI reference
- `scripts/little_loops/cli/parallel.md` — inline docs

### Configuration
- N/A — behavior is driven by issue frontmatter fields

## Impact

- **Priority**: P4 — Low priority; enhancement to existing parallel execution, not a correctness fix
- **Effort**: Medium — touches `ParallelRunner` worktree invocation builder, adds conditional logic and a new CLI flag
- **Risk**: Low — wraps existing behavior conditionally; `--skip-learning-gate` provides emergency bypass
- **Breaking Change**: No — new optional behavior behind `learning_tests_required` frontmatter check

## Success Metrics

- Issues with `learning_tests_required` in frontmatter get assumption-firewall before per-worktree implementation
- Worktrees blocked by `proof-first-task` exit cleanly without starting implementation
- `--skip-learning-gate` flag correctly bypasses all per-worktree gating
- Parallel execution throughput is unaffected when no issues have `learning_tests_required`

## Labels

`enhancement`, `learning-tests`, `ll-parallel`, `captured`

## Session Log
- `/ll:format-issue` - 2026-06-18T19:33:16 - `4072b9ee-5401-460f-9774-32c1e434c36f.jsonl`
- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`

## Status

**Open** | Created: 2026-06-18 | Priority: P4
