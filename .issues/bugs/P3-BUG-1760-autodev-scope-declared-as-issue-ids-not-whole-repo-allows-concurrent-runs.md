---
id: BUG-1760
title: autodev scope declared as issue IDs not whole repo, allows concurrent conflicting runs
type: BUG
status: open
priority: P3
captured_at: '2026-05-28T00:42:55Z'
discovered_date: '2026-05-28'
discovered_by: capture-issue
labels:
- bug
- autodev
- ll-loop
- concurrency
---

# BUG-1760: autodev scope declared as issue IDs not whole repo, allows concurrent conflicting runs

## Summary

`LockManager._scopes_overlap()` compares scope paths as strings. If two `ll-loop run autodev` invocations use different issue ID sets (e.g. `ENH-1699,ENH-1700` vs `BUG-031`), the path-based overlap check finds no conflict and both acquire locks. Both autodev instances then operate concurrently on the same git repo, racing on git operations, issue status writes, and `.loops/.running/` state files.

## Root Cause

- **File**: `scripts/little_loops/fsm/concurrency.py`
- **Function**: `LockManager._scopes_overlap()`
- **Explanation**: Scope is intended to represent "what filesystem paths does this loop touch." If the autodev loop definition declares `scope: [<issue-ids>]` (treating issue IDs as path tokens) rather than `scope: ["."]`, two autodev runs with disjoint issue sets will have non-overlapping scopes and bypass the conflict guard. All autodev runs operate on the same repo root regardless of which issues they process.

## Observed Behavior

During the 2026-05-27 incident: a second `ll-loop run autodev BUG-031` was started at 7:14 PM while `ll-loop run autodev ENH-1699,ENH-1700,ENH-1701,ENH-1702` was still running (since 3:42 PM). Both acquired `.lock` files in `.loops/.running/` without conflict. Both had active lock files simultaneously.

## Expected Behavior

Only one autodev instance should run at a time because all autodev runs share the git working tree. A second `ll-loop run autodev` should either block (if `--queue`) or exit with a clear conflict message.

## Implementation Steps

1. Find the autodev loop YAML definition (likely in `.loops/autodev.yaml` or similar)
2. Verify whether `scope:` is set to issue IDs or `["."]`
3. If set to issue IDs: change to `scope: ["."]` so any two autodev runs conflict
4. Alternatively: update `LockManager` to also conflict on matching loop name regardless of scope (name-based lock as an additional guard)
5. Add test: two `LockManager.acquire()` calls for the same loop name with different non-overlapping scopes — should they conflict? Document the intended semantics.

## API/Interface

The autodev loop YAML `scope:` field should be:
```yaml
scope:
  - "."
```
Not:
```yaml
scope:
  - "ENH-1699"
  - "ENH-1700"
```

## Related Issues

- BUG-232: TOCTOU race in scope-lock acquisition — different (race during acquire, not scope definition)
- BUG-525: TOCTOU race condition lock acquire — same
- BUG-1359 (done): outer-loop-eval scope conflict with sub-loop — different direction (sub-loop blocked by parent, not two peers)

## Session Log
- `/ll:capture-issue` - 2026-05-28T00:42:55Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
