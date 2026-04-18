---
discovered_date: "2026-04-18"
discovered_by: capture-issue
depends_on: [FEAT-1074, FEAT-1075, FEAT-1076, ENH-1073]
---

# ENH-1167: ENH-1073 `collect_children` State Logic Underspecified for Parallel Worktree Mode

## Summary

ENH-1073's `collect_children` state is described only as "diff issue IDs pre/post, gather children from all workers." In parallel worktree mode each worker runs in an isolated git branch — child issue files written by workers are in per-worker branches that have not yet merged to main. The logic for discovering and deduplicating child IDs from N parallel worktrees has no clear implementation path.

## Current Behavior

ENH-1073 proposes this state:

```yaml
collect_children:
  # shell: diff issue IDs pre/post, gather children from all workers
  # exit 0 if next generation exists, 1 if done
  on_yes: fan_out    # next generation
  on_no: done
```

This description works for sequential mode where the main branch always reflects completed work. In parallel worktree mode with `isolation: worktree`, each worker's issue files are written to a worker-specific git branch. After `fan_out` completes (all workers done), those branches have been merged back to main (by `ParallelRunner`'s merge-back step). The `collect_children` state executes after merge-back — so in theory, child issue files from all workers should be on main.

**Unresolved questions:**
1. Does `ParallelRunner` merge ALL worker branches back before returning? If merge fails for some workers (conflict, error), are their children still discoverable?
2. How does `collect_children` distinguish "children written in this generation" from "pre-existing issues on main"? The "diff issue IDs pre/post" approach requires snapshotting issue IDs before `fan_out` — but `ParallelStateConfig` has no mechanism to capture a pre-execution snapshot.
3. In `fail_mode: collect` mode, failed workers' branches may or may not have been merged. Which children are included in the next generation?

## Expected Behavior

ENH-1073 should specify:
1. How the "pre-fan-out" issue ID snapshot is captured and stored in context (so `collect_children` can compute the diff)
2. Whether `ParallelRunner` guarantees all successful worker branches are merged before returning (answer: yes, per FEAT-1075 design)
3. How failed worker children are handled (excluded from next generation, or included if partial merge succeeded)
4. What `collect_children`'s actual shell command looks like

## Motivation

`recursive-refine` is the most important loop targeted by ENH-1073 (it discovers child decomposition issues). Without a clear `collect_children` implementation, ENH-1073 cannot be implemented correctly — parallel `recursive-refine` may silently drop children from failed workers, breaking the decomposition tree guarantee stated in ENH-1073's success metrics: "No regressions in child issue discovery."

## Proposed Solution

**Refine ENH-1073 to specify `collect_children` concretely.** The most likely correct approach:

1. **Pre-snapshot**: Add a `snapshot_ids` state before `fan_out` that captures current issue IDs to a context variable:
   ```yaml
   snapshot_ids:
     action: shell
     shell: "ll-issues list --ids-only > /tmp/pre_gen_ids.txt && echo done"
     on_yes: fan_out
   ```

2. **Post-merge diff**: After `fan_out` (all merges complete), `collect_children` diffs the snapshot against current state:
   ```yaml
   collect_children:
     action: shell
     shell: |
       NEW_IDS=$(comm -13 <(sort /tmp/pre_gen_ids.txt) <(ll-issues list --ids-only | sort))
       if [ -n "$NEW_IDS" ]; then echo "$NEW_IDS"; exit 0; else exit 1; fi
     on_yes: fan_out
     on_no: done
   ```

3. **Failed worker children**: Excluded from next generation (their branches were not merged by `ParallelRunner` in fail_mode: collect). This is acceptable — failed items are in `ParallelResult.failed` and can be reported.

**Alternative**: Rely on `ParallelResult.all_captures` — have `collect_children` read `${captured.fan_out.results}` and extract child IDs from worker captures instead of diffing the filesystem. This avoids the snapshot step but requires workers to emit their child IDs as captures (a behavior change to the `refine-to-ready-issue` sub-loop).

## Implementation Steps

1. Run `/ll:refine-issue ENH-1073` to add concrete `collect_children` implementation spec
2. Add `snapshot_ids` state to the ENH-1073 YAML example (or document the capture-based alternative)
3. Clarify `ParallelRunner` merge-back guarantees in FEAT-1075 notes (all successful workers merged before `run()` returns)
4. Add acceptance criterion: "parallel `recursive-refine` discovers all children from successful workers across N generations"

## Integration Map

### Files to Modify
- `.issues/enhancements/P3-ENH-1073-extend-orchestrator-loops-with-parallel-fan-out-support.md` — refine `collect_children` state with concrete implementation approach

### Dependencies
- FEAT-1075 merge-back behavior must be confirmed: does `ParallelRunner` guarantee all successful worker branches are on main before returning?
- `refine-to-ready-issue` sub-loop behavior: does it emit child issue IDs in captures? (If not, filesystem diff is the correct approach)

## Acceptance Criteria

- ENH-1073 `collect_children` state has a concrete shell command or capture-based implementation spec
- Failed worker children are explicitly addressed (included or excluded, with rationale)
- ENH-1073 success metric "no regressions in child issue discovery" is backed by the specified implementation

## Impact

- **Priority**: P3 — ENH-1073 is P3; this refinement must be done before implementing ENH-1073
- **Effort**: Very Small — Issue refinement only; no code changes
- **Risk**: Low — Clarifying documentation; no production code touched
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `orchestrator`, `recursive-refine`, `design`

---

## Session Log
- `/ll:capture-issue` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8ff9cd96-1544-4ffa-b28c-15aab5e9f3e8.jsonl`

---

**Open** | Created: 2026-04-18 | Priority: P3
