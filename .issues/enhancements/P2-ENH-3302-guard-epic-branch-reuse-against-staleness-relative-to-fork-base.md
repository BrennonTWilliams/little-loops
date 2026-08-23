---
id: ENH-3302
type: ENH
title: Guard epic branch reuse against staleness relative to fork base
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-23'
captured_at: '2026-08-23T19:19:05Z'
---

# ENH-3302: Guard epic branch reuse against staleness relative to fork base

## Summary

`_ensure_epic_branch` (`scripts/little_loops/parallel/worker_pool.py:1938`) is strictly create-if-missing: when `git rev-parse --verify <branch>` succeeds it reuses the existing `epic/*` integration branch as-is — no fast-forward, no merge of the fork base, not even a warning that the branch is behind. A branch held open by a failed merge becomes a frozen snapshot: every later run attaches sub-loop worktrees (`fsm/executor.py:961`, `checkout_existing=True`) to that stale tree.

Observed 2026-08-23: `epic/epic-3041-host-agnostic-advisor` was created 2026-08-08 off then-current main (`d93ce3e8f`) and held open when its merge verify failed. This morning's `sprint-refine-and-implement` run reused it ~448 commits behind main. The worktree's stale `.issues/` tree (predating main's issue re-anchoring, commit `731af505` era) caused 5 of 8 skips (`refine_failed` — "FEAT-3118 does not exist", "depends_on unknown issue FEAT-3120") and 11 false-negative verify failures (all pass on current main). Run: `.loops/runs/sprint-refine-and-implement-20260823T093038/`.

## Current Behavior

Docstring of the reuse path (`worker_pool.py:1939`):

```
Lazily create ``branch`` off ``base`` if it does not exist yet.
```

Steps: in-memory cache hit → local `rev-parse --verify` hit → remote `ls-remote` hit → else `git branch <branch> <base>`. All three "exists" paths return with zero staleness inspection.

## Expected Behavior

[What should happen instead]

## Motivation

Branch persistence across runs is by design (an epic integration branch accumulates children until the epic merges), but silent staleness turns a single held-open merge into a cascade: refine failures, bogus dependency-graph errors, verify false negatives, and (see the companion BUG) issue-ID collisions. The failure is invisible until a human diffs the branch point.

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

1. Add staleness measurement in `_ensure_epic_branch` after the local and remote hit paths (worker_pool.py:1953-1970).
2. Thread the resolved base into the check (already available at call sites via `resolve_epic_base`).
3. Add `refresh_on_reuse` to `EpicBranchesConfig` (`scripts/little_loops/parallel/types.py`) + `config-schema.json` + schema-parity defaults.
4. On `merge` mode: `git merge --no-edit <base>` inside a scratch worktree or via the git lock on the branch; conflict → emit event + warn, do not abort the run.
5. Emit a structured event (e.g. `epic_branch_stale`) so run summaries and `ll-loop` audit tooling can surface it.
6. Tests: stale-branch fixture repo — reuse path warns; merge mode fast-forwards; conflict falls back to warn.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Desired Behavior

On the local/remote "exists" paths, measure staleness against the resolved fork base (`worktree_utils.resolve_epic_base`, ENH-2656): `git rev-list --count <branch>..<base>`. Then either:

- **Warn** (minimum): log/emit `epic branch <branch> is N commits behind <base>` above a threshold, and

- **Optionally reconcile** (config-gated, e.g. `parallel.epic_branches.refresh_on_reuse: warn|merge|off`, default `warn`): merge the base into the branch before dispatching workers; on merge conflict, fall back to warn + surface in the run summary rather than proceeding silently.

## Affected Files

- `scripts/little_loops/parallel/worker_pool.py` (`_ensure_epic_branch`)
- `scripts/little_loops/parallel/types.py` (`EpicBranchesConfig`)
- `scripts/little_loops/config-schema.json`
- `scripts/tests/test_worker_pool.py` (or wherever `_ensure_epic_branch` is covered)

## Acceptance Criteria

- [ ] Reusing an epic branch N>threshold commits behind its fork base emits a visible warning including N and the base ref
- [ ] `refresh_on_reuse: merge` merges the base into the branch before worker dispatch; clean merge proceeds, conflict degrades to warn without aborting
- [ ] Default behavior (`warn`) changes no git state
- [ ] `python -m pytest scripts/tests/` passes

## Related Key Documentation

| Document | Category | Relevance |
|----------|----------|-----------|
| docs/ARCHITECTURE.md | architecture | Parallel orchestration / epic-branch lifecycle design |
| docs/reference/API.md | architecture | `worktree_utils` (`resolve_epic_base`, `setup_worktree`) and worker-pool surfaces |

## Status

**Open** | Created: 2026-08-23 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-08-23T19:19:40 - `0e2d1ba2-9c47-49de-b246-1efb9ad7b60c.jsonl`
