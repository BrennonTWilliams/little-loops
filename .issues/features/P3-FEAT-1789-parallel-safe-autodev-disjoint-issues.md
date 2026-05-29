---
id: FEAT-1789
title: parallel-safe autodev for disjoint issues
type: FEAT
status: open
priority: P3
captured_at: '2026-05-29T18:45:00Z'
labels:
- autodev
- ll-loop
- concurrency
- feature
depends_on: ENH-1787
relates_to:
- BUG-1760
---

# FEAT-1789: parallel-safe autodev for disjoint issues

## Summary

Currently autodev serializes all runs via scope `["."]` — only one autodev instance can run at a time regardless of which issues it targets. Autodev's refinement phase (format, refine, wire, confidence-check) is mostly read-only per-issue and writes only to disjoint issue files. With per-instance temp files, concurrent refinement of unrelated issues could be safe. Implementation still needs serialization or worktree isolation.

## Current Behavior

Autodev serializes all runs via scope `["."]` — only one autodev instance can run at a time regardless of which issues it targets. All temp files (`.loops/tmp/autodev-queue.txt`, `autodev-passed.txt`, `autodev-skipped.txt`, `autodev-inflight`, `autodev-broke-down`, `autodev-pre-ids.txt`, `autodev-post-ids.txt`, `autodev-diff-ids.txt`, `autodev-new-children.txt`, `autodev-decide-ran`) are hardcoded paths shared across instances. Git operations (`git mv` of parent issue files, `ll-auto --only` for implementation) all operate on the same working tree.

## Expected Behavior

Multiple `ll-loop run autodev` invocations with disjoint issue sets can run concurrently. Each instance gets isolated temp files scoped by instance ID. Refinement phases (format, refine, wire, confidence-check) operate on disjoint issue files with per-issue scope, allowing concurrent execution. Implementation phases coordinate through either a full-repo lock or worktree isolation.

## Motivation

Running two independent autodev sessions (e.g. `autodev BUG-031` and `autodev ENH-1699,ENH-1700`) concurrently would cut wall-clock time for issue backlogs that contain unrelated work. The refinement pipeline spends significant time waiting on LLM responses — overlapping that wait time across issues is the primary win.

## Use Case

**Who**: Developer or automation pipeline managing a backlog of unrelated issues.

**Context**: The developer has two independent issues (e.g. BUG-031 and ENH-1699,ENH-1700) that need refinement. Each set touches different parts of the codebase and has no overlapping source files.

**Goal**: Run `ll-loop run autodev BUG-031` and `ll-loop run autodev ENH-1699,ENH-1700` concurrently to cut wall-clock time.

**Outcome**: Both autodev sessions complete refinement in parallel, overlapping LLM response wait time. Implementation phases serialize via lock or worktree. Total wall-clock time approaches max(single-instance time) rather than sum(all instances).

## Obstacles

1. **Shared temp files**: `.loops/tmp/autodev-queue.txt`, `autodev-passed.txt`, `autodev-skipped.txt`, `autodev-inflight`, `autodev-broke-down`, `autodev-pre-ids.txt`, `autodev-post-ids.txt`, `autodev-diff-ids.txt`, `autodev-new-children.txt`, `autodev-decide-ran` — all hardcoded paths shared across instances.

2. **Git operations**: `enqueue_children` and `enqueue_or_skip` do `git mv` of parent issue files. `implement_current` runs `ll-auto --only` which makes source changes and git commits. Concurrent git operations on the same working tree race.

3. **Disjointness detection**: Two issues targeting different areas can still touch overlapping source files during implementation. Need a way to know they're truly disjoint before allowing parallel implementation.

## Proposed Solution

1. **Scope temp files by instance ID**: Change all `.loops/tmp/autodev-*` paths to `.loops/tmp/autodev-<instance_id>-*` so concurrent instances have isolated state.

2. **Split scope**: Refinement phase uses issue-specific scope (e.g., `.issues/<type>/<issue-file>.md`) so concurrent refinement of disjoint issues doesn't conflict. Implementation phase still requires `["."]` or worktree isolation.

3. **Worktree isolation for implementation**: When an issue reaches `implement_current`, either acquire the full-repo lock, or spawn implementation in an isolated worktree so it doesn't block refinement of other issues.

## Acceptance Criteria

- Two `ll-loop run autodev` invocations with disjoint issue sets can run refinement concurrently
- Shared temp files are fully isolated per instance
- Implementation phase coordinates safely (lock or worktree)
- Backward compatible: single-issue autodev behavior unchanged

## Implementation Steps

1. **Add instance_id plumbing**: Ensure every autodev invocation gets a unique instance ID, building on ENH-1354 and ENH-1726 for runtime file path scoping.

2. **Scope temp files by instance ID**: Change all hardcoded `.loops/tmp/autodev-*` paths to `.loops/tmp/autodev-<instance_id>-*` in `scripts/little_loops/loops/autodev.yaml`.

3. **Split scope for refinement vs implementation**: Refinement phase uses issue-specific scope (`.issues/<type>/<issue-file>.md`). Implementation phase retains `["."]` or acquires worktree isolation.

4. **Add worktree isolation or lock for implementation**: When an issue reaches `implement_current`, either acquire a full-repo lock or spawn implementation in an isolated worktree.

5. **Update tests**: Add concurrent execution test cases to `scripts/tests/test_builtin_loops.py`. Verify temp file isolation and disjointness detection.

6. **Verify backward compatibility**: Run single-issue autodev to confirm behavior is unchanged.

## API/Interface

No public API changes. Internal contract changes:

- Temp file path convention: `.loops/tmp/autodev-*` → `.loops/tmp/autodev-<instance_id>-*`
- Loop scope parameter: refinement phase accepts issue-specific scope in addition to full-repo `["."]`
- New worktree/lock coordination point in `implement_current` state

## Impact

- **Priority**: P3
- **Effort**: Medium — requires touching all temp file references in autodev.yaml, adding instance_id plumbing, and designing the split-scope or worktree handoff
- **Risk**: Medium — concurrency bugs are subtle; needs thorough testing of edge cases (child detection across instances, queue file isolation, git state coordination)
- **Breaking Change**: No — single-instance behavior unchanged

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — all temp file references, scope definitions, implement_current state
- `scripts/little_loops/fsm/concurrency.py` — lock or worktree coordination for implementation phase
- `scripts/little_loops/cli/loop/run.py` — instance_id plumbing on invocation

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/lifecycle.py` — imports loop runner, may need instance_id passthrough
- `scripts/little_loops/cli/loop/next_loop.py` — schedules autodev runs
- `scripts/little_loops/subprocess_utils.py` — shared subprocess utilities

### Similar Patterns
- `scripts/little_loops/loops/harness-multi-item.yaml` — multi-item loop that may have similar scope/isolation patterns
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — sprint loop with multi-issue coordination

### Tests
- `scripts/tests/test_builtin_loops.py` — add concurrent execution test cases, temp file isolation tests

### Documentation
- `docs/reference/API.md` — document new instance_id conventions if public
- `docs/development/TROUBLESHOOTING.md` — add concurrent autodev guidance

### Configuration
- N/A

## Related Issues

- BUG-1760 (cancelled): original misdiagnosis that led to this feature request
- ENH-1354: multi-instance instance_id generation and runtime file path scoping
- ENH-1726: per-run artifact dirs for built-in loops

**Open** | Created: 2026-05-29 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-05-29T18:46:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e778a487-9894-450e-a694-a731058b51d1.jsonl`
