---
id: BUG-3303
type: BUG
title: Issue ID allocation inside worktrees collides with main tree IDs
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-23'
captured_at: '2026-08-23T19:19:29Z'
---

# BUG-3303: Issue ID allocation inside worktrees collides with main tree IDs

## Summary

Issue ID allocation (the next-ID scan behind `ll-issues create` / decomposition flows) reads only the `.issues/` tree visible from the current working directory. When automation runs inside a git worktree attached to a stale branch, the worktree's `.issues/` is missing issues that exist on main, so newly created issues are assigned IDs that already belong to different issues on main.

Observed 2026-08-23 in the `sprint-refine-and-implement` run on EPIC-3041: FEAT-3040's decomposition ran in a worktree on `epic/epic-3041-host-agnostic-advisor` (branched 2026-08-08, ~448 commits behind main). The worktree's `.issues/` predated main's re-anchoring, so the two telemetry children were allocated **FEAT-3117** and **FEAT-3118** — IDs already used on main by the wire-trigger issues (`P3-FEAT-3117-wire-confidence-gate-consult-trigger.md`, `P3-FEAT-3118-wire-pre-done-consult-trigger.md`). The children never landed (abandoned ref `b972a9c7c`) and were manually recovered as FEAT-3300/FEAT-3301 (commit `3e492b26a`). Had the branch merged cleanly, main would have received two colliding ID pairs, corrupting `depends_on`/`parent` resolution for the whole advisor cluster.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. Locate the next-ID scan (`scripts/little_loops/cli/issues/create.py` / `issue_parser.py` next-id helper).
2. Add a canonical-namespace resolver: detect linked-worktree context, resolve the main checkout path from `git-common-dir`, union both `.issues/` scans.
3. Cover decomposition paths that allocate IDs (recursive decompose flows) via the same helper.
4. Tests: fixture repo + linked worktree on a stale branch; assert allocated ID exceeds main's max.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Root Cause

ID allocation is scoped to the working directory's checkout instead of the canonical issue namespace. Per `feedback_bare_numeric_frontmatter_id_supported` conventions, the numeric ID is the unique key across the whole repo history; a stale worktree checkout is not an authoritative view of allocated IDs.

## Steps to Reproduce

1. Create a branch, then add new issues on main so main's max ID advances.
2. In a worktree attached to the stale branch, run `ll-issues create ...` (or any decomposition flow that allocates IDs).
3. The new issue receives an ID equal to one already allocated on main.

## Desired Behavior

ID allocation consults the canonical namespace even from a worktree — candidates:

- Resolve the primary repo root (a worktree's `.git` file points at the main checkout's `gitdir`) and scan that `.issues/` tree in addition to the local one, taking the max.
- And/or scan git refs (`git ls-tree <default-branch> -- .issues` via the common git dir) so IDs allocated on main are visible regardless of checkout state.
- Minimum viable guard: when running inside a linked worktree (`git rev-parse --git-common-dir` differs from `--git-dir`), also read the main working tree's `.issues/` max ID.

## Acceptance Criteria

- [ ] `ll-issues create` inside a linked worktree on a stale branch never allocates an ID <= the main tree's max allocated ID
- [ ] Decomposition flows allocate through the same guarded path
- [ ] Behavior unchanged when running in the primary checkout
- [ ] `python -m pytest scripts/tests/` passes

## Related Key Documentation

| Document | Category | Relevance |
|----------|----------|-----------|
| docs/reference/API.md | architecture | `issue_parser` / `ll-issues create` ID-allocation surfaces |
| .claude/CLAUDE.md | guidelines | Issue File Format — numeric ID is the canonical unique identifier |

## Status

**Open** | Created: 2026-08-23 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-08-23T19:19:40 - `0e2d1ba2-9c47-49de-b246-1efb9ad7b60c.jsonl`
